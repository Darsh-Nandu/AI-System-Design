"""Domain models for the news aggregation pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


class ArticleStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    CLUSTERED = "clustered"  # same story, different angle
    STALE = "stale"
    ARCHIVED = "archived"


class PartitionTier(StrEnum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class DedupResult(StrEnum):
    ACCEPTED = "accepted"
    EXACT_DUPLICATE = "exact_duplicate"
    CLUSTERED = "clustered"


class Entity(BaseModel):
    text: str
    label: str  # PERSON, ORG, GPE, DATE, EVENT, etc.

    def __hash__(self) -> int:
        return hash((self.text.lower(), self.label))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return False
        return self.text.lower() == other.text.lower() and self.label == other.label


class RawArticle(BaseModel):
    """Article as it arrives from scrapers — minimal, unprocessed."""

    url: str
    source: str
    title: str
    body: str
    published_at: datetime
    raw_tags: list[str] = Field(default_factory=list)


class EnrichedArticle(BaseModel):
    """Article after NLP enrichment but before deduplication."""

    id: UUID = Field(default_factory=uuid4)
    raw: RawArticle
    entities: list[Entity] = Field(default_factory=list)
    entity_fingerprint: str = ""
    topics: list[str] = Field(default_factory=list)
    is_volatile: bool = False
    partition: PartitionTier = PartitionTier.WARM
    embedding: list[float] = Field(default_factory=list)


class Article(BaseModel):
    """Fully processed article stored in the system."""

    id: UUID = Field(default_factory=uuid4)
    url: str
    source: str
    title: str
    body: str
    published_at: datetime
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    entities: list[Entity] = Field(default_factory=list)
    entity_fingerprint: str = ""
    topics: list[str] = Field(default_factory=list)
    is_volatile: bool = False
    partition: PartitionTier = PartitionTier.WARM
    status: ArticleStatus = ArticleStatus.ACCEPTED
    story_id: UUID | None = None
    similarity_score: float | None = None
    stale: bool = False
    stale_at: datetime | None = None
    superseded_by: UUID | None = None

    @property
    def is_current(self) -> bool:
        return not self.stale and self.status != ArticleStatus.ARCHIVED


class Story(BaseModel):
    """Cluster of articles covering the same event from different angles."""

    id: UUID = Field(default_factory=uuid4)
    topic: str
    entity_fingerprint: str
    article_ids: list[UUID] = Field(default_factory=list)
    latest_article_id: UUID | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class VolatileTopic(BaseModel):
    """A topic that requires hot-partition treatment and frequent freshness checks."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    keywords: list[str] = Field(default_factory=list)
    entity_labels: list[str] = Field(default_factory=list)
    hot_until: datetime | None = None  # None = indefinitely hot
    auto_detected: bool = False


class KafkaArticleMessage(BaseModel):
    """Message schema on the raw-articles Kafka topic."""

    url: str
    source: str
    title: str
    body: str
    published_at: str  # ISO 8601
    raw_tags: list[str] = Field(default_factory=list)
    scraped_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_raw_article(self) -> RawArticle:
        return RawArticle(
            url=self.url,
            source=self.source,
            title=self.title,
            body=self.body,
            published_at=datetime.fromisoformat(self.published_at),
            raw_tags=self.raw_tags,
        )
