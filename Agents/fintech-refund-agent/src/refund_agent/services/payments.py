"""Payment gateway service.

Simulates a Stripe / Razorpay-compatible API with idempotency key support.
In production: replace the mock with a real Stripe SDK call.
The idempotency_key is the crash-safety mechanism: if the same key is
submitted twice, the second call returns the first result without charging again.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime

from refund_agent.logging import get_logger
from refund_agent.models import RefundResult
from refund_agent.storage.redis_client import get_redis

logger = get_logger(__name__)

_PROCESSED_KEY_PREFIX = "idem:"


class PaymentGateway:
    """Stripe-compatible idempotent refund executor."""

    async def refund(
        self,
        transaction_id: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> RefundResult:
        redis = await get_redis()
        cache_key = f"{_PROCESSED_KEY_PREFIX}{idempotency_key}"

        # Check if this key was already processed
        existing = await redis.get(cache_key)
        if existing:
            logger.info("idempotency_hit", key=idempotency_key, txn_id=transaction_id)
            import orjson
            data = orjson.loads(existing)
            return RefundResult(**data)

        # In production: await stripe.Refund.create(..., idempotency_key=idempotency_key)
        gateway_ref = f"re_{uuid.uuid4().hex[:16]}"

        result = RefundResult(
            transaction_id=transaction_id,
            amount=amount,
            currency=currency,
            idempotency_key=idempotency_key,
            status="success",
            gateway_reference=gateway_ref,
            processed_at=datetime.utcnow(),
        )

        import orjson
        await redis.setex(cache_key, 86_400 * 7, orjson.dumps(result.model_dump(mode="json")))

        logger.info(
            "refund_gateway_success",
            txn_id=transaction_id,
            amount=str(amount),
            gateway_ref=gateway_ref,
            key=idempotency_key,
        )
        return result
