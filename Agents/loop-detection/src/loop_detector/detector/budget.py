"""Layer 4: Step and token budget.

Hard cap on reasoning steps and total tokens consumed.
On exhaustion, signals forced summarization -- not a silent kill.
The agent produces a partial result and explanation before stopping.
"""

from __future__ import annotations

from loop_detector.config import get_settings
from loop_detector.logging import get_logger
from loop_detector.metrics import budget_exhausted_total
from loop_detector.models import AgentStep, LoopSignal, LoopSignalType

settings = get_settings()
logger = get_logger(__name__)


class BudgetTracker:
    """Tracks step count and token usage against configured limits."""

    def __init__(
        self,
        max_steps: int | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.max_steps = max_steps or settings.max_steps
        self.max_tokens = max_tokens or settings.max_tokens
        self.steps = 0
        self.tokens = 0

    def tick(self, step: AgentStep, session_id: str) -> LoopSignal | None:
        self.steps += 1
        self.tokens += step.tokens_used

        if self.steps >= self.max_steps:
            budget_exhausted_total.labels(reason="steps").inc()
            logger.warning(
                "step_budget_exhausted",
                session_id=session_id,
                steps=self.steps,
                max=self.max_steps,
            )
            return LoopSignal(
                session_id=session_id,
                signal_type=LoopSignalType.BUDGET_EXHAUSTED,
                step=step.step,
                tool_name=step.tool_name,
                message=(
                    f"Step budget exhausted: {self.steps} steps reached the limit of "
                    f"{self.max_steps}. The agent must call summarize_and_halt now."
                ),
                metadata={"steps": self.steps, "tokens": self.tokens, "limit": self.max_steps},
            )

        if self.tokens >= self.max_tokens:
            budget_exhausted_total.labels(reason="tokens").inc()
            logger.warning(
                "token_budget_exhausted",
                session_id=session_id,
                tokens=self.tokens,
                max=self.max_tokens,
            )
            return LoopSignal(
                session_id=session_id,
                signal_type=LoopSignalType.BUDGET_EXHAUSTED,
                step=step.step,
                tool_name=step.tool_name,
                message=(
                    f"Token budget exhausted: {self.tokens:,} tokens reached the limit of "
                    f"{self.max_tokens:,}. The agent must call summarize_and_halt now."
                ),
                metadata={"steps": self.steps, "tokens": self.tokens, "limit": self.max_tokens},
            )

        return None

    @property
    def steps_remaining(self) -> int:
        return max(0, self.max_steps - self.steps)

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.max_tokens - self.tokens)

    def reset(self) -> None:
        self.steps = 0
        self.tokens = 0
