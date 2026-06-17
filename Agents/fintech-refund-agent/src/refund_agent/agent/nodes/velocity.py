"""Velocity check node.

Enforces a sliding-window rate limit via Redis.
Exceeding the limit flags the session for the fraud team.
"""

from __future__ import annotations

import time

from refund_agent.agent.state import RefundSessionState
from refund_agent.config import get_settings
from refund_agent.logging import get_logger
from refund_agent.metrics import velocity_checks_total
from refund_agent.models import EscalationReason, RefundStatus
from refund_agent.storage.redis_client import get_redis

settings = get_settings()
logger = get_logger(__name__)

_WINDOW_SECONDS = 86_400  # 24 hours


async def check_velocity(state: RefundSessionState) -> RefundSessionState:
    """Sliding-window rate limit: max N refund sessions per user per 24h."""
    user_id = state["user_id"]
    session_id = state["session_id"]
    key = f"velocity:{user_id}"

    redis = await get_redis()
    now = int(time.time())
    cutoff = now - _WINDOW_SECONDS

    # Sorted set: member=session_id, score=timestamp
    await redis.zremrangebyscore(key, "-inf", cutoff)
    count = await redis.zcard(key)

    if count >= settings.max_refunds_per_24h:
        logger.warning(
            "velocity_limit_exceeded",
            user_id=user_id,
            count=count,
            limit=settings.max_refunds_per_24h,
        )
        velocity_checks_total.labels(result="blocked").inc()
        return {
            **state,
            "velocity_count_24h": count,
            "velocity_ok": False,
            "status": RefundStatus.VELOCITY_BLOCKED,
            "escalation_reason": EscalationReason.VELOCITY_EXCEEDED,
            "next_prompt": (
                f"Your account has reached the maximum of {settings.max_refunds_per_24h} "
                "refund requests in the last 24 hours. Your request has been flagged for "
                "review and our team will contact you shortly."
            ),
        }

    # Record this session in the window
    await redis.zadd(key, {session_id: now})
    await redis.expire(key, _WINDOW_SECONDS)

    velocity_checks_total.labels(result="ok").inc()
    logger.info("velocity_check_passed", user_id=user_id, count=count + 1)

    return {
        **state,
        "velocity_count_24h": count + 1,
        "velocity_ok": True,
    }
