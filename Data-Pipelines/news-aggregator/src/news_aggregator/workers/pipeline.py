"""Article processing pipeline — orchestrates all stages for a single article."""

from __future__ import annotations

import time
import uuid
from datetime import datetime

from news_aggregator.deduplication.fingerprint import has_candidate_overlap, record_fingerprint
from news_aggregator.deduplication.similarity import check_similarity
from news_aggregator.invalidation.checker import trigger_invalidation
from news_aggregator.logging import get_logger
from news_aggregator.metrics import articles_processed_total, processing_duration_seconds
from news_aggregator.models import (
    Article,
    ArticleStatus,
    DedupResult,
    EnrichedArticle,
    RawArticle,
)
from news_aggregator.storage.postgres import ArticleRepository, AsyncSessionFactory, StoryRepository
from news_aggregator.storage.qdrant import QdrantStore
from news_aggregator.storage.redis_client import RedisStore
from news_aggregator.workers.embedding import embed
from news_aggregator.workers.enrichment import enrich

logger = get_logger(__name__)


class ArticlePipeline:
    """
    Stateless pipeline: enrich → embed → dedup → write → invalidate.
    One instance is shared per worker process; all methods are async-safe.
    """

    def __init__(self, qdrant: QdrantStore, redis: RedisStore) -> None:
        self._qdrant = qdrant
        self._redis = redis

    async def process(self, raw: RawArticle) -> ArticleStatus:
        """Process one article through the full pipeline. Returns final status."""
        start = time.monotonic()

        try:
            # ── Stage 1: Enrich ──────────────────────────────────────────
            t = time.monotonic()
            enriched = await enrich(raw, self._redis)
            processing_duration_seconds.labels(stage="enrich").observe(time.monotonic() - t)

            # ── Stage 2: Embed ───────────────────────────────────────────
            t = time.monotonic()
            text = f"{raw.title} {raw.body[:1000]}"
            enriched.embedding = await embed(text)
            processing_duration_seconds.labels(stage="embed").observe(time.monotonic() - t)

            # ── Stage 3: Deduplication ───────────────────────────────────
            t = time.monotonic()
            status = await self._dedup(enriched)
            processing_duration_seconds.labels(stage="dedup").observe(time.monotonic() - t)

            if status == ArticleStatus.DUPLICATE:
                articles_processed_total.labels(status="duplicate").inc()
                return status

            # ── Stage 4: Write ───────────────────────────────────────────
            t = time.monotonic()
            article = await self._write(enriched, status)
            processing_duration_seconds.labels(stage="write").observe(time.monotonic() - t)

            # ── Stage 5: Event-driven invalidation ──────────────────────
            await trigger_invalidation(article, self._qdrant, self._redis)

            articles_processed_total.labels(status=status.value).inc()
            logger.info(
                "article_processed",
                url=raw.url,
                status=status.value,
                total_ms=round((time.monotonic() - start) * 1000, 1),
            )
            return status

        except Exception:
            articles_processed_total.labels(status="error").inc()
            logger.exception("article_processing_failed", url=raw.url)
            raise

    async def _dedup(self, enriched: EnrichedArticle) -> ArticleStatus:
        # Stage 1: fingerprint pre-filter
        has_overlap = await has_candidate_overlap(enriched, self._redis)
        if not has_overlap:
            await record_fingerprint(enriched, self._redis)
            return ArticleStatus.ACCEPTED

        # Stage 2: cosine similarity
        result, existing_story_id, score = await check_similarity(enriched, self._qdrant)

        if result == DedupResult.EXACT_DUPLICATE:
            return ArticleStatus.DUPLICATE

        await record_fingerprint(enriched, self._redis)

        if result == DedupResult.CLUSTERED:
            enriched.story_id = existing_story_id  # type: ignore[attr-defined]
            enriched.similarity_score = score  # type: ignore[attr-defined]
            return ArticleStatus.CLUSTERED

        return ArticleStatus.ACCEPTED

    async def _write(self, enriched: EnrichedArticle, status: ArticleStatus) -> Article:
        story_id: uuid.UUID | None = getattr(enriched, "story_id", None)
        similarity_score: float | None = getattr(enriched, "similarity_score", None)

        article = Article(
            id=enriched.id,
            url=enriched.raw.url,
            source=enriched.raw.source,
            title=enriched.raw.title,
            body=enriched.raw.body,
            published_at=enriched.raw.published_at,
            processed_at=datetime.utcnow(),
            entities=enriched.entities,
            entity_fingerprint=enriched.entity_fingerprint,
            topics=enriched.topics,
            is_volatile=enriched.is_volatile,
            partition=enriched.partition,
            status=status,
            story_id=story_id,
            similarity_score=similarity_score,
        )

        # Attach embedding for Qdrant (not persisted in Postgres)
        article_with_embedding = article.model_copy()
        object.__setattr__(article_with_embedding, "embedding", enriched.embedding)

        async with AsyncSessionFactory() as session:
            article_repo = ArticleRepository(session)
            story_repo = StoryRepository(session)

            await article_repo.upsert(article)

            if status == ArticleStatus.CLUSTERED and story_id:
                await story_repo.update_latest(story_id, article.id)
                await article_repo.assign_story(article.id, story_id)
            elif status == ArticleStatus.CLUSTERED:
                # Create new story cluster
                story = await story_repo.get_or_create(
                    fingerprint=article.entity_fingerprint,
                    topic=", ".join(article.topics),
                )
                await article_repo.assign_story(article.id, story.id)
                article = article.model_copy(update={"story_id": story.id})

        await self._qdrant.upsert(article_with_embedding)  # type: ignore[arg-type]
        return article
