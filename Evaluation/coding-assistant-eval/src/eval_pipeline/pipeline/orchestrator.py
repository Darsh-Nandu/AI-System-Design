"""Main orchestrator that ties together all eval stages for one run."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from eval_pipeline.config import get_settings
from eval_pipeline.dataset.sampler import prioritise_high_signal, stratified_sample
from eval_pipeline.evaluators.bug_fix import BugFixEvaluator
from eval_pipeline.evaluators.code_gen import CodeGenEvaluator
from eval_pipeline.evaluators.explanation import ExplanationEvaluator
from eval_pipeline.feedback.implicit import compute_weighted_regression_score
from eval_pipeline.logging import get_logger
from eval_pipeline.metrics import (
    eval_runs_total,
    improvements_detected_total,
    pass_rate_gauge,
    regressions_detected_total,
    ship_decision_gauge,
)
from eval_pipeline.models import (
    EvalRun,
    EvalStatus,
    EvalSummary,
    LogEntry,
    ShipDecision,
    TaskResult,
    TaskType,
)
from eval_pipeline.pipeline.replay import ReplayPipeline
from eval_pipeline.registry.store import EvalRegistry

logger = get_logger(__name__)
settings = get_settings()


def _make_decision(summary: EvalSummary) -> tuple[ShipDecision, list[str]]:
    reasons: list[str] = []
    hold = False

    cg_drop = summary.code_gen_old_pass_rate - summary.code_gen_new_pass_rate
    if cg_drop > settings.code_gen_regression_threshold:
        reasons.append(
            f"Code gen pass rate dropped {cg_drop:.1%} (threshold {settings.code_gen_regression_threshold:.1%})"
        )
        hold = True

    bf_drop = summary.bug_fix_old_pass_rate - summary.bug_fix_new_pass_rate
    if bf_drop > settings.bug_fix_regression_threshold:
        reasons.append(
            f"Bug fix pass rate dropped {bf_drop:.1%} (threshold {settings.bug_fix_regression_threshold:.1%})"
        )
        hold = True

    exp_drop = summary.explanation_old_score - summary.explanation_new_score
    if exp_drop > settings.explanation_regression_threshold:
        reasons.append(
            f"Explanation score dropped {exp_drop:.2f} (threshold {settings.explanation_regression_threshold:.2f})"
        )
        hold = True

    if summary.weighted_regression_score > settings.regression_hold_threshold:
        reasons.append(
            f"Weighted regression score {summary.weighted_regression_score:.1f} exceeds threshold"
        )
        hold = True

    if hold:
        return ShipDecision.HOLD, reasons

    if not reasons and summary.regression_count == 0:
        return ShipDecision.SHIP, ["No regressions detected across all task types"]

    return ShipDecision.REVIEW, reasons or ["Some differences detected, manual review recommended"]


class EvalOrchestrator:
    def __init__(self, candidate_model: str | None = None) -> None:
        self._replay = ReplayPipeline(model=candidate_model)
        self._code_gen = CodeGenEvaluator(timeout=settings.sandbox_timeout_seconds)
        self._bug_fix = BugFixEvaluator()
        self._explanation = ExplanationEvaluator()
        self._registry = EvalRegistry()

    async def run(
        self,
        run: EvalRun,
        entries: list[LogEntry],
        per_task_type: int = 100,
    ) -> EvalRun:
        run.status = EvalStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        await self._registry.upsert_run(run)

        try:
            sample = prioritise_high_signal(
                stratified_sample(entries, per_task_type=per_task_type)
            )

            logger.info("eval_run_started", run_id=run.id, entries=len(sample))

            new_outputs = await self._replay.generate_batch(sample)

            tasks = []
            for entry in sample:
                new_out = new_outputs.get(entry.id, "")
                evaluator = {
                    TaskType.CODE_GENERATION: self._code_gen,
                    TaskType.BUG_FIXING: self._bug_fix,
                    TaskType.CODE_EXPLANATION: self._explanation,
                }[entry.task_type]
                tasks.append(evaluator.evaluate(entry, new_out))

            results: list[TaskResult] = await asyncio.gather(*tasks)

            await self._registry.save_results(run.id, results)

            summary = self._build_summary(results)
            run.summary = summary
            run.status = EvalStatus.COMPLETED
            run.finished_at = datetime.now(timezone.utc)

            _update_metrics(summary)
            eval_runs_total.labels(status="completed").inc()
            logger.info("eval_run_completed", run_id=run.id, decision=summary.ship_decision)

        except Exception as exc:
            run.status = EvalStatus.FAILED
            run.error = str(exc)
            run.finished_at = datetime.now(timezone.utc)
            eval_runs_total.labels(status="failed").inc()
            logger.exception("eval_run_failed", run_id=run.id, error=str(exc))

        await self._registry.upsert_run(run)
        return run

    def _build_summary(self, results: list[TaskResult]) -> EvalSummary:
        by_type: dict[TaskType, list[TaskResult]] = {t: [] for t in TaskType}
        filtered = 0
        regressions = 0
        improvements = 0

        for r in results:
            by_type[r.task_type].append(r)
            if r.filtered_by_similarity:
                filtered += 1
            if r.regression_flag:
                regressions += 1
                regressions_detected_total.labels(task_type=r.task_type.value).inc()
            if r.improvement_flag:
                improvements += 1
                improvements_detected_total.labels(task_type=r.task_type.value).inc()

        def _avg_exec_rate(bucket: list[TaskResult], old: bool) -> float:
            rates = [
                (r.old_execution if old else r.new_execution).pass_rate
                for r in bucket
                if (r.old_execution if old else r.new_execution) is not None
            ]
            return sum(rates) / len(rates) if rates else 0.0

        def _avg_judge(bucket: list[TaskResult], old: bool) -> float:
            scores = [
                (r.old_judge_score if old else r.new_judge_score).overall
                for r in bucket
                if (r.old_judge_score if old else r.new_judge_score) is not None
            ]
            return sum(scores) / len(scores) if scores else 0.0

        cg = by_type[TaskType.CODE_GENERATION]
        bf = by_type[TaskType.BUG_FIXING]
        ex = by_type[TaskType.CODE_EXPLANATION]

        weighted_score = compute_weighted_regression_score(results)
        decision, reasons = _make_decision(
            EvalSummary(
                code_gen_old_pass_rate=_avg_exec_rate(cg, old=True),
                code_gen_new_pass_rate=_avg_exec_rate(cg, old=False),
                bug_fix_old_pass_rate=_avg_exec_rate(bf, old=True),
                bug_fix_new_pass_rate=_avg_exec_rate(bf, old=False),
                explanation_old_score=_avg_judge(ex, old=True),
                explanation_new_score=_avg_judge(ex, old=False),
                weighted_regression_score=weighted_score,
            )
        )

        return EvalSummary(
            total_entries=len(results),
            filtered_by_similarity=filtered,
            evaluated=len(results) - filtered,
            code_gen_old_pass_rate=_avg_exec_rate(cg, old=True),
            code_gen_new_pass_rate=_avg_exec_rate(cg, old=False),
            bug_fix_old_pass_rate=_avg_exec_rate(bf, old=True),
            bug_fix_new_pass_rate=_avg_exec_rate(bf, old=False),
            explanation_old_score=_avg_judge(ex, old=True),
            explanation_new_score=_avg_judge(ex, old=False),
            regression_count=regressions,
            improvement_count=improvements,
            weighted_regression_score=weighted_score,
            ship_decision=decision,
            decision_reasons=reasons,
        )


def _update_metrics(summary: EvalSummary) -> None:
    pass_rate_gauge.labels(task_type="code_generation", model_role="baseline").set(
        summary.code_gen_old_pass_rate
    )
    pass_rate_gauge.labels(task_type="code_generation", model_role="candidate").set(
        summary.code_gen_new_pass_rate
    )
    pass_rate_gauge.labels(task_type="bug_fixing", model_role="baseline").set(
        summary.bug_fix_old_pass_rate
    )
    pass_rate_gauge.labels(task_type="bug_fixing", model_role="candidate").set(
        summary.bug_fix_new_pass_rate
    )
    decision_map = {ShipDecision.SHIP: 1, ShipDecision.REVIEW: 0, ShipDecision.HOLD: -1}
    ship_decision_gauge.set(decision_map[summary.ship_decision])
