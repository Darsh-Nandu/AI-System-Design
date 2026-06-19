"""Append-only security event log in PostgreSQL."""

from __future__ import annotations

import json
from datetime import datetime

import structlog
from sqlalchemy import String, DateTime, Text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from guardrails.config import get_settings
from guardrails.models import SecurityEvent, Severity, ThreatCategory

log = structlog.get_logger(__name__)

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


class SecurityEventORM(Base):
    __tablename__ = "security_events"
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    attack_type: Mapped[str] = mapped_column(String(64), index=True)
    layer_caught_by: Mapped[str] = mapped_column(String(64))
    original_input: Mapped[str] = mapped_column(Text)
    attempted_action: Mapped[str] = mapped_column(Text)
    injection_source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    action_taken: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), index=True)
    metadata_json: Mapped[str] = mapped_column(Text)


async def create_tables() -> None:
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def log_event(event: SecurityEvent) -> None:
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():
            orm = SecurityEventORM(
                event_id=event.event_id,
                timestamp=event.timestamp,
                session_id=event.session_id,
                user_id=event.user_id,
                attack_type=event.attack_type.value,
                layer_caught_by=event.layer_caught_by,
                original_input=event.original_input[:2000],
                attempted_action=event.attempted_action[:500],
                injection_source=event.injection_source,
                action_taken=event.action_taken,
                severity=event.severity.value,
                metadata_json=json.dumps(event.metadata, default=str),
            )
            session.add(orm)

    sev = event.severity
    log.info(
        "security_event_logged",
        event_id=event.event_id,
        severity=sev.value,
        attack_type=event.attack_type.value,
        layer=event.layer_caught_by,
    )

    if sev == Severity.CRITICAL:
        log.critical(
            "CRITICAL_SECURITY_EVENT",
            event_id=event.event_id,
            attack_type=event.attack_type.value,
            msg="Immediate security team alert required",
        )
    elif sev == Severity.HIGH:
        log.warning(
            "HIGH_SECURITY_EVENT",
            event_id=event.event_id,
            attack_type=event.attack_type.value,
        )


async def list_events(
    severity: str | None = None,
    attack_type: str | None = None,
    limit: int = 100,
) -> list[dict]:
    from sqlalchemy import select
    factory = get_session_factory()

    async with factory() as session:
        q = select(SecurityEventORM).order_by(SecurityEventORM.timestamp.desc()).limit(limit)
        if severity:
            q = q.where(SecurityEventORM.severity == severity.upper())
        if attack_type:
            q = q.where(SecurityEventORM.attack_type == attack_type)
        result = await session.execute(q)
        rows = result.scalars().all()

    return [
        {
            "event_id": r.event_id,
            "timestamp": r.timestamp.isoformat(),
            "severity": r.severity,
            "attack_type": r.attack_type,
            "layer_caught_by": r.layer_caught_by,
            "action_taken": r.action_taken,
            "session_id": r.session_id,
            "original_input_preview": r.original_input[:100] + "..." if len(r.original_input) > 100 else r.original_input,
        }
        for r in rows
    ]
