"""Event-driven staleness invalidation.

Triggered on every accepted article. Searches for existing articles that
this new article supersedes and marks them stale immediately — not on a schedule.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta

from news_aggregator.config import get_settings
from news_aggregator.logging import get_logger
from news_aggregator.metrics import articles_stale_marked_total
from news_aggregator.models import Article, PartitionTier
from news_aggregator.storage.postgres import ArticleRepository, AsyncSessionFactory
from news_aggregator.storage.qdrant import QdrantStore
from news_aggregator.storage.redis_client import RedisStore

settings = get_settings()
logger = get_logger(__name__)

# Supersession requires a meaningful time gap (same article reposted is just a duplicate)
MIN_SUPERSESSION_GAP_MINUTES = 5


async def trigger_invalidation(
    new_article: Article,
    qdrant: QdrantStore,
    redis: RedisStore,
) -> None:
    """Check if new_article supersedes any existing articles and mark them stale."""
    if not new_article.entity_fingerprint or not hasattr(new_article, "_embedding"):
        return

    embedding = getattr(new_article, "_embedding", None)
    if not embedding:
        return

    partitions = [PartitionTier.HOT, PartitionTier.WARM]
    candidates: list[tuple[uuid.UUID, float, PartitionTier]] = []

    for partition in partitions:
        matches = await qdrant.search_similar(
            embedding=embedding,
            partition=partition,
            limit=10,
            score_threshold=settings.dedup_cluster_threshold,
        )
        for m in matches:
            if m.article_id != new_article.id and not m.is_stale:
                candidates.append((m.article_id, m.score, partition))

    if not candidates:
        return

    async with AsyncSessionFactory() as session:
        repo = ArticleRepository(session)
        for article_id, score, partition in candidates:
            existing_articles = await repo.get_by_fingerprint(
                new_article.entity_fingerprint, exclude_stale=True
            )
            for existing in existing_articles:
                if existing.id == article_id:
                    # Check time gap to avoid marking near-simultaneous articles stale
                    if existing.published_at and new_article.published_at:
                        gap = new_article.published_at - existing.published_at
                        if gap < timedelta(minutes=MIN_SUPERSESSION_GAP_MINUTES):
                            continue
                    if new_article.published_at > existing.published_at:
                        await repo.mark_stale(article_id, new_article.id)
                        await qdrant.mark_stale(article_id, partition)
                        articles_stale_marked_total.inc()
                        logger.info(
                            "article_marked_stale",
                            stale_id=str(article_id),
                            superseded_by=str(new_article.id),
                            score=score,
                        )


async def run_hot_checker(qdrant: QdrantStore) -> None:
    """Background task: runs every 5 minutes on HOT partition for volatile topics."""
    logger.info("hot_checker_started", interval=settings.hot_checker_interval_seconds)
    while True:
        await asyncio.sleep(settings.hot_checker_interval_seconds)
        try:
            size = await qdrant.get_collection_size(PartitionTier.HOT)
            logger.info("hot_checker_tick", hot_partition_size=size)
            # Actual cross-article comparison would run here in production
            # (compare recent articles within the hot partition for supersession)
        except Exception:
            logger.exception("hot_checker_error")


async def run_cold_archiver() -> None:
    """Daily task: move WARM articles older than N days to COLD partition."""
    logger.info("cold_archiver_started", archive_after_days=settings.cold_archive_after_days)
    while True:
        await asyncio.sleep(86_400)  # once per day
        cutoff = datetime.utcnow() - timedelta(days=settings.cold_archive_after_days)
        try:
            async with AsyncSessionFactory() as session:
                from sqlalchemy import select, update
                from news_aggregator.storage.postgres import ArticleORM
                await session.execute(
                    update(ArticleORM)
                    .where(
                        ArticleORM.partition == PartitionTier.WARM.value,
                        ArticleORM.published_at < cutoff,
                        ArticleORM.stale == False,  # noqa: E712
                    )
                    .values(partition=PartitionTier.COLD.value)
                )
                await session.commit()
            logger.info("cold_archiver_tick", cutoff=cutoff.isoformat())
        except Exception:
            logger.exception("cold_archiver_error")
