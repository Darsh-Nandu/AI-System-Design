"""Unit tests for the article processing pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from news_aggregator.models import ArticleStatus, RawArticle
from news_aggregator.workers.pipeline import ArticlePipeline


@pytest.fixture
def pipeline(mock_qdrant: AsyncMock, mock_redis: AsyncMock) -> ArticlePipeline:
    return ArticlePipeline(qdrant=mock_qdrant, redis=mock_redis)


@pytest.mark.asyncio
async def test_pipeline_accepts_new_article(
    pipeline: ArticlePipeline, raw_article: RawArticle
):
    with (
        patch("news_aggregator.workers.pipeline.enrich", new_callable=AsyncMock) as mock_enrich,
        patch("news_aggregator.workers.pipeline.embed", new_callable=AsyncMock) as mock_embed,
        patch("news_aggregator.workers.pipeline.has_candidate_overlap", new_callable=AsyncMock) as mock_fp,
        patch("news_aggregator.workers.pipeline.record_fingerprint", new_callable=AsyncMock),
        patch("news_aggregator.workers.pipeline.check_similarity", new_callable=AsyncMock) as mock_sim,
        patch("news_aggregator.workers.pipeline.trigger_invalidation", new_callable=AsyncMock),
        patch("news_aggregator.workers.pipeline.AsyncSessionFactory") as mock_session_factory,
    ):
        from news_aggregator.models import EnrichedArticle, Entity, PartitionTier
        mock_enrich.return_value = EnrichedArticle(
            raw=raw_article,
            entities=[Entity(text="Biden", label="PERSON")],
            entity_fingerprint="abc123",
            topics=["politics"],
            is_volatile=False,
            partition=PartitionTier.WARM,
            embedding=[0.1] * 384,
        )
        mock_embed.return_value = [0.1] * 384
        mock_fp.return_value = False  # no overlap → skip stage 2

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_ctx.scalar = AsyncMock(return_value=None)
        mock_ctx.execute = AsyncMock()
        mock_ctx.add = AsyncMock()
        mock_ctx.commit = AsyncMock()
        mock_ctx.refresh = AsyncMock()
        mock_session_factory.return_value = mock_ctx

        status = await pipeline.process(raw_article)
        assert status == ArticleStatus.ACCEPTED


@pytest.mark.asyncio
async def test_pipeline_rejects_exact_duplicate(
    pipeline: ArticlePipeline, raw_article: RawArticle
):
    with (
        patch("news_aggregator.workers.pipeline.enrich", new_callable=AsyncMock) as mock_enrich,
        patch("news_aggregator.workers.pipeline.embed", new_callable=AsyncMock) as mock_embed,
        patch("news_aggregator.workers.pipeline.has_candidate_overlap", new_callable=AsyncMock) as mock_fp,
        patch("news_aggregator.workers.pipeline.check_similarity", new_callable=AsyncMock) as mock_sim,
    ):
        from news_aggregator.models import DedupResult, EnrichedArticle, Entity, PartitionTier
        mock_enrich.return_value = EnrichedArticle(
            raw=raw_article,
            entities=[Entity(text="Biden", label="PERSON")],
            entity_fingerprint="abc123",
            topics=["politics"],
            is_volatile=False,
            partition=PartitionTier.WARM,
            embedding=[0.1] * 384,
        )
        mock_embed.return_value = [0.1] * 384
        mock_fp.return_value = True  # fingerprint match → go to stage 2
        mock_sim.return_value = (DedupResult.EXACT_DUPLICATE, None, 0.99)

        status = await pipeline.process(raw_article)
        assert status == ArticleStatus.DUPLICATE
