"""Unit tests for the eligibility gate node."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from refund_agent.agent.nodes.eligibility import _check_transaction
from refund_agent.models import RefundStatus, Transaction


def _make_txn(**kwargs) -> Transaction:
    defaults = {
        "id": "txn_test",
        "user_id": "user_test_123",
        "amount": Decimal("49.99"),
        "currency": "USD",
        "merchant": "Test Store",
        "description": "Test purchase",
        "created_at": datetime.now(timezone.utc) - timedelta(days=3),
        "refunded": False,
        "refund_eligible": True,
    }
    return Transaction(**{**defaults, **kwargs})


def test_eligible_transaction_passes():
    txn = _make_txn()
    assert _check_transaction(txn, "user_test_123") is None


def test_wrong_owner_rejected():
    txn = _make_txn()
    reason = _check_transaction(txn, "different_user")
    assert reason is not None
    assert "owned" in reason


def test_already_refunded_rejected():
    txn = _make_txn(refunded=True)
    reason = _check_transaction(txn, "user_test_123")
    assert reason is not None
    assert "refunded" in reason


def test_outside_window_rejected():
    old_date = datetime.now(timezone.utc) - timedelta(days=35)
    txn = _make_txn(created_at=old_date)
    reason = _check_transaction(txn, "user_test_123")
    assert reason is not None
    assert "window" in reason


def test_ineligible_product_rejected():
    txn = _make_txn(refund_eligible=False)
    reason = _check_transaction(txn, "user_test_123")
    assert reason is not None
    assert "eligible" in reason


@pytest.mark.asyncio
async def test_all_ineligible_returns_ineligible_status(base_state: dict):
    base_state["candidate_transactions"][0]["user_id"] = "wrong_user"
    base_state["candidate_transactions"][1]["user_id"] = "wrong_user"
    base_state["candidate_transactions"][2]["user_id"] = "wrong_user"

    with patch("refund_agent.agent.nodes.eligibility.TransactionService") as mock_svc:
        mock_svc.return_value.get_transaction = AsyncMock(return_value=None)
        from refund_agent.agent.nodes.eligibility import check_eligibility
        result = await check_eligibility(base_state)

    assert result["status"] == RefundStatus.INELIGIBLE
    assert result["eligible_transactions"] == []
