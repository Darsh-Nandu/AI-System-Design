"""LLM-as-judge with structured rubric and position-bias mitigation.

Bias mitigations implemented:
1. Different model as judge (not either candidate).
2. Swap order, run twice, average scores (cancels position bias).
3. Explicit rubric: correctness (0-3), clarity (0-3), completeness (0-3).
4. Instruction: "length is not a quality signal."
"""

from __future__ import annotations

import json
import time

import anthropic

from eval_pipeline.config import get_settings
from eval_pipeline.logging import get_logger
from eval_pipeline.metrics import judge_latency
from eval_pipeline.models import JudgeScore

logger = get_logger(__name__)
settings = get_settings()

_SYSTEM_PROMPT = """\
You are a rigorous technical evaluator comparing two AI-generated coding assistant responses.

RUBRIC (score each dimension 0-3):
  correctness: Is the information factually accurate and technically sound?
  clarity: Is the explanation clear and well-structured?
  completeness: Does the response fully address the question?

IMPORTANT RULES:
- Length is NOT a quality signal. Do not prefer longer answers.
- Score each response independently against the rubric, not relative to each other.
- Provide brief reasoning (1-2 sentences) explaining the scores.

Respond with valid JSON only:
{
  "response_a": {"correctness": <0-3>, "clarity": <0-3>, "completeness": <0-3>, "reasoning": "..."},
  "response_b": {"correctness": <0-3>, "clarity": <0-3>, "completeness": <0-3>, "reasoning": "..."}
}"""


def _build_user_prompt(context: str, response_a: str, response_b: str) -> str:
    return (
        f"CONTEXT / QUESTION:\n{context}\n\n"
        f"RESPONSE A:\n{response_a}\n\n"
        f"RESPONSE B:\n{response_b}"
    )


class LLMJudge:
    """Calls Claude to score two responses; averages both orderings to cancel position bias."""

    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.judge_model

    def _call(self, context: str, a: str, b: str) -> tuple[JudgeScore, JudgeScore]:
        t0 = time.perf_counter()
        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_prompt(context, a, b)}],
        )
        judge_latency.observe(time.perf_counter() - t0)

        raw = response.content[0].text
        data = json.loads(raw)
        score_a = JudgeScore(**data["response_a"])
        score_b = JudgeScore(**data["response_b"])
        return score_a, score_b

    def score(self, context: str, old_output: str, new_output: str) -> tuple[JudgeScore, JudgeScore]:
        """Score old_output and new_output with position-bias mitigation.

        Runs the judge twice with swapped order and averages the results.
        Returns (old_score, new_score).
        """
        try:
            # Order 1: old=A, new=B
            score_old_1, score_new_1 = self._call(context, old_output, new_output)
            # Order 2: new=A, old=B  (swapped)
            score_new_2, score_old_2 = self._call(context, new_output, old_output)

            old_avg = JudgeScore(
                correctness=(score_old_1.correctness + score_old_2.correctness) / 2,
                clarity=(score_old_1.clarity + score_old_2.clarity) / 2,
                completeness=(score_old_1.completeness + score_old_2.completeness) / 2,
                reasoning=score_old_1.reasoning,
            )
            new_avg = JudgeScore(
                correctness=(score_new_1.correctness + score_new_2.correctness) / 2,
                clarity=(score_new_1.clarity + score_new_2.clarity) / 2,
                completeness=(score_new_1.completeness + score_new_2.completeness) / 2,
                reasoning=score_new_1.reasoning,
            )
            return old_avg, new_avg

        except Exception as exc:
            logger.warning("judge_failed", error=str(exc))
            default = JudgeScore(correctness=1.5, clarity=1.5, completeness=1.5)
            return default, default
