"""Embedding generation with sentence-transformers (async-safe via executor)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from sentence_transformers import SentenceTransformer

from rag.config import get_settings

settings = get_settings()

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embedder")
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def _embed_sync(texts: list[str]) -> np.ndarray:
    return _get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)


async def embed_texts(texts: list[str]) -> np.ndarray:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _embed_sync, texts)


async def embed_one(text: str) -> list[float]:
    arr = await embed_texts([text])
    return arr[0].tolist()
