"""Unit tests for the velocity check node."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from refund_agent.models import EscalationReason, RefundStatus


@pytest.mark.asyncio
async def test_velocity_passes_under_limit(base_state: dict, mock_redis: AsyncMock):
    mock_redis.zcard.return_value = 2

    with patch("refund_agent.agent.nodes.velocity.get_redis", return_value=AsyncMock(return_value=mock_redis)):
        from refund_agent.agent.nodes.velocity import check_velocity
        with patch("refund_agent.agent.nodes.velocity.get_redis", new=AsyncMock(return_value=mock_redis)):
            result = await check_velocity(base_state)

    assert result["velocity_ok"] is True
    assert result["velocity_count_24h"] == 3


@pytest.mark.asyncio
async def test_velocity_blocks_at_limit(base_state: dict, mock_redis: AsyncMock):
    mock_redis.zcard.return_value = 5  # at the limit (max_refunds_per_24h = 5)

    with patch("refund_agent.agent.nodes.velocity.get_redis", new=AsyncMock(return_value=mock_redis)):
        from refund_agent.agent.nodes.velocity import check_velocity
        result = await check_velocity(base_state)

    assert result["velocity_ok"] is False
    assert result["status"] == RefundStatus.VELOCITY_BLOCKED
    assert result["escalation_reason"] == EscalationReason.VELOCITY_EXCEEDED


@pytest.mark.asyncio
async def test_velocity_message_mentions_limit(base_state: dict, mock_redis: AsyncMock):
    mock_redis.zcard.return_value = 10

    with patch("refund_agent.agent.nodes.velocity.get_redis", new=AsyncMock(return_value=mock_redis)):
        from refund_agent.agent.nodes.velocity import check_velocity
        result = await check_velocity(base_state)

    assert "maximum" in result["next_prompt"].lower()
