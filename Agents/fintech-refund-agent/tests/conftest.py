"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from refund_agent.models import (
    ConfidenceLevel,
    EscalationReason,
    EvidenceGrade,
    EvidenceSubmission,
    RefundStatus,
    Transaction,
)


@pytest.fixture
def user_id() -> str:
    return "user_test_123"


@pytest.fixture
def session_id() -> str:
    return f"sess_{uuid4().hex[:12]}"


@pytest.fixture
def sample_transactions(user_id: str) -> list[Transaction]:
    now = datetime.now(timezone.utc)
    return [
        Transaction(
            id=f"txn_000{i}",
            user_id=user_id,
            amount=Decimal(str(amount)),
            currency="USD",
            merchant=merchant,
            description=f"Order from {merchant}",
            created_at=now.replace(day=max(1, now.day - days_ago)),
            refunded=False,
            refund_eligible=True,
        )
        for i, (amount, merchant, days_ago) in enumerate([
            (49.99, "Zomato", 3),
            (129.00, "Myntra", 7),
            (15.50, "Swiggy", 1),
        ])
    ]


@pytest.fixture
def high_confidence_grade() -> EvidenceGrade:
    return EvidenceGrade(
        confidence_level=ConfidenceLevel.HIGH,
        confidence_score=0.92,
        reason="Duplicate charge confirmed in transaction DB",
        system_verifiable=True,
        requires_human=False,
    )


@pytest.fixture
def low_confidence_grade() -> EvidenceGrade:
    return EvidenceGrade(
        confidence_level=ConfidenceLevel.LOW,
        confidence_score=0.40,
        reason="Subjective quality complaint",
        system_verifiable=False,
        requires_human=True,
    )


@pytest.fixture
def evidence() -> EvidenceSubmission:
    return EvidenceSubmission(
        reason="Item never arrived",
        raw_text="I ordered 3 days ago and there is no delivery update.",
        attachments=[],
    )


@pytest.fixture
def base_state(user_id: str, session_id: str, sample_transactions: list[Transaction]) -> dict:
    return {
        "session_id": session_id,
        "user_id": user_id,
        "messages": [],
        "user_message": "refund everything from last month",
        "candidate_transactions": [t.model_dump() for t in sample_transactions],
        "confirmed_transaction_ids": [t.id for t in sample_transactions],
        "awaiting_confirmation": False,
        "velocity_count_24h": 0,
        "velocity_ok": True,
        "eligible_transactions": [t.model_dump() for t in sample_transactions],
        "ineligible_reasons": {},
        "evidence": None,
        "evidence_grade": None,
        "total_amount": Decimal("0"),
        "magnitude_ok": False,
        "idempotency_keys": {},
        "completed_refunds": [],
        "pending_transaction_ids": [],
        "failed_transaction_ids": [],
        "status": RefundStatus.PENDING_CONFIRMATION,
        "escalation_reason": None,
        "human_ticket_id": None,
        "next_prompt": "",
        "error": None,
    }


@pytest.fixture
def mock_redis() -> AsyncMock:
    mock = AsyncMock()
    mock.zremrangebyscore = AsyncMock(return_value=None)
    mock.zcard = AsyncMock(return_value=0)
    mock.zadd = AsyncMock(return_value=1)
    mock.expire = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=None)
    mock.setex = AsyncMock(return_value=True)
    mock.ping = AsyncMock(return_value=True)
    return mock
