"""SQLAlchemy 2.0 async models and session factory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from eval_pipeline.config import get_settings

settings = get_settings()

_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class LogEntryORM(Base):
    __tablename__ = "log_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text)
    old_model_output: Mapped[str] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(32), default="python")
    implicit_signals: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    test_cases: Mapped[list[Any]] = mapped_column(JSON, default=list)
    repo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    bug_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ground_truth_patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class EvalRunORM(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    suite_name: Mapped[str] = mapped_column(String(128))
    baseline_model: Mapped[str] = mapped_column(String(128))
    candidate_model: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class TaskResultORM(Base):
    __tablename__ = "task_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    log_entry_id: Mapped[str] = mapped_column(String(64))
    task_type: Mapped[str] = mapped_column(String(32))
    similarity_score: Mapped[float] = mapped_column(Float)
    filtered: Mapped[bool] = mapped_column(default=False)
    old_pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    old_judge_overall: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_judge_overall: Mapped[float | None] = mapped_column(Float, nullable=True)
    implicit_weight: Mapped[float] = mapped_column(Float, default=1.0)
    regression_flag: Mapped[bool] = mapped_column(default=False)
    improvement_flag: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


async def create_tables() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
