"""Unit tests for the magnitude check node."""

from __future__ import annotations

from decimal import Decimal

import pytest

from refund_agent.agent.nodes.magnitude import check_magnitude
from refund_agent.models import EscalationReason, RefundStatus


@pytest.mark.asyncio
async def test_magnitude_passes_under_threshold(base_state: dict):
    # Total is 49.99 + 129.00 + 15.50 = 194.49, under the $500 default
    result = await check_magnitude(base_state)
    assert result["magnitude_ok"] is True
    assert result["total_amount"] == Decimal("194.49")


@pytest.mark.asyncio
async def test_magnitude_escalates_over_threshold(base_state: dict, sample_transactions):
    # Inflate amount to exceed threshold
    big_txn = sample_transactions[0].model_copy(update={"amount": Decimal("600.00")})
    base_state["eligible_transactions"] = [big_txn.model_dump()]

    result = await check_magnitude(base_state)
    assert result["magnitude_ok"] is False
    assert result["status"] == RefundStatus.ESCALATED
    assert result["escalation_reason"] == EscalationReason.HIGH_AMOUNT


@pytest.mark.asyncio
async def test_magnitude_escalation_message_contains_amount(base_state: dict, sample_transactions):
    big_txn = sample_transactions[0].model_copy(update={"amount": Decimal("999.00")})
    base_state["eligible_transactions"] = [big_txn.model_dump()]

    result = await check_magnitude(base_state)
    assert "999" in result["next_prompt"] or "500" in result["next_prompt"]


@pytest.mark.asyncio
async def test_magnitude_exactly_at_threshold_passes(base_state: dict, sample_transactions):
    exact_txn = sample_transactions[0].model_copy(update={"amount": Decimal("500.00")})
    base_state["eligible_transactions"] = [exact_txn.model_dump()]

    result = await check_magnitude(base_state)
    assert result["magnitude_ok"] is True
