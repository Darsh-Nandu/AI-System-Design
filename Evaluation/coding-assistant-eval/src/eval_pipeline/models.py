"""Domain models for the coding assistant eval pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field


class TaskType(str, Enum):
    CODE_GENERATION = "code_generation"
    BUG_FIXING = "bug_fixing"
    CODE_EXPLANATION = "code_explanation"


class EvalStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ShipDecision(str, Enum):
    SHIP = "ship"
    HOLD = "hold"
    REVIEW = "review"


class ImplicitSignals(BaseModel):
    """User behaviour signals recorded alongside each production log entry."""

    copied: bool = False
    re_asked_within_60s: bool = False
    edit_distance_after_copy: float = Field(default=1.0, ge=0.0, le=1.0)
    thumbs_up: bool | None = None

    @computed_field
    @property
    def quality_weight(self) -> float:
        """Importance weight: how good was the old output?

        High weight -> divergence is a high-priority regression.
        Low weight  -> divergence may be an improvement.
        """
        if self.copied and self.edit_distance_after_copy < 0.1 and not self.re_asked_within_60s:
            return 1.0
        if self.thumbs_up is True:
            return 0.9
        if self.re_asked_within_60s or (not self.copied and self.thumbs_up is None):
            return 0.3
        return 0.6


class TestCase(BaseModel):
    """An input/output pair for execution-based code evaluation."""

    input_data: str
    expected_output: str
    timeout_seconds: float = 10.0


class LogEntry(BaseModel):
    """A single row in the production logs golden dataset."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    prompt: str
    old_model_output: str
    task_type: TaskType
    language: str = "python"
    implicit_signals: ImplicitSignals = Field(default_factory=ImplicitSignals)

    # Code generation fields
    test_cases: list[TestCase] = Field(default_factory=list)

    # Bug fixing fields
    repo_path: str | None = None
    bug_description: str | None = None
    ground_truth_patch: str | None = None

    # Code explanation fields
    reference_explanation: str | None = None
    raw_code: str | None = None


class JudgeScore(BaseModel):
    """Structured rubric score from the LLM judge (each dimension 0-3)."""

    correctness: float = Field(ge=0.0, le=3.0)
    clarity: float = Field(ge=0.0, le=3.0)
    completeness: float = Field(ge=0.0, le=3.0)
    reasoning: str = ""

    @computed_field
    @property
    def overall(self) -> float:
        return (self.correctness + self.clarity + self.completeness) / 9.0


class ExecutionResult(BaseModel):
    """Outcome of running code against a test suite."""

    passed: int = 0
    failed: int = 0
    errors: int = 0
    timeout: bool = False
    complexity_score: float | None = None

    @computed_field
    @property
    def pass_rate(self) -> float:
        total = self.passed + self.failed + self.errors
        return self.passed / total if total > 0 else 0.0


class TaskResult(BaseModel):
    """Full comparison record for a single log entry."""

    log_entry_id: str
    task_type: TaskType
    old_output: str
    new_output: str

    similarity_score: float
    filtered_by_similarity: bool = False

    old_execution: ExecutionResult | None = None
    new_execution: ExecutionResult | None = None

    old_judge_score: JudgeScore | None = None
    new_judge_score: JudgeScore | None = None

    implicit_weight: float = 1.0

    @computed_field
    @property
    def regression_flag(self) -> bool:
        if self.old_execution and self.new_execution:
            return self.new_execution.pass_rate < self.old_execution.pass_rate - 0.05
        if self.old_judge_score and self.new_judge_score:
            return self.new_judge_score.overall < self.old_judge_score.overall - 0.1
        return False

    @computed_field
    @property
    def improvement_flag(self) -> bool:
        if self.old_execution and self.new_execution:
            return self.new_execution.pass_rate > self.old_execution.pass_rate + 0.05
        if self.old_judge_score and self.new_judge_score:
            return self.new_judge_score.overall > self.old_judge_score.overall + 0.1
        return False


class EvalSummary(BaseModel):
    """Aggregate scorecard for one eval run."""

    total_entries: int = 0
    filtered_by_similarity: int = 0
    evaluated: int = 0

    code_gen_old_pass_rate: float = 0.0
    code_gen_new_pass_rate: float = 0.0

    bug_fix_old_pass_rate: float = 0.0
    bug_fix_new_pass_rate: float = 0.0

    explanation_old_score: float = 0.0
    explanation_new_score: float = 0.0

    regression_count: int = 0
    improvement_count: int = 0
    weighted_regression_score: float = 0.0

    ship_decision: ShipDecision = ShipDecision.REVIEW
    decision_reasons: list[str] = Field(default_factory=list)


class EvalRun(BaseModel):
    """A complete eval run comparing baseline vs candidate model."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    suite_name: str
    baseline_model: str
    candidate_model: str
    status: EvalStatus = EvalStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary: EvalSummary | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
