"""Article search and ingest endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_aggregator.api.schemas import (
    ArticleOut,
    EntityOut,
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResult,
)
from news_aggregator.models import ArticleStatus, KafkaArticleMessage, RawArticle
from news_aggregator.storage.postgres import ArticleORM, AsyncSessionFactory, get_session
from news_aggregator.storage.qdrant import QdrantStore
from news_aggregator.storage.redis_client import RedisStore
from news_aggregator.workers.embedding import embed
from news_aggregator.workers.pipeline import ArticlePipeline

router = APIRouter(prefix="/articles", tags=["articles"])


def _orm_to_out(orm: ArticleORM) -> ArticleOut:
    entities = [EntityOut(**e) for e in (orm.entities or [])]
    return ArticleOut(
        id=orm.id,
        url=orm.url,
        source=orm.source,
        title=orm.title,
        published_at=orm.published_at,
        processed_at=orm.processed_at,
        topics=orm.topics or [],
        entities=entities,
        partition=orm.partition,
        stale=orm.stale,
        story_id=orm.story_id,
        superseded_by=orm.superseded_by,
        stale_at=orm.stale_at,
    )


@router.post("/search", response_model=SearchResult)
async def search_articles(
    request: SearchRequest,
    session: AsyncSession = Depends(get_session),
) -> SearchResult:
    """Semantic search over articles. Routes to hot partition for volatile queries."""
    from news_aggregator.models import PartitionTier

    qdrant = QdrantStore()
    query_embedding = await embed(request.query)

    # Try HOT partition first (volatile topics), fall back to WARM
    partition_order = [PartitionTier.HOT, PartitionTier.WARM, PartitionTier.COLD]
    if request.partition:
        partition_order = [PartitionTier(request.partition)]

    article_ids: list[UUID] = []
    for partition in partition_order:
        matches = await qdrant.search_similar(
            embedding=query_embedding,
            partition=partition,
            limit=request.limit,
            score_threshold=0.5,
        )
        for m in matches:
            if not m.is_stale or request.include_stale:
                article_ids.append(m.article_id)
        if len(article_ids) >= request.limit:
            break

    await qdrant.close()

    if not article_ids:
        return SearchResult(articles=[], total=0, query=request.query)

    q = select(ArticleORM).where(ArticleORM.id.in_(article_ids))
    if not request.include_stale:
        q = q.where(ArticleORM.stale == False)  # noqa: E712
    rows = await session.scalars(q)
    articles = [_orm_to_out(row) for row in rows.all()]

    return SearchResult(articles=articles, total=len(articles), query=request.query)


@router.get("/{article_id}", response_model=ArticleOut)
async def get_article(
    article_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ArticleOut:
    row = await session.get(ArticleORM, article_id)
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    return _orm_to_out(row)


@router.post("/ingest", response_model=IngestResponse, status_code=202)
async def ingest_article(
    request: IngestRequest,
    session: AsyncSession = Depends(get_session),
) -> IngestResponse:
    """Manually ingest a single article (bypasses Kafka — for testing/editorial)."""
    raw = RawArticle(
        url=request.url,
        source=request.source,
        title=request.title,
        body=request.body,
        published_at=request.published_at,
        raw_tags=request.tags,
    )

    qdrant = QdrantStore()
    redis = RedisStore()
    await qdrant.ensure_collections()

    pipeline = ArticlePipeline(qdrant=qdrant, redis=redis)
    status = await pipeline.process(raw)

    await qdrant.close()
    await redis.close()

    return IngestResponse(
        article_id=uuid4(),
        status=status.value,
        message=f"Article processed with status: {status.value}",
    )
