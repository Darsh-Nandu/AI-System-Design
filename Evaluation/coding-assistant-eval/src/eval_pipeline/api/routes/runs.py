"""Eval run management routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException

from eval_pipeline.api.schemas import EvalRunOut, StartEvalRequest, TaskResultOut
from eval_pipeline.dataset.loader import iter_log_entries
from eval_pipeline.models import EvalRun
from eval_pipeline.pipeline.orchestrator import EvalOrchestrator
from eval_pipeline.registry.store import EvalRegistry

router = APIRouter(prefix="/runs", tags=["runs"])

_registry = EvalRegistry()


def _to_out(run: EvalRun) -> EvalRunOut:
    return EvalRunOut(
        id=run.id,
        suite_name=run.suite_name,
        baseline_model=run.baseline_model,
        candidate_model=run.candidate_model,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        summary=run.summary,
        error=run.error,
    )


async def _run_eval(run: EvalRun, per_task_type: int, candidate_model: str) -> None:
    entries = [e async for e in iter_log_entries()]
    orchestrator = EvalOrchestrator(candidate_model=candidate_model)
    await orchestrator.run(run, entries, per_task_type=per_task_type)


@router.post("", response_model=EvalRunOut, status_code=202)
async def start_run(body: StartEvalRequest, background_tasks: BackgroundTasks) -> EvalRunOut:
    run = EvalRun(
        suite_name=body.suite_name,
        baseline_model=body.baseline_model,
        candidate_model=body.candidate_model,
    )
    await _registry.upsert_run(run)
    background_tasks.add_task(
        _run_eval, run, body.per_task_type, body.candidate_model
    )
    return _to_out(run)


@router.get("", response_model=list[EvalRunOut])
async def list_runs(
    baseline_model: str | None = None,
    candidate_model: str | None = None,
    limit: int = 50,
) -> list[EvalRunOut]:
    runs = await _registry.list_runs(
        baseline_model=baseline_model,
        candidate_model=candidate_model,
        limit=limit,
    )
    return [_to_out(r) for r in runs]


@router.get("/{run_id}", response_model=EvalRunOut)
async def get_run(run_id: str) -> EvalRunOut:
    run = await _registry.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _to_out(run)


@router.get("/{run_id}/results", response_model=list[TaskResultOut])
async def get_results(run_id: str) -> list[TaskResultOut]:
    rows = await _registry.get_results(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run not found or has no results")
    return [
        TaskResultOut(
            log_entry_id=r.log_entry_id,
            task_type=r.task_type,
            similarity_score=r.similarity_score,
            filtered=r.filtered,
            old_pass_rate=r.old_pass_rate,
            new_pass_rate=r.new_pass_rate,
            old_judge_overall=r.old_judge_overall,
            new_judge_overall=r.new_judge_overall,
            implicit_weight=r.implicit_weight,
            regression_flag=r.regression_flag,
            improvement_flag=r.improvement_flag,
        )
        for r in rows
    ]
