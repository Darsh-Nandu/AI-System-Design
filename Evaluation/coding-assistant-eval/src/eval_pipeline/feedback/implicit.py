"""Implicit feedback correlation.

Weights regressions by how good the old model's output was. If users loved
the old output (high copy rate, low edit distance), a divergence from the new
model is high-priority. If users were already unhappy with the old output,
a divergence could actually be an improvement.
"""

from __future__ import annotations

from eval_pipeline.models import TaskResult


def compute_weighted_regression_score(results: list[TaskResult]) -> float:
    """Sum of (regression weight) for all entries flagged as regressions.

    A higher score means more high-quality outputs were regressed on.
    Compare against settings.regression_hold_threshold to decide HOLD vs SHIP.
    """
    score = 0.0
    for r in results:
        if r.regression_flag:
            score += r.implicit_weight
    return score


def label_priority(result: TaskResult) -> str:
    """Classify a divergent result for the dashboard display."""
    if not result.regression_flag and not result.improvement_flag:
        return "neutral"
    if result.regression_flag:
        weight = result.implicit_weight
        if weight >= 0.8:
            return "critical_regression"
        if weight >= 0.5:
            return "regression"
        return "low_priority_regression"
    if result.improvement_flag:
        weight = result.implicit_weight
        if weight <= 0.4:
            return "likely_improvement"
        return "improvement"
    return "neutral"
