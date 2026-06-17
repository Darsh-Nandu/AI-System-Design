"""Unit tests for the fingerprint detector."""

from __future__ import annotations

import pytest

from loop_detector.detector.fingerprint import FingerprintDetector, make_fingerprint
from loop_detector.models import LoopSignalType
from tests.conftest import make_step


def test_make_fingerprint_is_deterministic() -> None:
    a = make_fingerprint("search", {"query": "hello", "limit": 10})
    b = make_fingerprint("search", {"limit": 10, "query": "hello"})
    assert a == b


def test_make_fingerprint_differs_on_tool_name() -> None:
    a = make_fingerprint("search", {"query": "hello"})
    b = make_fingerprint("filter", {"query": "hello"})
    assert a != b


def test_make_fingerprint_normalizes_floats() -> None:
    a = make_fingerprint("calc", {"value": 0.123456789})
    b = make_fingerprint("calc", {"value": 0.1235})
    assert a == b


def test_fingerprint_no_signal_on_first_occurrence(session_id: str) -> None:
    detector = FingerprintDetector(window=5)
    step = make_step(tool_name="search", args={"query": "test"})
    signal = detector.check(step, session_id)
    assert signal is None


def test_fingerprint_detects_exact_repeat(session_id: str) -> None:
    detector = FingerprintDetector(window=5)
    step = make_step(tool_name="search", args={"query": "test"}, step_index=0)
    detector.check(step, session_id)

    step2 = make_step(tool_name="search", args={"query": "test"}, step_index=1)
    signal = detector.check(step2, session_id)
    assert signal is not None
    assert signal.signal_type == LoopSignalType.EXACT_REPEAT


def test_fingerprint_no_signal_for_different_args(session_id: str) -> None:
    detector = FingerprintDetector(window=5)
    detector.check(make_step(args={"query": "cats"}), session_id)
    signal = detector.check(make_step(args={"query": "dogs"}), session_id)
    assert signal is None


def test_fingerprint_window_evicts_old(session_id: str) -> None:
    detector = FingerprintDetector(window=2)
    detector.check(make_step(args={"query": "a"}, step_index=0), session_id)
    detector.check(make_step(args={"query": "b"}, step_index=1), session_id)
    # "a" should now be evicted from the window of 2
    detector.check(make_step(args={"query": "c"}, step_index=2), session_id)
    signal = detector.check(make_step(args={"query": "a"}, step_index=3), session_id)
    assert signal is None
