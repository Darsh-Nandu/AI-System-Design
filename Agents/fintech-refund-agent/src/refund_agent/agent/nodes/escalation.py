"""Escalation node.

Routes sessions to the human agent queue when:
- Evidence confidence is below threshold
- Total amount exceeds the auto-approve limit
- Velocity limit was exceeded (fraud flag)
"""

from __future__ import annotations

from refund_agent.agent.state import RefundSessionState
from refund_agent.config import get_settings
from refund_agent.logging import get_logger
from refund_agent.metrics import escalations_total
from refund_agent.models import AuditEntry, EscalationReason, EvidenceGrade, RefundStatus, Transaction
from refund_agent.services.escalation import HumanQueueService
from refund_agent.storage.audit_log import AuditLogger

settings = get_settings()
logger = get_logger(__name__)


async def escalate(state: RefundSessionState) -> RefundSessionState:
    """Create a human-queue ticket and update state."""
    session_id = state["session_id"]
    user_id = state["user_id"]
    reason = state.get("escalation_reason") or EscalationReason.LOW_CONFIDENCE

    eligible_raw = state.get("eligible_transactions") or []
    eligible = [Transaction(**t) for t in eligible_raw]
    total = sum(t.amount for t in eligible)

    grade_raw = state.get("evidence_grade")
    evidence_grade = EvidenceGrade(**grade_raw) if grade_raw else None
    evidence_obj = state.get("evidence")

    queue = HumanQueueService()
    ticket_id = await queue.create_ticket(
        session_id=session_id,
        user_id=user_id,
        escalation_reason=reason,
        transactions=eligible,
        confidence_score=evidence_grade.confidence_score if evidence_grade else None,
        evidence_summary=evidence_obj.get("reason", "") if evidence_obj else "",
    )

    audit = AuditLogger()
    await audit.log(AuditEntry(
        session_id=session_id,
        user_id=user_id,
        action="escalated_to_human",
        amount=total,
        confidence_score=evidence_grade.confidence_score if evidence_grade else None,
        evidence_type=evidence_obj.get("evidence_type") if evidence_obj else None,
        decision=f"escalated:{reason.value}",
        metadata={"ticket_id": ticket_id, "reason": reason.value},
    ))

    escalations_total.labels(reason=reason.value).inc()
    logger.info(
        "session_escalated",
        session_id=session_id,
        reason=reason.value,
        ticket_id=ticket_id,
        total=str(total),
    )

    sla_note = ""
    if reason == EscalationReason.VELOCITY_EXCEEDED:
        sla_note = " Our fraud prevention team will review this."
    else:
        sla_note = " You will hear back within 4 hours."

    return {
        **state,
        "status": RefundStatus.ESCALATED,
        "human_ticket_id": ticket_id,
        "next_prompt": (
            f"Your refund request has been escalated to our team (ticket #{ticket_id}).{sla_note}\n\n"
            f"Reason: {reason.value.replace('_', ' ')}"
        ),
    }
