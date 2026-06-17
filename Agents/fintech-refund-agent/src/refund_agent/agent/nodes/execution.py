"""Execution node.

Fires refunds one transaction at a time with idempotency keys.
Checkpoints state after each success so crashes are recoverable.
No transaction is ever processed twice.
"""

from __future__ import annotations

import hashlib

from refund_agent.agent.state import RefundSessionState
from refund_agent.config import get_settings
from refund_agent.logging import get_logger
from refund_agent.metrics import refunds_executed_total
from refund_agent.models import AuditEntry, RefundResult, RefundStatus, Transaction
from refund_agent.services.payments import PaymentGateway
from refund_agent.storage.audit_log import AuditLogger
from refund_agent.storage.redis_client import get_redis

settings = get_settings()
logger = get_logger(__name__)


def _make_idempotency_key(user_id: str, txn_id: str, session_id: str) -> str:
    """Deterministic key: same inputs always produce the same key.

    This is the crash-safety guarantee: a retry generates the same key,
    and the payment API deduplicates on it.
    """
    raw = f"{user_id}:{txn_id}:{session_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _checkpoint(state: RefundSessionState, redis_key: str) -> None:
    """Persist session progress so we can resume after a crash."""
    import orjson

    redis = await get_redis()
    payload = {
        "completed": [r["transaction_id"] for r in state["completed_refunds"]],
        "pending": state["pending_transaction_ids"],
        "failed": state["failed_transaction_ids"],
    }
    await redis.setex(redis_key, 86_400, orjson.dumps(payload))


async def execute_refunds(state: RefundSessionState) -> RefundSessionState:
    """Execute refunds one at a time, checkpointing after each success."""
    session_id = state["session_id"]
    user_id = state["user_id"]
    eligible: list[Transaction] = [Transaction(**t) for t in state["eligible_transactions"]]
    checkpoint_key = f"checkpoint:{session_id}"

    redis = await get_redis()
    gateway = PaymentGateway()
    audit = AuditLogger()

    completed: list[RefundResult] = list(state.get("completed_refunds") or [])
    completed_ids = {r["transaction_id"] for r in completed}
    failed_ids: list[str] = list(state.get("failed_transaction_ids") or [])
    idempotency_keys: dict[str, str] = dict(state.get("idempotency_keys") or {})

    pending = [t for t in eligible if t.id not in completed_ids and t.id not in failed_ids]

    logger.info(
        "execution_start",
        session_id=session_id,
        total=len(eligible),
        already_done=len(completed_ids),
        pending=len(pending),
    )

    for txn in pending:
        idem_key = _make_idempotency_key(user_id, txn.id, session_id)
        idempotency_keys[txn.id] = idem_key

        try:
            result = await gateway.refund(
                transaction_id=txn.id,
                amount=txn.amount,
                currency=txn.currency,
                idempotency_key=idem_key,
            )

            completed.append(result)
            completed_ids.add(txn.id)

            evidence_grade = state.get("evidence_grade") or {}
            evidence_obj = state.get("evidence") or {}

            await audit.log(AuditEntry(
                session_id=session_id,
                user_id=user_id,
                action="refund_executed",
                transaction_id=txn.id,
                amount=txn.amount,
                confidence_score=evidence_grade.get("confidence_score"),
                evidence_type=evidence_obj.get("evidence_type"),
                idempotency_key=idem_key,
                decision="auto_approved",
                metadata={"gateway_ref": result.gateway_reference},
            ))

            refunds_executed_total.labels(status="success").inc()
            logger.info("refund_success", txn_id=txn.id, amount=str(txn.amount), key=idem_key)

        except Exception as exc:
            failed_ids.append(txn.id)
            refunds_executed_total.labels(status="failed").inc()
            logger.error("refund_failed", txn_id=txn.id, error=str(exc))

        # Checkpoint after every transaction
        pending_remaining = [t.id for t in eligible if t.id not in completed_ids and t.id not in failed_ids]
        await _checkpoint(
            {**state, "completed_refunds": [r.model_dump() for r in completed],
             "pending_transaction_ids": pending_remaining,
             "failed_transaction_ids": failed_ids},
            checkpoint_key,
        )

    # Compose confirmation message
    success_count = len(completed) - len(completed_ids.intersection(
        {r["transaction_id"] for r in state.get("completed_refunds") or []}
    ))
    total_refunded = sum(r["amount"] for r in completed)
    lines = "\n".join(
        f"  {r['transaction_id'][-6:]} -- ${r['amount']:.2f} -- {r['status']}"
        for r in completed
    )
    fail_note = f"\n\n{len(failed_ids)} refund(s) failed and have been queued for manual review." if failed_ids else ""

    final_status = (
        RefundStatus.COMPLETED if not failed_ids
        else RefundStatus.PARTIALLY_COMPLETED
    )

    return {
        **state,
        "completed_refunds": [r.model_dump() if hasattr(r, "model_dump") else r for r in completed],
        "pending_transaction_ids": [],
        "failed_transaction_ids": failed_ids,
        "idempotency_keys": idempotency_keys,
        "status": final_status,
        "next_prompt": (
            f"Refunds processed successfully:\n{lines}\n\n"
            f"Total refunded: ${total_refunded:.2f}{fail_note}"
        ),
    }
