"""Eligibility gate node.

Rule-based checks per transaction before any evidence is requested.
Checks: user ownership, refund window, already refunded, product type.
"""

from __future__ import annotations

from datetime import datetime, timezone

from refund_agent.agent.state import RefundSessionState
from refund_agent.config import get_settings
from refund_agent.logging import get_logger
from refund_agent.metrics import eligibility_checks_total
from refund_agent.models import RefundStatus, Transaction
from refund_agent.services.transactions import TransactionService

settings = get_settings()
logger = get_logger(__name__)


async def check_eligibility(state: RefundSessionState) -> RefundSessionState:
    """Filter confirmed transactions to only those eligible for refund."""
    session_id = state["session_id"]
    user_id = state["user_id"]
    confirmed_ids = state["confirmed_transaction_ids"]
    candidates: list[Transaction] = [Transaction(**t) for t in state["candidate_transactions"]]

    # Filter to only confirmed ones
    confirmed = {t.id: t for t in candidates if t.id in confirmed_ids}

    txn_service = TransactionService()
    eligible: list[Transaction] = []
    ineligible: dict[str, str] = {}

    for txn_id, txn in confirmed.items():
        reason = _check_transaction(txn, user_id)
        if reason:
            ineligible[txn_id] = reason
            eligibility_checks_total.labels(result="ineligible").inc()
            logger.info("transaction_ineligible", txn_id=txn_id, reason=reason)
        else:
            # Double-check refund status in DB (authoritative source)
            latest = await txn_service.get_transaction(txn_id)
            if latest and latest.refunded:
                ineligible[txn_id] = "already refunded"
                eligibility_checks_total.labels(result="already_refunded").inc()
            else:
                eligible.append(txn)
                eligibility_checks_total.labels(result="eligible").inc()

    if not eligible:
        reasons_text = "\n".join(
            f"- #{txn_id[-6:]}: {reason}" for txn_id, reason in ineligible.items()
        )
        return {
            **state,
            "eligible_transactions": [],
            "ineligible_reasons": ineligible,
            "status": RefundStatus.INELIGIBLE,
            "next_prompt": f"None of the selected transactions are eligible for refund:\n{reasons_text}",
        }

    ineligible_text = ""
    if ineligible:
        ineligible_text = (
            "\n\nNote: The following were excluded: "
            + ", ".join(f"#{i[-6:]}" for i in ineligible)
        )

    logger.info(
        "eligibility_complete",
        session_id=session_id,
        eligible=len(eligible),
        ineligible=len(ineligible),
    )

    return {
        **state,
        "eligible_transactions": [t.model_dump() for t in eligible],
        "ineligible_reasons": ineligible,
        "next_prompt": (
            f"{len(eligible)} transaction(s) are eligible for refund. "
            f"Please describe the reason for your refund request.{ineligible_text}"
        ),
    }


def _check_transaction(txn: Transaction, user_id: str) -> str | None:
    """Return a rejection reason string, or None if eligible."""
    if txn.user_id != user_id:
        return "not owned by this account"

    if txn.refunded:
        return "already refunded"

    if not txn.refund_eligible:
        return "product type not eligible for refund"

    if txn.age_days > settings.refund_window_days:
        return f"outside {settings.refund_window_days}-day refund window"

    return None
