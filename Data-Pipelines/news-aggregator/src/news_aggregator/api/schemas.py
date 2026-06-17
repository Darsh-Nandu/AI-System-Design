"""API request/response schemas — separate from domain models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EntityOut(BaseModel):
    text: str
    label: str


class ArticleOut(BaseModel):
    id: UUID
    url: str
    source: str
    title: str
    published_at: datetime
    processed_at: datetime
    topics: list[str]
    entities: list[EntityOut]
    partition: str
    stale: bool
    story_id: UUID | None
    superseded_by: UUID | None
    stale_at: datetime | None


class StoryOut(BaseModel):
    id: UUID
    topic: str
    article_count: int
    latest_article_id: UUID | None
    created_at: datetime
    updated_at: datetime


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    include_stale: bool = False
    partition: str | None = None
    limit: int = Field(default=10, ge=1, le=100)


class SearchResult(BaseModel):
    articles: list[ArticleOut]
    total: int
    query: str
    searched_at: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict[str, str]


class IngestRequest(BaseModel):
    """Manually ingest a single article (for testing / editorial use)."""
    url: str
    source: str
    title: str
    body: str
    published_at: datetime
    tags: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    article_id: UUID | None
    status: str
    message: str
