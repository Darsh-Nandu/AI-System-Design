"""PostgreSQL async storage — SQLAlchemy 2.0 ORM."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from news_aggregator.config import get_settings
from news_aggregator.models import Article, ArticleStatus, PartitionTier, Story

settings = get_settings()


class Base(DeclarativeBase):
    pass


class ArticleORM(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    entities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    entity_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    topics: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    is_volatile: Mapped[bool] = mapped_column(Boolean, default=False)
    partition: Mapped[str] = mapped_column(String(10), default="warm")
    status: Mapped[str] = mapped_column(String(20), default="accepted", index=True)
    story_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("stories.id"), nullable=True, index=True
    )
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    story: Mapped[StoryORM | None] = relationship("StoryORM", back_populates="articles")

    __table_args__ = (
        UniqueConstraint("url", name="uq_articles_url"),
        Index("ix_articles_entity_fingerprint_stale", "entity_fingerprint", "stale"),
        Index("ix_articles_partition_stale", "partition", "stale"),
        Index("ix_articles_published_at", "published_at"),
    )


class StoryORM(Base):
    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    entity_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    latest_article_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    articles: Mapped[list[ArticleORM]] = relationship("ArticleORM", back_populates="story")


class VolatileTopicORM(Base):
    __tablename__ = "volatile_topics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    hot_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_detected: Mapped[bool] = mapped_column(Boolean, default=False)


# ── Engine & session factory ────────────────────────────────────────────────

_engine = create_async_engine(
    settings.postgres_dsn,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session


async def create_tables() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── Repository ──────────────────────────────────────────────────────────────


class ArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, article: Article) -> ArticleORM:
        existing = await self._session.scalar(
            select(ArticleORM).where(ArticleORM.url == article.url)
        )
        if existing:
            return existing

        orm = ArticleORM(
            id=article.id,
            url=article.url,
            source=article.source,
            title=article.title,
            body=article.body,
            published_at=article.published_at,
            entities=[e.model_dump() for e in article.entities],
            entity_fingerprint=article.entity_fingerprint,
            topics=article.topics,
            is_volatile=article.is_volatile,
            partition=article.partition.value,
            status=article.status.value,
            story_id=article.story_id,
            similarity_score=article.similarity_score,
            stale=article.stale,
        )
        self._session.add(orm)
        await self._session.commit()
        return orm

    async def mark_stale(self, article_id: uuid.UUID, superseded_by: uuid.UUID) -> None:
        await self._session.execute(
            update(ArticleORM)
            .where(ArticleORM.id == article_id)
            .values(
                stale=True,
                stale_at=func.now(),
                superseded_by=superseded_by,
                status=ArticleStatus.STALE.value,
            )
        )
        await self._session.commit()

    async def get_by_fingerprint(
        self, fingerprint: str, exclude_stale: bool = True
    ) -> list[ArticleORM]:
        q = select(ArticleORM).where(ArticleORM.entity_fingerprint == fingerprint)
        if exclude_stale:
            q = q.where(ArticleORM.stale == False)  # noqa: E712
        result = await self._session.scalars(q)
        return list(result.all())

    async def assign_story(self, article_id: uuid.UUID, story_id: uuid.UUID) -> None:
        await self._session.execute(
            update(ArticleORM)
            .where(ArticleORM.id == article_id)
            .values(story_id=story_id, status=ArticleStatus.CLUSTERED.value)
        )
        await self._session.commit()


class StoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, fingerprint: str, topic: str) -> StoryORM:
        existing = await self._session.scalar(
            select(StoryORM).where(StoryORM.entity_fingerprint == fingerprint)
        )
        if existing:
            return existing

        story = StoryORM(entity_fingerprint=fingerprint, topic=topic)
        self._session.add(story)
        await self._session.commit()
        await self._session.refresh(story)
        return story

    async def update_latest(self, story_id: uuid.UUID, latest_article_id: uuid.UUID) -> None:
        await self._session.execute(
            update(StoryORM)
            .where(StoryORM.id == story_id)
            .values(latest_article_id=latest_article_id, updated_at=func.now())
        )
        await self._session.commit()
