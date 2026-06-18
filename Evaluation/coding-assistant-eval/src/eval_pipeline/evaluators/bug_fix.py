"""SWE-bench style evaluator for bug fixing tasks.

Applies the model-generated patch to a local repo clone and runs the repo's
test suite. Pass/fail is binary and objective -- no judge needed.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
from pathlib import Path

from eval_pipeline.logging import get_logger
from eval_pipeline.metrics import entries_evaluated_total
from eval_pipeline.models import ExecutionResult, LogEntry, TaskResult, TaskType
from eval_pipeline.pipeline.similarity import SimilarityFilter

logger = get_logger(__name__)

_DIFF_FENCE = re.compile(r"```(?:diff|patch)?\n(.*?)```", re.DOTALL)


def _extract_patch(text: str) -> str:
    match = _DIFF_FENCE.search(text)
    return match.group(1).strip() if match else text.strip()


def _apply_patch_and_test(repo_path: str, patch: str, timeout: float = 60.0) -> bool:
    """Apply a unified diff patch to `repo_path` and run pytest.

    Returns True if all tests pass.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as pf:
        pf.write(patch)
        patch_file = pf.name

    try:
        apply_result = subprocess.run(
            ["git", "apply", "--check", patch_file],
            cwd=repo_path,
            capture_output=True,
            timeout=10.0,
        )
        if apply_result.returncode != 0:
            return False

        subprocess.run(
            ["git", "apply", patch_file],
            cwd=repo_path,
            capture_output=True,
            timeout=10.0,
        )

        test_result = subprocess.run(
            ["python", "-m", "pytest", "--tb=no", "-q"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return test_result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except FileNotFoundError:
        # git or pytest not found in test env
        return False
    finally:
        Path(patch_file).unlink(missing_ok=True)
        # Revert the patch so the next evaluation starts from a clean state
        try:
            subprocess.run(
                ["git", "checkout", "."],
                cwd=repo_path,
                capture_output=True,
                timeout=10.0,
            )
        except Exception:
            pass


class BugFixEvaluator:
    """SWE-bench style evaluator: apply patch, run tests, binary pass/fail."""

    def __init__(self) -> None:
        self._filter = SimilarityFilter()

    async def evaluate(self, entry: LogEntry, new_output: str) -> TaskResult:
        sim_score, skip = await self._filter.check(entry.old_model_output, new_output)

        if skip or not entry.repo_path:
            entries_evaluated_total.labels(task_type=TaskType.BUG_FIXING.value).inc()
            return TaskResult(
                log_entry_id=entry.id,
                task_type=TaskType.BUG_FIXING,
                old_output=entry.old_model_output,
                new_output=new_output,
                similarity_score=sim_score,
                filtered_by_similarity=skip,
                implicit_weight=entry.implicit_signals.quality_weight,
            )

        loop = asyncio.get_event_loop()

        old_patch = _extract_patch(entry.old_model_output)
        new_patch = _extract_patch(new_output)

        old_pass, new_pass = await asyncio.gather(
            loop.run_in_executor(None, _apply_patch_and_test, entry.repo_path, old_patch),
            loop.run_in_executor(None, _apply_patch_and_test, entry.repo_path, new_patch),
        )

        old_exec = ExecutionResult(passed=1 if old_pass else 0, failed=0 if old_pass else 1)
        new_exec = ExecutionResult(passed=1 if new_pass else 0, failed=0 if new_pass else 1)

        logger.info(
            "bug_fix_eval",
            entry_id=entry.id,
            old_pass=old_pass,
            new_pass=new_pass,
        )
        entries_evaluated_total.labels(task_type=TaskType.BUG_FIXING.value).inc()

        return TaskResult(
            log_entry_id=entry.id,
            task_type=TaskType.BUG_FIXING,
            old_output=entry.old_model_output,
            new_output=new_output,
            similarity_score=sim_score,
            old_execution=old_exec,
            new_execution=new_exec,
            implicit_weight=entry.implicit_signals.quality_weight,
        )
