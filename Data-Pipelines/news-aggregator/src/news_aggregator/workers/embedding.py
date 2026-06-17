"""Embedding model — sentence-transformers, loaded once per process."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from news_aggregator.config import get_settings
from news_aggregator.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="embed")


@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    logger.info("loading_embedding_model", model=settings.embedding_model)
    model = SentenceTransformer(settings.embedding_model)
    return model


def _embed_sync(text: str) -> list[float]:
    model = _load_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


async def embed(text: str) -> list[float]:
    """Non-blocking embed — runs in thread pool so async workers don't block."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _embed_sync, text)


async def embed_batch(texts: list[str]) -> list[list[float]]:
    loop = asyncio.get_running_loop()

    def _batch() -> list[list[float]]:
        model = _load_model()
        vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)
        return [v.tolist() for v in vectors]

    return await loop.run_in_executor(_executor, _batch)
