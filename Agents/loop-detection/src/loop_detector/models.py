"""Domain models for the loop detection system."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class LoopSignalType(StrEnum):
    EXACT_DUPLICATE = "exact_duplicate"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NO_PROGRESS = "no_progress"
    TOOL_TIMEOUT = "tool_timeout"
    CAUSAL_CYCLE = "causal_cycle"
    MONITORING_FLAG = "monitoring_flag"


class RecoveryStrategy(StrEnum):
    INJECT_CORRECTION = "inject_correction"
    FORCE_SUMMARIZE = "force_summarize"
    HUMAN_CHECKPOINT = "human_checkpoint"


class LoopSignal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: str
    signal_type: LoopSignalType
    step: int
    tool_name: str | None = None
    tool_args_hash: str | None = None
    similarity_score: float | None = None
    message: str
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict = Field(default_factory=dict)


class DetectionResult(BaseModel):
    is_looping: bool
    signals: list[LoopSignal] = Field(default_factory=list)
    recommended_strategy: RecoveryStrategy | None = None
    consecutive_detections: int = 0
    step: int = 0


class ToolExecution(BaseModel):
    tool_name: str
    args: dict
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    result: str | None = None
    timed_out: bool = False
    error: str | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds() * 1000


class AgentStep(BaseModel):
    step: int
    tool_name: str
    tool_args: dict
    args_hash: str
    observation: str
    tokens_used: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HumanCheckpoint(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: str
    step: int
    consecutive_detections: int
    signals: list[LoopSignal]
    serialized_state: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_note: str | None = None


class SessionStats(BaseModel):
    session_id: str
    total_steps: int = 0
    total_tokens: int = 0
    loop_signals: int = 0
    consecutive_detections: int = 0
    recovery_strategy: RecoveryStrategy | None = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
