"""Faithfulness checker: post-generation hallucination detection.

Every sentence in the generated answer is mapped back to the retrieved chunks
using cosine similarity. Sentences with no grounding above the threshold
are flagged as ungrounded claims and can be removed or highlighted.

This is the third layer of hallucination prevention.
"""

from __future__ import annotations

import re

import numpy as np

from rag.config import get_settings
from rag.indexing.embedder import embed_texts
from rag.logging import get_logger
from rag.metrics import faithfulness_score, ungrounded_claims_total
from rag.models import CitedClaim, ScoredChunk

logger = get_logger(__name__)
settings = get_settings()

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    sentences = _SENTENCE_RE.split(text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 10]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


async def check_faithfulness(
    answer: str,
    chunks: list[ScoredChunk],
) -> tuple[list[CitedClaim], float]:
    """Return (cited_claims, faithfulness_score).

    faithfulness_score is the fraction of sentences that are grounded.
    """
    sentences = _split_sentences(answer)
    if not sentences or not chunks:
        return [], 1.0

    chunk_texts = [sc.chunk.text for sc in chunks]
    all_texts = sentences + chunk_texts
    embeddings = await embed_texts(all_texts)

    sentence_embs = embeddings[: len(sentences)]
    chunk_embs = embeddings[len(sentences) :]

    claims: list[CitedClaim] = []
    grounded_count = 0

    for i, sentence in enumerate(sentences):
        s_emb = sentence_embs[i]
        best_score = 0.0
        best_chunk_idx = -1

        for j, c_emb in enumerate(chunk_embs):
            sim = _cosine(s_emb, c_emb)
            if sim > best_score:
                best_score = sim
                best_chunk_idx = j

        grounded = best_score >= settings.faithfulness_threshold
        best_chunk = chunks[best_chunk_idx] if best_chunk_idx >= 0 else None

        if not grounded:
            ungrounded_claims_total.inc()
            logger.warning(
                "ungrounded_claim",
                sentence=sentence[:80],
                best_similarity=round(best_score, 3),
            )

        claims.append(
            CitedClaim(
                sentence=sentence,
                chunk_id=best_chunk.chunk.id if best_chunk else None,
                citation=best_chunk.chunk.citation if best_chunk else None,
                similarity=round(best_score, 4),
                grounded=grounded,
            )
        )
        if grounded:
            grounded_count += 1

    score = grounded_count / len(sentences) if sentences else 1.0
    faithfulness_score.observe(score)
    logger.info("faithfulness_check", score=round(score, 3), total=len(sentences), grounded=grounded_count)
    return claims, score
