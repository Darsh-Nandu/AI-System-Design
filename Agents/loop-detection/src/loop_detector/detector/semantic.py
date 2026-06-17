"""Layer 3: Semantic similarity detection.

Embeds each (action, observation) pair and compares against the last N pairs.
High cosine similarity with different exact args indicates a 'soft loop':
the agent is rephrasing the same failed approach without making progress.
"""

from __future__ import annotations

import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from loop_detector.config import get_settings
from loop_detector.logging import get_logger
from loop_detector.metrics import semantic_hits_total
from loop_detector.models import AgentStep, LoopSignal, LoopSignalType

settings = get_settings()
logger = get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embed-loop")


@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    logger.info("loading_embedding_model", model="all-MiniLM-L6-v2")
    return SentenceTransformer("all-MiniLM-L6-v2")


def _embed_sync(text: str) -> list[float]:
    model = _load_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


async def embed(text: str) -> list[float]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _embed_sync, text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a)
    vb = np.array(b)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


class SemanticDetector:
    """Embedding-based soft loop detector."""

    def __init__(
        self,
        window: int | None = None,
        threshold: float | None = None,
    ) -> None:
        self._window = window or settings.semantic_window
        self._threshold = threshold or settings.semantic_threshold
        self._history: deque[tuple[str, list[float]]] = deque(maxlen=self._window)

    async def check(
        self,
        step: AgentStep,
        session_id: str,
    ) -> LoopSignal | None:
        text = f"tool={step.tool_name} | {step.observation[:500]}"
        embedding = await embed(text)

        best_score = 0.0
        for _prev_text, prev_embedding in self._history:
            score = cosine_similarity(embedding, prev_embedding)
            if score > best_score:
                best_score = score

        self._history.append((text, embedding))

        if best_score >= self._threshold:
            semantic_hits_total.inc()
            logger.info(
                "semantic_loop_detected",
                session_id=session_id,
                tool=step.tool_name,
                step=step.step,
                score=best_score,
            )
            return LoopSignal(
                session_id=session_id,
                signal_type=LoopSignalType.SEMANTIC_SIMILARITY,
                step=step.step,
                tool_name=step.tool_name,
                tool_args_hash=step.args_hash,
                similarity_score=best_score,
                message=(
                    f"Soft loop detected: '{step.tool_name}' call at step {step.step} "
                    f"is semantically similar (score={best_score:.3f}) to a recent action. "
                    "The agent appears to be rephrasing the same failed approach."
                ),
                metadata={"score": best_score, "threshold": self._threshold},
            )
        return None

    def reset(self) -> None:
        self._history.clear()
