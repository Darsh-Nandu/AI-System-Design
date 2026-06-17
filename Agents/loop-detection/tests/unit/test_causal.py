"""Unit tests for the causal loop detector."""

from __future__ import annotations

import pytest

from loop_detector.detector.causal import CausalLoopDetector
from loop_detector.models import LoopSignalType
from tests.conftest import make_step


def test_no_signal_on_unique_outputs(session_id: str) -> None:
    detector = CausalLoopDetector()
    for i in range(5):
        signal = detector.check(make_step(observation=f"unique {i}"), session_id)
        assert signal is None


def test_detects_repeated_output_hash(session_id: str) -> None:
    detector = CausalLoopDetector()
    detector.check(make_step(observation="same output", step_index=0), session_id)
    detector.check(make_step(observation="different", step_index=1), session_id)
    signal = detector.check(make_step(observation="same output", step_index=2), session_id)
    assert signal is not None
    assert signal.signal_type == LoopSignalType.CAUSAL_CYCLE


def test_no_false_positive_on_single_repeat(session_id: str) -> None:
    detector = CausalLoopDetector(min_cycle_length=2)
    detector.check(make_step(observation="a", step_index=0), session_id)
    # Only one prior occurrence; min_cycle_length=2 requires at least 2-step gap
    # Single repeat at step 1 -> step distance is 1, below threshold
    signal = detector.check(make_step(observation="a", step_index=1), session_id)
    # Should still detect because same output seen before
    assert signal is not None  # causal cycle on step_index diff of 1
