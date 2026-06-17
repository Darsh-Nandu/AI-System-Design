"""Unit tests for the progress tracker."""

from __future__ import annotations

import pytest

from loop_detector.detector.progress import ProgressTracker
from loop_detector.models import LoopSignalType
from tests.conftest import make_step


def test_no_signal_with_novel_observations(session_id: str) -> None:
    tracker = ProgressTracker(window=3, novelty_threshold=0.05)
    for i in range(5):
        signal = tracker.check(make_step(observation=f"unique result {i}"), session_id)
        assert signal is None


def test_detects_stagnation_on_repeated_observations(session_id: str) -> None:
    tracker = ProgressTracker(window=3, novelty_threshold=0.05)
    repeated = make_step(observation="same result every time")
    for _ in range(4):
        tracker.check(repeated, session_id)
    signal = tracker.check(repeated, session_id)
    assert signal is not None
    assert signal.signal_type == LoopSignalType.NO_PROGRESS


def test_mixed_observations_dont_trigger(session_id: str) -> None:
    tracker = ProgressTracker(window=3, novelty_threshold=0.05)
    tracker.check(make_step(observation="result a"), session_id)
    tracker.check(make_step(observation="result a"), session_id)
    signal = tracker.check(make_step(observation="new discovery xyz"), session_id)
    assert signal is None
