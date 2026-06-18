"""LLM-as-judge evaluator for code explanation tasks.

Anti-cheat: the model receives raw, uncommented code (comments and docstrings
stripped by the dataset builder). The judge compares the explanation against
the original docs/comments that were hidden.
"""

from __future__ import annotations

from eval_pipeline.judge.llm_judge import LLMJudge
from eval_pipeline.logging import get_logger
from eval_pipeline.metrics import entries_evaluated_total
from eval_pipeline.models import LogEntry, TaskResult, TaskType
from eval_pipeline.pipeline.similarity import SimilarityFilter

logger = get_logger(__name__)

_JUDGE_CONTEXT_TEMPLATE = """\
TASK: Evaluate explanations of the following code snippet.

CODE:
{raw_code}

REFERENCE EXPLANATION (ground truth, hidden from the models):
{reference}

Score each response on:
  correctness: Does the explanation accurately describe what the code does?
  clarity: Is it readable and well-structured?
  completeness: Does it cover all important aspects?"""


class ExplanationEvaluator:
    """Evaluates code explanation via bias-mitigated LLM judge."""

    def __init__(self) -> None:
        self._filter = SimilarityFilter()
        self._judge = LLMJudge()

    async def evaluate(self, entry: LogEntry, new_output: str) -> TaskResult:
        sim_score, skip = await self._filter.check(entry.old_model_output, new_output)

        if skip:
            entries_evaluated_total.labels(task_type=TaskType.CODE_EXPLANATION.value).inc()
            return TaskResult(
                log_entry_id=entry.id,
                task_type=TaskType.CODE_EXPLANATION,
                old_output=entry.old_model_output,
                new_output=new_output,
                similarity_score=sim_score,
                filtered_by_similarity=True,
                implicit_weight=entry.implicit_signals.quality_weight,
            )

        raw_code = entry.raw_code or entry.prompt
        reference = entry.reference_explanation or "(no reference available)"

        context = _JUDGE_CONTEXT_TEMPLATE.format(
            raw_code=raw_code, reference=reference
        )

        # Blocking call -- run in executor to avoid blocking the event loop
        import asyncio

        loop = asyncio.get_event_loop()
        old_score, new_score = await loop.run_in_executor(
            None, self._judge.score, context, entry.old_model_output, new_output
        )

        logger.info(
            "explanation_eval",
            entry_id=entry.id,
            old_overall=round(old_score.overall, 3),
            new_overall=round(new_score.overall, 3),
        )
        entries_evaluated_total.labels(task_type=TaskType.CODE_EXPLANATION.value).inc()

        return TaskResult(
            log_entry_id=entry.id,
            task_type=TaskType.CODE_EXPLANATION,
            old_output=entry.old_model_output,
            new_output=new_output,
            similarity_score=sim_score,
            old_judge_score=old_score,
            new_judge_score=new_score,
            implicit_weight=entry.implicit_signals.quality_weight,
        )
