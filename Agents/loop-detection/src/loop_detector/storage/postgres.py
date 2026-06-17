"""PostgreSQL ORM -- SQLAlchemy 2.0 async."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from loop_detector.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


class LoopSignalORM(Base):
    __tablename__ = "loop_signals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_args_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class HumanCheckpointORM(Base):
    __tablename__ = "human_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_detections: Mapped[int] = mapped_column(Integer, default=0)
    signal_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    serialized_state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SessionStatsORM(Base):
    __tablename__ = "session_stats"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    loop_signals: Mapped[int] = mapped_column(Integer, default=0)
    recovery_strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


_engine = create_async_engine(
    settings.postgres_dsn,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
)

AsyncSessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session


async def create_tables() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
