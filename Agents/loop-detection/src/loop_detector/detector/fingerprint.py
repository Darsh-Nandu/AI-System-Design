"""Layer 2: Action fingerprinting.

Hashes (tool_name, normalized_args) for every tool call.
An exact match within the sliding window is an immediate loop signal.

Normalization rules:
- Sort all dict keys recursively
- Round floats to 4 decimal places
- Strip leading/trailing whitespace from strings
- Sort lists of primitives
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any

from loop_detector.config import get_settings
from loop_detector.logging import get_logger
from loop_detector.metrics import fingerprint_hits_total
from loop_detector.models import AgentStep, LoopSignal, LoopSignalType

settings = get_settings()
logger = get_logger(__name__)


def normalize_args(obj: Any) -> Any:
    """Normalize args so semantically identical calls produce the same hash."""
    if isinstance(obj, dict):
        return {k: normalize_args(v) for k, v in sorted(obj.items())}
    if isinstance(obj, float):
        return round(obj, 4)
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, list):
        normalized = [normalize_args(v) for v in obj]
        # Only sort lists of primitives -- sorting lists of dicts changes meaning
        if all(isinstance(x, (str, int, float, bool)) for x in normalized):
            return sorted(normalized, key=str)
        return normalized
    return obj


def make_fingerprint(tool_name: str, args: dict) -> str:
    """Return a stable SHA-256 fingerprint for a tool call."""
    normalized = normalize_args(args)
    raw = f"{tool_name}:{json.dumps(normalized, sort_keys=True)}"
    return hashlib.sha256(raw.encode()).hexdigest()


class FingerprintDetector:
    """Sliding window of recent fingerprints. Flags exact duplicates."""

    def __init__(self, window: int | None = None) -> None:
        self._window = window or settings.fingerprint_window
        self._history: deque[str] = deque(maxlen=self._window)

    def check(self, step: AgentStep, session_id: str) -> LoopSignal | None:
        fingerprint = step.args_hash
        if fingerprint in self._history:
            fingerprint_hits_total.inc()
            logger.info(
                "fingerprint_match",
                session_id=session_id,
                tool=step.tool_name,
                step=step.step,
            )
            return LoopSignal(
                session_id=session_id,
                signal_type=LoopSignalType.EXACT_DUPLICATE,
                step=step.step,
                tool_name=step.tool_name,
                tool_args_hash=fingerprint,
                message=(
                    f"Exact duplicate detected: '{step.tool_name}' was already called "
                    f"with identical arguments within the last {self._window} steps."
                ),
                metadata={"fingerprint": fingerprint, "window": self._window},
            )
        self._history.append(fingerprint)
        return None

    def reset(self) -> None:
        self._history.clear()
