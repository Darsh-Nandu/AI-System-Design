"""Immutable audit log -- writes to both Kafka and Postgres.

Kafka gives infinite retention and replay capability.
Postgres gives queryable history for the support dashboard.
"""

from __future__ import annotations

import orjson
from aiokafka import AIOKafkaProducer

from refund_agent.config import get_settings
from refund_agent.logging import get_logger
from refund_agent.models import AuditEntry
from refund_agent.storage.postgres import AsyncSessionFactory, AuditEntryORM

settings = get_settings()
logger = get_logger(__name__)

_producer: AIOKafkaProducer | None = None


async def _get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            acks="all",
            enable_idempotence=True,
        )
        await _producer.start()
    return _producer


class AuditLogger:
    async def log(self, entry: AuditEntry) -> None:
        try:
            await self._write_kafka(entry)
        except Exception:
            logger.warning("kafka_audit_failed", session_id=entry.session_id)

        try:
            await self._write_postgres(entry)
        except Exception:
            logger.exception("postgres_audit_failed", session_id=entry.session_id)

    async def _write_kafka(self, entry: AuditEntry) -> None:
        producer = await _get_producer()
        payload = orjson.dumps(entry.model_dump(mode="json"))
        await producer.send(
            settings.kafka_audit_topic,
            value=payload,
            key=entry.session_id.encode(),
        )

    async def _write_postgres(self, entry: AuditEntry) -> None:
        async with AsyncSessionFactory() as session:
            orm = AuditEntryORM(
                id=entry.id,
                session_id=entry.session_id,
                user_id=entry.user_id,
                action=entry.action,
                transaction_id=entry.transaction_id,
                amount=entry.amount,
                confidence_score=entry.confidence_score,
                evidence_type=entry.evidence_type,
                idempotency_key=entry.idempotency_key,
                agent_version=entry.agent_version,
                decision=entry.decision,
                metadata_=entry.metadata,
            )
            session.add(orm)
            await session.commit()
