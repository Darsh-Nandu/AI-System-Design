"""Request and response schemas for the monitoring API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from loop_detector.models import LoopSignalType, RecoveryStrategy


class LoopSignalOut(BaseModel):
    signal_type: LoopSignalType
    session_id: str
    step_index: int
    description: str
    confidence: float
    metadata: dict[str, Any]
    detected_at: datetime


class SessionSummaryOut(BaseModel):
    session_id: str
    total_steps: int
    total_tokens: int
    loop_signals: int
    recovery_actions: int
    last_signal_type: LoopSignalType | None
    last_activity: datetime | None


class CheckpointOut(BaseModel):
    id: UUID
    session_id: str
    reason: str
    context: dict[str, Any]
    resolved: bool
    created_at: datetime
    resolved_at: datetime | None


class ResolveCheckpointRequest(BaseModel):
    resolution_note: str = Field(..., min_length=1, max_length=2048)


class HealthOut(BaseModel):
    status: str
    version: str = "1.0.0"
