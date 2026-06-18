"""PostgreSQL storage for patient registry, ingestion records, and audit metadata."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, DateTime, Text, Boolean, Integer, Float
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from medical_rag.config import get_settings

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        cfg = get_settings()
        _engine = create_async_engine(cfg.database_url, echo=False, pool_size=5)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory


class Base(DeclarativeBase):
    pass


class PatientORM(Base):
    __tablename__ = "patients"
    patient_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finding_count: Mapped[int] = mapped_column(Integer, default=0)


class IngestionRecordORM(Base):
    __tablename__ = "ingestion_records"
    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), index=True)
    modality: Mapped[str] = mapped_column(String(32))
    source_document: Mapped[str] = mapped_column(String(256))
    finding_date: Mapped[str] = mapped_column(String(16))
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    pii_integrity_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence: Mapped[float] = mapped_column(Float)


class QueryRecordORM(Base):
    __tablename__ = "query_records"
    query_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), index=True)
    requester_id: Mapped[str] = mapped_column(String(64))
    query_text: Mapped[str] = mapped_column(Text)
    faithfulness_score: Mapped[float] = mapped_column(Float)
    queried_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def create_tables() -> None:
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
