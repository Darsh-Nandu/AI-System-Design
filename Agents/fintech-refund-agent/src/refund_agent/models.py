"""Domain models for the refund agent."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4
from datetime import datetime

from pydantic import BaseModel, Field


class RefundStatus(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    VELOCITY_BLOCKED = "velocity_blocked"
    INELIGIBLE = "ineligible"
    PENDING_EVIDENCE = "pending_evidence"
    ESCALATED = "escalated"
    EXECUTING = "executing"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"


class EscalationReason(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    HIGH_AMOUNT = "high_amount"
    VELOCITY_EXCEEDED = "velocity_exceeded"
    SYSTEM_ERROR = "system_error"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Transaction(BaseModel):
    id: str
    user_id: str
    amount: Decimal
    currency: str = "USD"
    merchant: str
    description: str
    created_at: datetime
    refunded: bool = False
    refund_eligible: bool = True

    @property
    def age_days(self) -> int:
        return (datetime.utcnow() - self.created_at).days


class EvidenceSubmission(BaseModel):
    reason: str
    evidence_type: str = ""
    raw_text: str = ""
    attachments: list[str] = Field(default_factory=list)


class EvidenceGrade(BaseModel):
    confidence_level: ConfidenceLevel
    confidence_score: float
    reason: str
    system_verifiable: bool = False
    requires_human: bool = False


class RefundResult(BaseModel):
    transaction_id: str
    amount: Decimal
    currency: str
    idempotency_key: str
    status: str  # "success" | "failed" | "already_processed"
    gateway_reference: str = ""
    processed_at: datetime = Field(default_factory=datetime.utcnow)


class AuditEntry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    user_id: str
    action: str
    transaction_id: str | None = None
    amount: Decimal | None = None
    confidence_score: float | None = None
    evidence_type: str | None = None
    idempotency_key: str | None = None
    agent_version: str = "refund-agent-v0.1.0"
    decision: str = ""
    metadata: dict = Field(default_factory=dict)
