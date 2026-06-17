"""Recovery Strategy 1: Inject a correction message into the agent context.

The loop is broken without a restart. The agent continues with explicit
awareness of what it tried and why it failed, and is nudged toward a
different approach or to ask the user for clarification.
"""

from __future__ import annotations

from loop_detector.logging import get_logger
from loop_detector.models import DetectionResult, LoopSignal, LoopSignalType

logger = get_logger(__name__)


def build_correction_message(result: DetectionResult) -> str:
    """Build a system message to inject into the agent's context."""
    if not result.signals:
        return _generic_correction(result.step)

    primary = result.signals[-1]
    return _signal_specific_correction(primary, result.step)


def _signal_specific_correction(signal: LoopSignal, step: int) -> str:
    tool_ref = f"'{signal.tool_name}'" if signal.tool_name else "your last tool call"

    if signal.signal_type == LoopSignalType.EXACT_DUPLICATE:
        return (
            f"[LOOP DETECTOR -- SYSTEM]\n"
            f"You have called {tool_ref} with identical arguments {_count_phrase(signal)} "
            f"within the last several steps. The results did not change. "
            f"This approach is not working. You must now:\n"
            f"1. Try a fundamentally different tool or approach, OR\n"
            f"2. Ask the user for clarification if the task requirements are ambiguous.\n"
            f"Do NOT repeat the same call again."
        )

    if signal.signal_type == LoopSignalType.SEMANTIC_SIMILARITY:
        score = signal.similarity_score or 0.0
        return (
            f"[LOOP DETECTOR -- SYSTEM]\n"
            f"Your recent action at step {step} is semantically very similar "
            f"(similarity={score:.2f}) to actions you took earlier. "
            f"You appear to be rephrasing the same failed approach. "
            f"The pattern has been recognised -- please try a genuinely different strategy.\n"
            f"If you are stuck because of missing information, say so explicitly."
        )

    if signal.signal_type == LoopSignalType.NO_PROGRESS:
        return (
            f"[LOOP DETECTOR -- SYSTEM]\n"
            f"The last several steps have not added new information to your reasoning. "
            f"You are spending tokens without making progress. "
            f"Either the task is not solvable with the available tools, "
            f"or you need to change your approach entirely. "
            f"Summarise what you have learned so far, then either ask the user "
            f"for additional context or produce a partial answer."
        )

    if signal.signal_type == LoopSignalType.CAUSAL_CYCLE:
        return (
            f"[LOOP DETECTOR -- SYSTEM]\n"
            f"A causal cycle has been detected at step {step}: you are re-deriving "
            f"the same intermediate result through a repeated chain of tool calls. "
            f"The output you just produced matches an output from {signal.metadata.get('cycle_length', '?')} "
            f"steps ago. You are stuck in a logical loop. Try a different entry point."
        )

    return _generic_correction(step)


def _generic_correction(step: int) -> str:
    return (
        f"[LOOP DETECTOR -- SYSTEM]\n"
        f"A loop pattern was detected at step {step}. "
        f"Your recent actions are not advancing the task. "
        f"Please reconsider your approach."
    )


def _count_phrase(signal: LoopSignal) -> str:
    return "multiple times"
