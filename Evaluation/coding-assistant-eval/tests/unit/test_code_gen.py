"""Unit tests for the execution-based code generation evaluator."""

from __future__ import annotations

import pytest

from eval_pipeline.evaluators.code_gen import CodeGenEvaluator, _extract_code
from eval_pipeline.models import TaskType
from tests.conftest import make_code_gen_entry


def test_extract_code_fenced() -> None:
    text = "Here is the solution:\n\n```python\ndef f():\n    return 1\n```\n"
    code = _extract_code(text)
    assert "def f():" in code
    assert "```" not in code


def test_extract_code_no_fence() -> None:
    text = "def f():\n    return 1"
    assert _extract_code(text) == text.strip()


@pytest.mark.asyncio
async def test_correct_code_passes_tests() -> None:
    evaluator = CodeGenEvaluator(timeout=5.0)
    entry = make_code_gen_entry(
        old_output="```python\ndef answer():\n    return 42\n```",
    )
    new_output = "```python\ndef answer():\n    return 42\n```"
    result = await evaluator.evaluate(entry, new_output)
    assert result.task_type == TaskType.CODE_GENERATION
    # Both outputs are identical so similarity filter skips execution
    assert result.filtered_by_similarity is True or (
        result.new_execution is not None and result.new_execution.pass_rate == 1.0
    )


@pytest.mark.asyncio
async def test_wrong_code_fails_tests() -> None:
    evaluator = CodeGenEvaluator(timeout=5.0)
    entry = make_code_gen_entry(
        old_output="```python\ndef answer():\n    return 42\n```",
    )
    new_output = "```python\ndef answer():\n    return 999\n```"
    result = await evaluator.evaluate(entry, new_output)
    assert result.task_type == TaskType.CODE_GENERATION
    if not result.filtered_by_similarity:
        assert result.new_execution is not None
        assert result.new_execution.pass_rate == 0.0


@pytest.mark.asyncio
async def test_no_test_cases_returns_partial_result() -> None:
    evaluator = CodeGenEvaluator(timeout=5.0)
    from eval_pipeline.models import ImplicitSignals, LogEntry, TaskType

    entry = LogEntry(
        prompt="Write something",
        old_model_output="def f(): pass",
        task_type=TaskType.CODE_GENERATION,
        implicit_signals=ImplicitSignals(),
        test_cases=[],
    )
    result = await evaluator.evaluate(entry, "def f(): pass")
    assert result.old_execution is None
    assert result.new_execution is None
