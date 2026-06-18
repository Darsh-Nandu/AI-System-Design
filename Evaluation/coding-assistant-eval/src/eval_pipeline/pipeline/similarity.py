"""Cosine similarity pre-filter -- the first stage of the cascaded evaluation."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from sentence_transformers import SentenceTransformer

from eval_pipeline.config import get_settings
from eval_pipeline.logging import get_logger
from eval_pipeline.metrics import entries_filtered_total

logger = get_logger(__name__)
settings = get_settings()

_executor = ThreadPoolExecutor(max_workers=2)
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def _embed_sync(texts: list[str]) -> np.ndarray:
    return _get_model().encode(texts, normalize_embeddings=True)


async def embed(texts: list[str]) -> np.ndarray:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _embed_sync, texts)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two normalised embedding vectors."""
    return float(np.dot(a, b))


class SimilarityFilter:
    """Filters out pairs where old and new outputs are essentially identical.

    Similarity above the threshold means the model did not substantively change
    its answer -- no need to run the expensive LLM judge.
    """

    def __init__(self, threshold: float | None = None) -> None:
        self._threshold = threshold or settings.similarity_filter_threshold

    async def check(self, old_text: str, new_text: str) -> tuple[float, bool]:
        """Return (similarity_score, should_skip).

        should_skip=True means the pair is too similar to bother judging.
        """
        if not old_text.strip() or not new_text.strip():
            return 0.0, False

        embeddings = await embed([old_text, new_text])
        score = cosine_similarity(embeddings[0], embeddings[1])
        skip = score >= self._threshold

        if skip:
            entries_filtered_total.inc()
            logger.debug("similarity_filter_skip", score=round(score, 4))

        return score, skip
