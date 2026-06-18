"""API request and response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from eval_pipeline.models import EvalStatus, EvalSummary, ShipDecision, TaskType


class StartEvalRequest(BaseModel):
    suite_name: str = Field(..., min_length=1)
    baseline_model: str
    candidate_model: str
    per_task_type: int = Field(default=100, ge=1, le=1000)


class EvalRunOut(BaseModel):
    id: str
    suite_name: str
    baseline_model: str
    candidate_model: str
    status: EvalStatus
    started_at: datetime | None
    finished_at: datetime | None
    summary: EvalSummary | None
    error: str | None


class TaskResultOut(BaseModel):
    log_entry_id: str
    task_type: TaskType
    similarity_score: float
    filtered: bool
    old_pass_rate: float | None
    new_pass_rate: float | None
    old_judge_overall: float | None
    new_judge_overall: float | None
    implicit_weight: float
    regression_flag: bool
    improvement_flag: bool


class HealthOut(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
