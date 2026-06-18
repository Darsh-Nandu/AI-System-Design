"""Unit tests for the ship/hold/review decision logic."""

from __future__ import annotations

from eval_pipeline.models import EvalSummary, ShipDecision
from eval_pipeline.pipeline.orchestrator import _make_decision


def _summary(**kwargs) -> EvalSummary:
    defaults = dict(
        code_gen_old_pass_rate=0.80,
        code_gen_new_pass_rate=0.80,
        bug_fix_old_pass_rate=0.70,
        bug_fix_new_pass_rate=0.70,
        explanation_old_score=0.60,
        explanation_new_score=0.60,
        weighted_regression_score=0.0,
    )
    defaults.update(kwargs)
    return EvalSummary(**defaults)


def test_no_regression_ships() -> None:
    decision, _ = _make_decision(_summary())
    assert decision == ShipDecision.SHIP


def test_code_gen_drop_holds() -> None:
    decision, reasons = _make_decision(_summary(code_gen_new_pass_rate=0.70))
    assert decision == ShipDecision.HOLD
    assert any("Code gen" in r for r in reasons)


def test_bug_fix_drop_holds() -> None:
    decision, reasons = _make_decision(_summary(bug_fix_new_pass_rate=0.55))
    assert decision == ShipDecision.HOLD
    assert any("Bug fix" in r for r in reasons)


def test_explanation_drop_holds() -> None:
    decision, reasons = _make_decision(_summary(explanation_new_score=0.20))
    assert decision == ShipDecision.HOLD
    assert any("Explanation" in r for r in reasons)


def test_high_weighted_regression_holds() -> None:
    decision, reasons = _make_decision(_summary(weighted_regression_score=10.0))
    assert decision == ShipDecision.HOLD
    assert any("Weighted" in r for r in reasons)


def test_small_improvements_ship() -> None:
    decision, _ = _make_decision(
        _summary(
            code_gen_new_pass_rate=0.85,
            bug_fix_new_pass_rate=0.75,
            explanation_new_score=0.70,
        )
    )
    assert decision == ShipDecision.SHIP
