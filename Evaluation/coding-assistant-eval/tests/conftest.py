"""Shared test fixtures."""

from __future__ import annotations

import pytest

from eval_pipeline.models import ImplicitSignals, LogEntry, TaskType, TestCase


def make_code_gen_entry(
    prompt: str = "Write a function that returns 42.",
    old_output: str = "```python\ndef answer():\n    return 42\n```",
    copied: bool = True,
    edit_distance: float = 0.0,
) -> LogEntry:
    return LogEntry(
        prompt=prompt,
        old_model_output=old_output,
        task_type=TaskType.CODE_GENERATION,
        implicit_signals=ImplicitSignals(
            copied=copied,
            edit_distance_after_copy=edit_distance,
            re_asked_within_60s=False,
        ),
        test_cases=[
            TestCase(input_data="print(answer())", expected_output="42"),
        ],
    )


def make_explanation_entry(
    raw_code: str = "def f(n): return n * 2",
    reference: str = "Doubles a number.",
    old_output: str = "This function doubles the input number.",
    copied: bool = True,
) -> LogEntry:
    return LogEntry(
        prompt=f"Explain:\n{raw_code}",
        old_model_output=old_output,
        task_type=TaskType.CODE_EXPLANATION,
        raw_code=raw_code,
        reference_explanation=reference,
        implicit_signals=ImplicitSignals(copied=copied),
    )
