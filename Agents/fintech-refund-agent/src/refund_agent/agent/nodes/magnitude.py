"""Magnitude check node.

Even if confidence score is 1.0, if the total refund amount exceeds the
configured threshold, escalate to a human agent.
This gate is independent of confidence -- it catches high-value fraud
that might have good-looking evidence.
"""

from __future__ import annotations

from decimal import Decimal

from refund_agent.agent.state import RefundSessionState
from refund_agent.config import get_settings
from refund_agent.logging import get_logger
from refund_agent.metrics import magnitude_checks_total
from refund_agent.models import EscalationReason, RefundStatus, Transaction

settings = get_settings()
logger = get_logger(__name__)


async def check_magnitude(state: RefundSessionState) -> RefundSessionState:
    """Block auto-execution if total refund amount exceeds the configured limit."""
    eligible: list[Transaction] = [Transaction(**t) for t in state["eligible_transactions"]]
    total = sum(t.amount for t in eligible)

    if total > settings.max_auto_refund_amount:
        logger.info(
            "magnitude_check_failed",
            session_id=state["session_id"],
            total=str(total),
            threshold=str(settings.max_auto_refund_amount),
        )
        magnitude_checks_total.labels(result="escalated").inc()
        return {
            **state,
            "total_amount": total,
            "magnitude_ok": False,
            "status": RefundStatus.ESCALATED,
            "escalation_reason": EscalationReason.HIGH_AMOUNT,
            "next_prompt": (
                f"The total refund amount of ${total:.2f} exceeds the automatic approval "
                f"limit of ${settings.max_auto_refund_amount:.2f}. Your request has been "
                "sent to our team for review. You will be contacted within 4 hours."
            ),
        }

    magnitude_checks_total.labels(result="ok").inc()
    logger.info("magnitude_check_passed", total=str(total))

    return {
        **state,
        "total_amount": total,
        "magnitude_ok": True,
    }
