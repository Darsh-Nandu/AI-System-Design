"""Integration tests for the full eval pipeline.

Set SKIP_INTEGRATION=1 to skip when Postgres is unavailable.
"""

from __future__ import annotations

import os
import uuid

import pytest

from eval_pipeline.models import EvalRun, EvalStatus

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION", "0") == "1",
    reason="Integration tests require running Postgres",
)


@pytest.mark.asyncio
async def test_registry_upsert_and_fetch() -> None:
    from eval_pipeline.registry.store import EvalRegistry
    from eval_pipeline.storage.postgres import create_tables

    await create_tables()
    registry = EvalRegistry()

    run = EvalRun(
        suite_name="test_suite",
        baseline_model="baseline",
        candidate_model="candidate",
    )
    await registry.upsert_run(run)

    fetched = await registry.get_run(run.id)
    assert fetched is not None
    assert fetched.suite_name == "test_suite"
    assert fetched.status == EvalStatus.PENDING


@pytest.mark.asyncio
async def test_similarity_filter_end_to_end() -> None:
    from eval_pipeline.pipeline.similarity import SimilarityFilter

    f = SimilarityFilter(threshold=0.95)
    score, skip = await f.check(
        "def add(a, b): return a + b",
        "def add(a, b): return a + b",
    )
    assert skip is True


@pytest.mark.asyncio
async def test_code_gen_eval_passes_correct_code() -> None:
    from eval_pipeline.evaluators.code_gen import CodeGenEvaluator
    from tests.conftest import make_code_gen_entry

    evaluator = CodeGenEvaluator(timeout=5.0)
    entry = make_code_gen_entry(
        old_output="```python\ndef answer():\n    return 42\n```",
    )
    new_output = "```python\ndef answer():\n    return 42\n```"
    result = await evaluator.evaluate(entry, new_output)
    assert result is not None
    assert not result.regression_flag
