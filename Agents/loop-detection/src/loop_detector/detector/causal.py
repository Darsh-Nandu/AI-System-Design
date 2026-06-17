"""Causal loop detection.

Tracks a dependency graph: which tool outputs feed into which subsequent inputs.
Detects cycles where the agent re-derives the same conclusion repeatedly,
even when no two adjacent calls are exact duplicates.

Example of a causal loop not caught by fingerprinting:
  Step 1: search("users") -> result_A
  Step 2: filter(result_A) -> result_B
  Step 3: search("users") -> result_A    # same as step 1
  Step 4: filter(result_A) -> result_B    # same as step 2

The fingerprinter catches step 3 (exact match), but causal detection also
catches longer, more subtle cycles across N steps.
"""

from __future__ import annotations

import hashlib

from loop_detector.logging import get_logger
from loop_detector.metrics import causal_cycle_total
from loop_detector.models import AgentStep, LoopSignal, LoopSignalType

logger = get_logger(__name__)

# Max steps to look back when building the dependency graph
_MAX_HISTORY = 50


class CausalLoopDetector:
    """Directed dependency graph to detect multi-step causal cycles."""

    def __init__(self) -> None:
        # Maps output_hash -> list of step indices that produced it
        self._output_to_steps: dict[str, list[int]] = {}
        # Maps step index -> (args_hash, output_hash)
        self._step_records: dict[int, tuple[str, str]] = {}

    def _hash_observation(self, observation: str) -> str:
        return hashlib.sha256(observation.encode()).hexdigest()[:16]

    def check(self, step: AgentStep, session_id: str) -> LoopSignal | None:
        output_hash = self._hash_observation(step.observation)
        args_hash = step.args_hash

        self._step_records[step.step] = (args_hash, output_hash)

        if output_hash in self._output_to_steps:
            prior_steps = self._output_to_steps[output_hash]
            if prior_steps:
                earliest = prior_steps[0]
                cycle_length = step.step - earliest

                if cycle_length >= 2:
                    causal_cycle_total.inc()
                    logger.info(
                        "causal_cycle_detected",
                        session_id=session_id,
                        step=step.step,
                        prior_step=earliest,
                        cycle_length=cycle_length,
                    )
                    return LoopSignal(
                        session_id=session_id,
                        signal_type=LoopSignalType.CAUSAL_CYCLE,
                        step=step.step,
                        tool_name=step.tool_name,
                        tool_args_hash=args_hash,
                        message=(
                            f"Causal cycle detected: the output at step {step.step} "
                            f"matches the output of step {earliest} "
                            f"(cycle length {cycle_length}). "
                            "The agent is re-deriving the same conclusion through a repeated chain."
                        ),
                        metadata={
                            "output_hash": output_hash,
                            "prior_step": earliest,
                            "cycle_length": cycle_length,
                        },
                    )

            self._output_to_steps[output_hash].append(step.step)
        else:
            self._output_to_steps[output_hash] = [step.step]

        return None

    def reset(self) -> None:
        self._output_to_steps.clear()
        self._step_records.clear()
