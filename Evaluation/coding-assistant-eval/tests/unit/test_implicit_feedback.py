"""Unit tests for implicit feedback weighting."""

from __future__ import annotations

from eval_pipeline.feedback.implicit import compute_weighted_regression_score, label_priority
from eval_pipeline.models import ExecutionResult, ImplicitSignals, LogEntry, TaskResult, TaskType


def _make_result(
    regression: bool,
    improvement: bool,
    implicit_weight: float,
) -> TaskResult:
    old_exec = ExecutionResult(passed=1 if not regression else 1)
    new_exec = ExecutionResult(passed=0 if regression else 1)
    return TaskResult(
        log_entry_id="x",
        task_type=TaskType.CODE_GENERATION,
        old_output="",
        new_output="",
        similarity_score=0.5,
        old_execution=old_exec,
        new_execution=new_exec,
        implicit_weight=implicit_weight,
    )


def test_quality_weight_high_for_beloved_output() -> None:
    signals = ImplicitSignals(copied=True, edit_distance_after_copy=0.0, re_asked_within_60s=False)
    assert signals.quality_weight == 1.0


def test_quality_weight_low_for_unsatisfied_user() -> None:
    signals = ImplicitSignals(copied=False, re_asked_within_60s=True)
    assert signals.quality_weight == 0.3


def test_weighted_regression_score_sums_weights() -> None:
    results = [
        _make_result(regression=True, improvement=False, implicit_weight=1.0),
        _make_result(regression=True, improvement=False, implicit_weight=0.3),
        _make_result(regression=False, improvement=True, implicit_weight=1.0),
    ]
    score = compute_weighted_regression_score(results)
    assert abs(score - 1.3) < 0.01


def test_label_priority_critical_regression() -> None:
    r = _make_result(regression=True, improvement=False, implicit_weight=0.9)
    assert label_priority(r) == "critical_regression"


def test_label_priority_likely_improvement() -> None:
    r = _make_result(regression=False, improvement=True, implicit_weight=0.3)
    assert label_priority(r) == "likely_improvement"
