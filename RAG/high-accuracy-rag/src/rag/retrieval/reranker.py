"""Cross-encoder re-ranker using ms-marco-MiniLM-L-6-v2.

Scores each candidate chunk against the original query using a cross-encoder
(full attention over both query and chunk text), which is more accurate than
bi-encoder cosine similarity for final ranking.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from sentence_transformers.cross_encoder import CrossEncoder

from rag.config import get_settings
from rag.logging import get_logger
from rag.metrics import rerank_latency
from rag.models import ScoredChunk

logger = get_logger(__name__)
settings = get_settings()

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reranker")
_reranker: CrossEncoder | None = None


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(settings.reranker_model)
    return _reranker


def _rerank_sync(query: str, chunks: list[ScoredChunk]) -> list[float]:
    pairs = [(query, sc.chunk.text) for sc in chunks]
    return list(_get_reranker().predict(pairs))


async def rerank(query: str, chunks: list[ScoredChunk], top_k: int | None = None) -> list[ScoredChunk]:
    if not chunks:
        return []

    k = top_k or settings.rerank_top_k
    t0 = time.perf_counter()

    loop = asyncio.get_event_loop()
    scores: list[float] = await loop.run_in_executor(_executor, _rerank_sync, query, chunks)

    rerank_latency.observe(time.perf_counter() - t0)

    for sc, score in zip(chunks, scores):
        sc.rerank_score = float(score)

    ranked = sorted(chunks, key=lambda sc: sc.rerank_score, reverse=True)
    return ranked[:k]
