"""Intent gap detector.

Computes semantic distance between the user's original request and
the tool call the agent is trying to make. A large gap indicates
the agent's actions may have been redirected by injected content.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import structlog
from sentence_transformers import SentenceTransformer

from guardrails.config import get_settings

log = structlog.get_logger(__name__)

_model: SentenceTransformer | None = None
_executor = ThreadPoolExecutor(max_workers=2)


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        cfg = get_settings()
        _model = SentenceTransformer(cfg.embedding_model)
    return _model


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _tool_call_description(tool_name: str, args: dict) -> str:
    arg_str = ", ".join(f"{k}={str(v)[:50]}" for k, v in args.items())
    return f"{tool_name}({arg_str})"


def compute_intent_gap(user_request: str, tool_name: str, args: dict) -> float:
    """Return cosine similarity between user request and tool action.

    High similarity (close to 1.0) means aligned intent.
    Low similarity (close to 0.0) means large gap -- possible redirection.
    """
    if not user_request:
        return 1.0

    model = _get_model()
    tool_desc = _tool_call_description(tool_name, args)
    u_vec = model.encode(user_request)
    t_vec = model.encode(tool_desc)
    return _cosine_sim(u_vec, t_vec)


def check_intent_gap(user_request: str, tool_name: str, args: dict) -> tuple[bool, float, str]:
    """Check whether the intent gap exceeds the configured threshold.

    Returns (gap_too_large, similarity, reason).
    """
    cfg = get_settings()
    sim = compute_intent_gap(user_request, tool_name, args)
    threshold = cfg.intent_gap_threshold

    if sim < threshold:
        reason = (
            f"Intent gap detected: similarity {sim:.2f} < {threshold}. "
            f"User requested '{user_request[:60]}' but agent wants to call "
            f"'{_tool_call_description(tool_name, args)[:80]}'. "
            "Possible indirect injection redirection."
        )
        log.warning("intent_gap_detected", sim=sim, threshold=threshold, tool=tool_name)
        return True, sim, reason

    return False, sim, "Intent gap within acceptable range"
