"""Stage 2 — Cosine similarity deduplication via Qdrant.

Thresholds (from config):
  > 0.97  → EXACT DUPLICATE   → reject
  0.85-0.97 → CLUSTERED       → accept + link to story
  < 0.85  → ACCEPTED          → new independent article
"""

from __future__ import annotations

import uuid

from news_aggregator.config import get_settings
from news_aggregator.logging import get_logger
from news_aggregator.metrics import dedup_stage2_checks_total
from news_aggregator.models import DedupResult, EnrichedArticle, PartitionTier
from news_aggregator.storage.qdrant import QdrantStore, SimilarityMatch

settings = get_settings()
logger = get_logger(__name__)


async def check_similarity(
    article: EnrichedArticle,
    qdrant: QdrantStore,
) -> tuple[DedupResult, uuid.UUID | None, float | None]:
    """Run Stage 2 similarity check.

    Returns:
        (DedupResult, existing_story_id or None, best_score or None)
    """
    partitions_to_check = _partitions_to_search(article.partition)
    best_match: SimilarityMatch | None = None

    for partition in partitions_to_check:
        matches = await qdrant.search_similar(
            embedding=article.embedding,
            partition=partition,
            limit=5,
            score_threshold=settings.dedup_cluster_threshold,
        )
        for m in matches:
            if not m.is_stale:
                if best_match is None or m.score > best_match.score:
                    best_match = m

    if best_match is None:
        dedup_stage2_checks_total.labels(result="accepted").inc()
        return DedupResult.ACCEPTED, None, None

    score = best_match.score

    if score >= settings.dedup_exact_threshold:
        logger.info(
            "dedup_exact_duplicate",
            url=article.raw.url,
            score=score,
            matched_id=str(best_match.article_id),
        )
        dedup_stage2_checks_total.labels(result="duplicate").inc()
        return DedupResult.EXACT_DUPLICATE, best_match.story_id, score

    # 0.85 ≤ score < 0.97 → cluster
    logger.info(
        "dedup_clustered",
        url=article.raw.url,
        score=score,
        existing_story=str(best_match.story_id) if best_match.story_id else None,
    )
    dedup_stage2_checks_total.labels(result="clustered").inc()
    return DedupResult.CLUSTERED, best_match.story_id, score


def _partitions_to_search(article_partition: PartitionTier) -> list[PartitionTier]:
    """Hot articles get checked against all partitions; others just warm."""
    if article_partition == PartitionTier.HOT:
        return [PartitionTier.HOT, PartitionTier.WARM]
    return [PartitionTier.WARM, PartitionTier.HOT]
