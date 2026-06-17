"""Unit tests for the deduplication stages."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from news_aggregator.deduplication.fingerprint import has_candidate_overlap, record_fingerprint
from news_aggregator.deduplication.similarity import check_similarity
from news_aggregator.models import DedupResult, EnrichedArticle, PartitionTier
from news_aggregator.storage.qdrant import SimilarityMatch


@pytest.mark.asyncio
async def test_stage1_no_overlap_when_fingerprint_not_seen(
    enriched_article: EnrichedArticle, mock_redis: AsyncMock
):
    mock_redis.has_fingerprint.return_value = False
    result = await has_candidate_overlap(enriched_article, mock_redis)
    assert result is False


@pytest.mark.asyncio
async def test_stage1_overlap_when_fingerprint_seen(
    enriched_article: EnrichedArticle, mock_redis: AsyncMock
):
    mock_redis.has_fingerprint.return_value = True
    result = await has_candidate_overlap(enriched_article, mock_redis)
    assert result is True


@pytest.mark.asyncio
async def test_stage1_empty_fingerprint_always_overlaps(
    enriched_article: EnrichedArticle, mock_redis: AsyncMock
):
    enriched_article.entity_fingerprint = ""
    result = await has_candidate_overlap(enriched_article, mock_redis)
    assert result is True  # no fingerprint → must run stage 2


@pytest.mark.asyncio
async def test_stage2_accepted_when_no_similar(
    enriched_article: EnrichedArticle, mock_qdrant: AsyncMock
):
    mock_qdrant.search_similar.return_value = []
    result, story_id, score = await check_similarity(enriched_article, mock_qdrant)
    assert result == DedupResult.ACCEPTED
    assert story_id is None
    assert score is None


@pytest.mark.asyncio
async def test_stage2_exact_duplicate_above_threshold(
    enriched_article: EnrichedArticle, mock_qdrant: AsyncMock
):
    existing_id = uuid4()
    mock_qdrant.search_similar.return_value = [
        SimilarityMatch(article_id=existing_id, score=0.98, is_stale=False, story_id=None)
    ]
    result, story_id, score = await check_similarity(enriched_article, mock_qdrant)
    assert result == DedupResult.EXACT_DUPLICATE
    assert score == pytest.approx(0.98)


@pytest.mark.asyncio
async def test_stage2_clustered_in_range(
    enriched_article: EnrichedArticle, mock_qdrant: AsyncMock
):
    story_id = uuid4()
    mock_qdrant.search_similar.return_value = [
        SimilarityMatch(article_id=uuid4(), score=0.90, is_stale=False, story_id=story_id)
    ]
    result, returned_story_id, score = await check_similarity(enriched_article, mock_qdrant)
    assert result == DedupResult.CLUSTERED
    assert returned_story_id == story_id


@pytest.mark.asyncio
async def test_stage2_ignores_stale_matches(
    enriched_article: EnrichedArticle, mock_qdrant: AsyncMock
):
    mock_qdrant.search_similar.return_value = [
        SimilarityMatch(article_id=uuid4(), score=0.99, is_stale=True, story_id=None)
    ]
    result, _, _ = await check_similarity(enriched_article, mock_qdrant)
    assert result == DedupResult.ACCEPTED
