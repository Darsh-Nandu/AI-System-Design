"""Human escalation queue service.

In production: integrate with Zendesk, Linear, or an internal ticketing system.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from refund_agent.logging import get_logger
from refund_agent.models import EscalationReason, Transaction
from refund_agent.storage.postgres import AsyncSessionFactory, EscalationTicketORM
from datetime import datetime, timezone

logger = get_logger(__name__)


class HumanQueueService:
    async def create_ticket(
        self,
        session_id: str,
        user_id: str,
        escalation_reason: EscalationReason,
        transactions: list[Transaction],
        confidence_score: float | None,
        evidence_summary: str,
    ) -> str:
        ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        total = sum(t.amount for t in transactions)
        txn_ids = [t.id for t in transactions]

        async with AsyncSessionFactory() as session:
            ticket = EscalationTicketORM(
                id=ticket_id,
                session_id=session_id,
                user_id=user_id,
                reason=escalation_reason.value,
                total_amount=total,
                transaction_ids=txn_ids,
                confidence_score=confidence_score,
                evidence_summary=evidence_summary,
                created_at=datetime.now(timezone.utc),
            )
            session.add(ticket)
            await session.commit()

        logger.info(
            "escalation_ticket_created",
            ticket_id=ticket_id,
            reason=escalation_reason.value,
            total=str(total),
        )
        return ticket_id
