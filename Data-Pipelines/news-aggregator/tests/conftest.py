"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from news_aggregator.models import (
    Article,
    ArticleStatus,
    EnrichedArticle,
    Entity,
    PartitionTier,
    RawArticle,
)


@pytest.fixture
def raw_article() -> RawArticle:
    return RawArticle(
        url="https://bbc.com/news/test-article-123",
        source="BBC News",
        title="US President Signs Climate Bill Into Law",
        body=(
            "President Biden signed the landmark climate bill at the White House ceremony "
            "on Wednesday. The legislation, backed by senators from both parties, introduces "
            "sweeping emissions targets and renewable energy subsidies."
        ),
        published_at=datetime(2024, 11, 1, 14, 30, tzinfo=timezone.utc),
        raw_tags=["climate", "politics", "US"],
    )


@pytest.fixture
def raw_article_duplicate(raw_article: RawArticle) -> RawArticle:
    """Same story, different wording (BBC vs CNN)."""
    return RawArticle(
        url="https://cnn.com/news/climate-bill-signed",
        source="CNN",
        title="Biden Enacts Historic Environmental Legislation",
        body=(
            "The US leader enacted sweeping environmental legislation in Washington on Wednesday. "
            "The bill, supported by both parties, sets ambitious carbon reduction targets "
            "and introduces major subsidies for renewable energy sources."
        ),
        published_at=datetime(2024, 11, 1, 14, 45, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_entities() -> list[Entity]:
    return [
        Entity(text="Biden", label="PERSON"),
        Entity(text="White House", label="FAC"),
        Entity(text="US", label="GPE"),
    ]


@pytest.fixture
def enriched_article(raw_article: RawArticle, sample_entities: list[Entity]) -> EnrichedArticle:
    return EnrichedArticle(
        raw=raw_article,
        entities=sample_entities,
        entity_fingerprint="abc123def456",
        topics=["politics", "climate"],
        is_volatile=False,
        partition=PartitionTier.WARM,
        embedding=[0.1] * 384,
    )


@pytest.fixture
def stored_article(enriched_article: EnrichedArticle) -> Article:
    return Article(
        id=uuid4(),
        url=enriched_article.raw.url,
        source=enriched_article.raw.source,
        title=enriched_article.raw.title,
        body=enriched_article.raw.body,
        published_at=enriched_article.raw.published_at,
        entities=enriched_article.entities,
        entity_fingerprint=enriched_article.entity_fingerprint,
        topics=enriched_article.topics,
        is_volatile=enriched_article.is_volatile,
        partition=enriched_article.partition,
        status=ArticleStatus.ACCEPTED,
    )


@pytest.fixture
def mock_qdrant() -> AsyncMock:
    mock = AsyncMock()
    mock.search_similar.return_value = []
    mock.upsert.return_value = None
    mock.mark_stale.return_value = None
    mock.ensure_collections.return_value = None
    return mock


@pytest.fixture
def mock_redis() -> AsyncMock:
    mock = AsyncMock()
    mock.has_fingerprint.return_value = False
    mock.set_fingerprint.return_value = None
    mock.is_volatile_keyword.return_value = False
    return mock
