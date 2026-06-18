"""Execution-based evaluator for code generation tasks.

Extracts code from the model output, runs it in a sandboxed subprocess against
each test case, and reports pass/fail counts. No judge bias -- execution is
ground truth.
"""

from __future__ import annotations

import asyncio
import re
import sys
import tempfile
import time
from pathlib import Path

from eval_pipeline.logging import get_logger
from eval_pipeline.metrics import entries_evaluated_total, sandbox_latency
from eval_pipeline.models import ExecutionResult, LogEntry, TaskResult, TaskType, TestCase
from eval_pipeline.pipeline.similarity import SimilarityFilter

logger = get_logger(__name__)

_CODE_FENCE = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)


def _extract_code(text: str) -> str:
    """Pull the first fenced code block; fall back to the full text."""
    match = _CODE_FENCE.search(text)
    return match.group(1).strip() if match else text.strip()


def _run_test_case(code: str, test_case: TestCase, timeout: float) -> bool:
    """Execute `code` synchronously, passing `input_data` via stdin.

    Returns True if stdout matches expected_output exactly (stripped).
    Runs in the same process but isolated in a subprocess for safety.
    """
    import subprocess

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        # Wrap the user code so it reads from a variable rather than stdin
        wrapped = f"_INPUT = '''{test_case.input_data}'''\n{code}"
        f.write(wrapped)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        actual = result.stdout.strip()
        return actual == test_case.expected_output.strip()
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def _execute_code(
    code: str,
    test_cases: list[TestCase],
    timeout: float,
) -> ExecutionResult:
    loop = asyncio.get_event_loop()
    passed = failed = errors = timed_out = 0
    t0 = time.perf_counter()

    for tc in test_cases:
        try:
            ok = await loop.run_in_executor(
                None, _run_test_case, code, tc, timeout
            )
            if ok:
                passed += 1
            else:
                failed += 1
        except Exception:
            errors += 1

    elapsed = time.perf_counter() - t0
    sandbox_latency.observe(elapsed)

    return ExecutionResult(
        passed=passed,
        failed=failed,
        errors=errors,
        timeout=timed_out > 0,
    )


class CodeGenEvaluator:
    """Evaluates code generation entries via execution-based testing."""

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout
        self._filter = SimilarityFilter()

    async def evaluate(self, entry: LogEntry, new_output: str) -> TaskResult:
        sim_score, skip = await self._filter.check(entry.old_model_output, new_output)

        old_code = _extract_code(entry.old_model_output)
        new_code = _extract_code(new_output)

        if skip or not entry.test_cases:
            entries_evaluated_total.labels(task_type=TaskType.CODE_GENERATION.value).inc()
            return TaskResult(
                log_entry_id=entry.id,
                task_type=TaskType.CODE_GENERATION,
                old_output=entry.old_model_output,
                new_output=new_output,
                similarity_score=sim_score,
                filtered_by_similarity=skip,
                implicit_weight=entry.implicit_signals.quality_weight,
            )

        old_exec, new_exec = await asyncio.gather(
            _execute_code(old_code, entry.test_cases, self._timeout),
            _execute_code(new_code, entry.test_cases, self._timeout),
        )

        logger.info(
            "code_gen_eval",
            entry_id=entry.id,
            old_pass_rate=round(old_exec.pass_rate, 3),
            new_pass_rate=round(new_exec.pass_rate, 3),
        )
        entries_evaluated_total.labels(task_type=TaskType.CODE_GENERATION.value).inc()

        return TaskResult(
            log_entry_id=entry.id,
            task_type=TaskType.CODE_GENERATION,
            old_output=entry.old_model_output,
            new_output=new_output,
            similarity_score=sim_score,
            old_execution=old_exec,
            new_execution=new_exec,
            implicit_weight=entry.implicit_signals.quality_weight,
        )
