"""Unit tests for the correction injection recovery."""

from __future__ import annotations

import pytest

from loop_detector.models import LoopSignal, LoopSignalType
from loop_detector.recovery.injection import build_correction_message


def _signal(signal_type: LoopSignalType) -> LoopSignal:
    return LoopSignal(
        signal_type=signal_type,
        session_id="test-session",
        step_index=5,
        description="test",
        confidence=0.9,
    )


def test_correction_for_exact_repeat() -> None:
    msg = build_correction_message(_signal(LoopSignalType.EXACT_REPEAT))
    assert "same tool" in msg.lower() or "repeated" in msg.lower() or "different" in msg.lower()


def test_correction_for_semantic_repeat() -> None:
    msg = build_correction_message(_signal(LoopSignalType.SEMANTIC_REPEAT))
    assert len(msg) > 20


def test_correction_for_no_progress() -> None:
    msg = build_correction_message(_signal(LoopSignalType.NO_PROGRESS))
    assert len(msg) > 20


def test_correction_is_string_for_all_signal_types() -> None:
    for stype in LoopSignalType:
        if stype == LoopSignalType.BUDGET_EXHAUSTED:
            continue
        msg = build_correction_message(_signal(stype))
        assert isinstance(msg, str)
        assert len(msg) > 0
