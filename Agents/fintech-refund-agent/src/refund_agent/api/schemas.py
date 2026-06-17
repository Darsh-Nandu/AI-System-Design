"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Authenticated user ID")
    session_id: str | None = Field(None, description="Resume an existing session")
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    session_id: str
    message: str
    status: str
    awaiting_input: bool = False


class ConfirmRequest(BaseModel):
    session_id: str
    user_id: str
    selection: str = Field(..., description="'all', '1,2,3', or a comma-separated list of indices")


class EvidenceRequest(BaseModel):
    session_id: str
    user_id: str
    reason: str = Field(..., min_length=5)
    details: str = ""
    attachments: list[str] = Field(default_factory=list)


class SessionStatusResponse(BaseModel):
    session_id: str
    user_id: str
    status: str
    total_refunded: Decimal | None = None
    completed_count: int = 0
    human_ticket_id: str | None = None
    created_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict[str, str]


class AuditEntryResponse(BaseModel):
    id: UUID
    timestamp: datetime
    action: str
    transaction_id: str | None
    amount: Decimal | None
    confidence_score: float | None
    decision: str
