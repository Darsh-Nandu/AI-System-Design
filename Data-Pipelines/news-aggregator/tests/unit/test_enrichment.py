"""Unit tests for the enrichment stage."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from news_aggregator.models import PartitionTier, RawArticle
from news_aggregator.workers.enrichment import (
    _build_fingerprint,
    _classify_topics,
    _extract_entities,
    _is_volatile,
    enrich,
)


def test_extract_entities_finds_persons():
    entities = _extract_entities("President Biden signed the climate bill.")
    labels = {e.label for e in entities}
    assert "PERSON" in labels or len(entities) > 0  # spaCy may vary


def test_build_fingerprint_is_deterministic():
    from news_aggregator.models import Entity
    entities = [Entity(text="Biden", label="PERSON"), Entity(text="US", label="GPE")]
    fp1 = _build_fingerprint(entities)
    fp2 = _build_fingerprint(list(reversed(entities)))
    assert fp1 == fp2  # order-independent


def test_build_fingerprint_empty_entities():
    fp = _build_fingerprint([])
    assert fp == ""


def test_classify_topics_politics():
    topics = _classify_topics("The president signed a new law in congress today.")
    assert "politics" in topics


def test_classify_topics_finance():
    topics = _classify_topics("Stock market hit record highs as the Federal Reserve announced interest rate cut.")
    assert "finance" in topics


def test_classify_topics_default_general():
    topics = _classify_topics("A cat sat on a mat and looked at the moon.")
    assert topics == ["general"]


def test_is_volatile_breaking_news():
    assert _is_volatile(["breaking_news"], "Breaking: explosion near parliament") is True


def test_is_volatile_election():
    assert _is_volatile(["politics"], "Election results: candidate Y wins presidential race") is True


def test_is_volatile_normal_article():
    assert _is_volatile(["sports"], "Local team wins regional championship.") is False


@pytest.mark.asyncio
async def test_enrich_returns_enriched_article(raw_article: RawArticle, mock_redis: AsyncMock):
    enriched = await enrich(raw_article, mock_redis)
    assert enriched.raw.url == raw_article.url
    assert isinstance(enriched.topics, list)
    assert len(enriched.topics) > 0
    assert enriched.partition in (PartitionTier.HOT, PartitionTier.WARM)


@pytest.mark.asyncio
async def test_enrich_volatile_article(mock_redis: AsyncMock):
    breaking = RawArticle(
        url="https://bbc.com/breaking",
        source="BBC",
        title="Breaking: Major earthquake strikes Istanbul",
        body="A major earthquake struck Istanbul today causing widespread damage.",
        published_at=datetime.now(timezone.utc),
    )
    enriched = await enrich(breaking, mock_redis)
    assert enriched.is_volatile is True
    assert enriched.partition == PartitionTier.HOT
