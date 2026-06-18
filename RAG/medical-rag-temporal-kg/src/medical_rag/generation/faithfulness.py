"""Faithfulness checker: verify every output sentence is grounded in evidence."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import structlog
from sentence_transformers import SentenceTransformer

from medical_rag.config import get_settings
from medical_rag.models import EvidenceItem

log = structlog.get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        cfg = get_settings()
        _model = SentenceTransformer(cfg.embedding_model)
    return _model


def _split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


async def check_faithfulness(
    answer: str,
    evidence: list[EvidenceItem],
) -> tuple[str, list[str], float]:
    """Return (grounded_answer, ungrounded_sentences, faithfulness_score)."""
    cfg = get_settings()
    threshold = cfg.faithfulness_threshold

    sentences = _split_sentences(answer)
    if not sentences or not evidence:
        return answer, [], 1.0

    evidence_texts = [ev.content[:500] for ev in evidence]

    import asyncio
    loop = asyncio.get_event_loop()
    model = _get_model()

    def _encode_all():
        sent_vecs = model.encode(sentences)
        ev_vecs = model.encode(evidence_texts)
        return sent_vecs, ev_vecs

    sent_vecs, ev_vecs = await loop.run_in_executor(_executor, _encode_all)

    grounded: list[str] = []
    ungrounded: list[str] = []

    for sentence, svec in zip(sentences, sent_vecs):
        max_sim = max(_cosine_sim(svec, evec) for evec in ev_vecs)
        if max_sim >= threshold:
            grounded.append(sentence)
        else:
            log.warning(
                "ungrounded_sentence",
                sentence=sentence[:80],
                max_sim=round(max_sim, 3),
                threshold=threshold,
            )
            ungrounded.append(sentence)

    faithfulness_score = len(grounded) / len(sentences) if sentences else 1.0
    grounded_answer = " ".join(grounded)

    return grounded_answer, ungrounded, faithfulness_score
