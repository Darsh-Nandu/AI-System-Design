"""Unit tests for the budget tracker."""

from __future__ import annotations

import pytest

from loop_detector.detector.budget import BudgetTracker
from loop_detector.models import LoopSignalType
from tests.conftest import make_step


def test_no_signal_within_budget(session_id: str) -> None:
    tracker = BudgetTracker(max_steps=10, max_tokens=1000)
    step = make_step(tokens=50)
    signal = tracker.check(step, session_id)
    assert signal is None


def test_step_budget_exhaustion(session_id: str) -> None:
    tracker = BudgetTracker(max_steps=3, max_tokens=10_000)
    for i in range(3):
        tracker.check(make_step(step_index=i, tokens=10), session_id)
    signal = tracker.check(make_step(step_index=3, tokens=10), session_id)
    assert signal is not None
    assert signal.signal_type == LoopSignalType.BUDGET_EXHAUSTED
    assert "steps" in signal.description


def test_token_budget_exhaustion(session_id: str) -> None:
    tracker = BudgetTracker(max_steps=100, max_tokens=100)
    signal = tracker.check(make_step(tokens=200), session_id)
    assert signal is not None
    assert signal.signal_type == LoopSignalType.BUDGET_EXHAUSTED
    assert "tokens" in signal.description


def test_step_count_increments(session_id: str) -> None:
    tracker = BudgetTracker(max_steps=10, max_tokens=10_000)
    for i in range(5):
        tracker.check(make_step(step_index=i, tokens=10), session_id)
    assert tracker.steps == 5
    assert tracker.tokens == 50
