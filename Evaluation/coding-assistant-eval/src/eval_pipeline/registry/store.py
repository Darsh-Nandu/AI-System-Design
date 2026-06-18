"""Versioned eval run registry backed by Postgres.

Each eval run is stored as an immutable record. Historical runs for any model
pair can be queried to show trend lines per task type over time.
"""

from __future__ import annotations

from sqlalchemy import select

from eval_pipeline.logging import get_logger
from eval_pipeline.models import EvalRun, EvalStatus, EvalSummary, ShipDecision, TaskResult
from eval_pipeline.storage.postgres import AsyncSessionLocal, EvalRunORM, TaskResultORM

logger = get_logger(__name__)


class EvalRegistry:
    async def upsert_run(self, run: EvalRun) -> None:
        async with AsyncSessionLocal() as db:
            existing = await db.get(EvalRunORM, run.id)
            if existing is None:
                orm = EvalRunORM(
                    id=run.id,
                    suite_name=run.suite_name,
                    baseline_model=run.baseline_model,
                    candidate_model=run.candidate_model,
                    status=run.status.value,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    summary=run.summary.model_dump() if run.summary else None,
                    error=run.error,
                    meta=run.metadata,
                )
                db.add(orm)
            else:
                existing.status = run.status.value
                existing.started_at = run.started_at
                existing.finished_at = run.finished_at
                existing.summary = run.summary.model_dump() if run.summary else None
                existing.error = run.error
            await db.commit()

    async def save_results(self, run_id: str, results: list[TaskResult]) -> None:
        async with AsyncSessionLocal() as db:
            for r in results:
                orm = TaskResultORM(
                    run_id=run_id,
                    log_entry_id=r.log_entry_id,
                    task_type=r.task_type.value,
                    similarity_score=r.similarity_score,
                    filtered=r.filtered_by_similarity,
                    old_pass_rate=r.old_execution.pass_rate if r.old_execution else None,
                    new_pass_rate=r.new_execution.pass_rate if r.new_execution else None,
                    old_judge_overall=r.old_judge_score.overall if r.old_judge_score else None,
                    new_judge_overall=r.new_judge_score.overall if r.new_judge_score else None,
                    implicit_weight=r.implicit_weight,
                    regression_flag=r.regression_flag,
                    improvement_flag=r.improvement_flag,
                )
                db.add(orm)
            await db.commit()

    async def get_run(self, run_id: str) -> EvalRun | None:
        async with AsyncSessionLocal() as db:
            orm = await db.get(EvalRunORM, run_id)
        return _orm_to_run(orm) if orm else None

    async def list_runs(
        self,
        baseline_model: str | None = None,
        candidate_model: str | None = None,
        limit: int = 50,
    ) -> list[EvalRun]:
        async with AsyncSessionLocal() as db:
            q = select(EvalRunORM).order_by(EvalRunORM.started_at.desc()).limit(limit)
            if baseline_model:
                q = q.where(EvalRunORM.baseline_model == baseline_model)
            if candidate_model:
                q = q.where(EvalRunORM.candidate_model == candidate_model)
            result = await db.execute(q)
            rows = result.scalars().all()
        return [_orm_to_run(r) for r in rows]

    async def get_results(self, run_id: str) -> list[TaskResultORM]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(TaskResultORM).where(TaskResultORM.run_id == run_id)
            )
            return list(result.scalars().all())


def _orm_to_run(orm: EvalRunORM) -> EvalRun:
    run = EvalRun(
        id=orm.id,
        suite_name=orm.suite_name,
        baseline_model=orm.baseline_model,
        candidate_model=orm.candidate_model,
        status=EvalStatus(orm.status),
        started_at=orm.started_at,
        finished_at=orm.finished_at,
        error=orm.error,
        metadata=orm.meta or {},
    )
    if orm.summary:
        run.summary = EvalSummary(**orm.summary)
    return run
