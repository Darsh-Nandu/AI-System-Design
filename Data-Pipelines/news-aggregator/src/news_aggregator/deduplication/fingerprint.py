"""Stage 1 — Entity fingerprint pre-filter.

Eliminates ~80% of comparison candidates before any embedding math.
If no overlapping named entities → articles cannot be about the same story.
"""

from __future__ import annotations

from news_aggregator.logging import get_logger
from news_aggregator.metrics import dedup_stage1_hits_total
from news_aggregator.models import EnrichedArticle
from news_aggregator.storage.redis_client import RedisStore

logger = get_logger(__name__)


async def has_candidate_overlap(article: EnrichedArticle, redis: RedisStore) -> bool:
    """Return True if there are existing articles that share named entities.

    Uses Redis as a fast bloom-filter-like cache of seen fingerprints.
    A miss here means we can skip Stage 2 entirely.
    """
    fingerprint = article.entity_fingerprint
    if not fingerprint:
        # No extractable entities — treat as always needing full check
        return True

    seen = await redis.has_fingerprint(fingerprint)
    if not seen:
        dedup_stage1_hits_total.inc()
        logger.debug("stage1_no_overlap", fingerprint=fingerprint, url=article.raw.url)
    return seen


async def record_fingerprint(article: EnrichedArticle, redis: RedisStore) -> None:
    """Record the fingerprint so future articles can match against it."""
    if article.entity_fingerprint:
        await redis.set_fingerprint(article.entity_fingerprint)
