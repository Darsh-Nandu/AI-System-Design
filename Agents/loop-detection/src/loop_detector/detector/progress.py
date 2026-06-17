"""Layer 5: Progress tracking.

Measures whether each step added new unique information to the agent's context.
Computes a novelty score (0.0 to 1.0) for each observation.
If the rolling average novelty across a window falls below the threshold,
the agent is accumulating cost without advancing toward a solution.
"""

from __future__ import annotations

import hashlib
from collections import deque

from loop_detector.config import get_settings
from loop_detector.logging import get_logger
from loop_detector.metrics import no_progress_total
from loop_detector.models import AgentStep, LoopSignal, LoopSignalType

settings = get_settings()
logger = get_logger(__name__)


class ProgressTracker:
    """Tracks information novelty over a rolling window."""

    def __init__(
        self,
        window: int | None = None,
        threshold: float | None = None,
    ) -> None:
        self._window = window or settings.progress_window
        self._threshold = threshold or settings.progress_novelty_threshold
        self._seen_hashes: set[str] = set()
        self._novelty_window: deque[float] = deque(maxlen=self._window)

    def check(self, step: AgentStep, session_id: str) -> LoopSignal | None:
        obs_hash = hashlib.sha256(step.observation.encode()).hexdigest()

        if obs_hash in self._seen_hashes:
            novelty = 0.0
        else:
            self._seen_hashes.add(obs_hash)
            novelty = 1.0

        self._novelty_window.append(novelty)

        # Need at least a full window before judging progress
        if len(self._novelty_window) < self._window:
            return None

        avg_novelty = sum(self._novelty_window) / len(self._novelty_window)

        if avg_novelty < self._threshold:
            no_progress_total.inc()
            logger.info(
                "no_progress_detected",
                session_id=session_id,
                step=step.step,
                avg_novelty=avg_novelty,
                threshold=self._threshold,
            )
            return LoopSignal(
                session_id=session_id,
                signal_type=LoopSignalType.NO_PROGRESS,
                step=step.step,
                tool_name=step.tool_name,
                message=(
                    f"No progress detected: average novelty across the last {self._window} "
                    f"steps is {avg_novelty:.3f}, below the threshold of {self._threshold}. "
                    "The agent is spending tokens without adding new information."
                ),
                metadata={
                    "avg_novelty": avg_novelty,
                    "threshold": self._threshold,
                    "window": self._window,
                },
            )
        return None

    def reset(self) -> None:
        self._seen_hashes.clear()
        self._novelty_window.clear()
