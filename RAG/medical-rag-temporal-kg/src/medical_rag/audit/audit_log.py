"""Append-only SHA256 hash-chained audit log for HIPAA compliance.

Each entry hashes the content of the previous entry.
Any tampering breaks the hash chain and is detectable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import String, DateTime, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from medical_rag.storage.postgres import Base, get_session_factory

log = structlog.get_logger(__name__)


class AuditEntryORM(Base):
    __tablename__ = "audit_log"
    entry_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sequence: Mapped[int] = mapped_column()
    event_type: Mapped[str] = mapped_column(String(64))
    patient_id: Mapped[str] = mapped_column(String(64), index=True)
    requester_id: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))
    chain_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _content_hash(entry_data: dict[str, Any]) -> str:
    serialized = json.dumps(entry_data, sort_keys=True, default=str)
    return _sha256(serialized)


def _chain_hash(content_hash: str, prev_hash: str) -> str:
    return _sha256(content_hash + prev_hash)


class AuditLogger:
    GENESIS_HASH = "0" * 64

    async def _get_last_entry(self, session: AsyncSession) -> AuditEntryORM | None:
        from sqlalchemy import select
        result = await session.execute(
            select(AuditEntryORM).order_by(AuditEntryORM.sequence.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def append(
        self,
        event_type: str,
        patient_id: str,
        requester_id: str,
        payload: dict[str, Any],
    ) -> str:
        import uuid
        factory = get_session_factory()
        async with factory() as session:
            async with session.begin():
                last = await self._get_last_entry(session)
                seq = (last.sequence + 1) if last else 1
                prev_hash = last.chain_hash if last else self.GENESIS_HASH

                entry_id = str(uuid.uuid4())
                entry_data = {
                    "entry_id": entry_id,
                    "sequence": seq,
                    "event_type": event_type,
                    "patient_id": patient_id,
                    "requester_id": requester_id,
                    "payload": payload,
                }
                c_hash = _content_hash(entry_data)
                ch = _chain_hash(c_hash, prev_hash)

                entry = AuditEntryORM(
                    entry_id=entry_id,
                    sequence=seq,
                    event_type=event_type,
                    patient_id=patient_id,
                    requester_id=requester_id,
                    payload_json=json.dumps(payload, default=str),
                    content_hash=c_hash,
                    prev_hash=prev_hash,
                    chain_hash=ch,
                )
                session.add(entry)

        log.info("audit_appended", entry_id=entry_id, seq=seq, event=event_type, patient=patient_id)
        return entry_id

    async def verify_chain(self, limit: int = 1000) -> tuple[bool, list[str]]:
        """Verify the integrity of the audit chain. Returns (ok, violations)."""
        from sqlalchemy import select
        factory = get_session_factory()
        violations: list[str] = []
        prev_chain_hash = self.GENESIS_HASH

        async with factory() as session:
            result = await session.execute(
                select(AuditEntryORM).order_by(AuditEntryORM.sequence.asc()).limit(limit)
            )
            entries = result.scalars().all()

        for entry in entries:
            entry_data = {
                "entry_id": entry.entry_id,
                "sequence": entry.sequence,
                "event_type": entry.event_type,
                "patient_id": entry.patient_id,
                "requester_id": entry.requester_id,
                "payload": json.loads(entry.payload_json),
            }
            expected_c_hash = _content_hash(entry_data)
            expected_chain = _chain_hash(expected_c_hash, prev_chain_hash)

            if entry.content_hash != expected_c_hash:
                violations.append(f"Content hash mismatch at seq {entry.sequence}")
            if entry.chain_hash != expected_chain:
                violations.append(f"Chain hash broken at seq {entry.sequence}")
            if entry.prev_hash != prev_chain_hash:
                violations.append(f"Prev hash mismatch at seq {entry.sequence}")

            prev_chain_hash = entry.chain_hash

        return len(violations) == 0, violations

    async def list_entries(
        self, patient_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        from sqlalchemy import select
        factory = get_session_factory()

        async with factory() as session:
            q = select(AuditEntryORM).order_by(AuditEntryORM.sequence.desc()).limit(limit)
            if patient_id:
                q = q.where(AuditEntryORM.patient_id == patient_id)
            result = await session.execute(q)
            entries = result.scalars().all()

        return [
            {
                "entry_id": e.entry_id,
                "sequence": e.sequence,
                "event_type": e.event_type,
                "patient_id": e.patient_id,
                "requester_id": e.requester_id,
                "chain_hash": e.chain_hash[:16] + "...",
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ]


_audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    return _audit_logger
