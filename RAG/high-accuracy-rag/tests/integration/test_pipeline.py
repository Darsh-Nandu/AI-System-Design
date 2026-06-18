"""Integration tests for the RAG pipeline.

Set SKIP_INTEGRATION=1 to skip when Qdrant/Postgres are unavailable.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION", "0") == "1",
    reason="Integration tests require running Qdrant and Postgres",
)


@pytest.mark.asyncio
async def test_chunker_and_embedder_produce_correct_shapes() -> None:
    from rag.indexing.chunker import chunk_document
    from rag.indexing.embedder import embed_texts

    chunks = chunk_document(
        "IN:MH:MUM:2019:CR:0001:v1",
        "Section 1\n\nThe defendant was held liable.\n\nSection 2\n\nDamages were awarded.",
        chunk_size=500,
    )
    assert len(chunks) >= 1

    texts = [c.text for c in chunks]
    embeddings = await embed_texts(texts)
    assert embeddings.shape == (len(chunks), 384)


@pytest.mark.asyncio
async def test_faithfulness_check_with_real_embedder() -> None:
    from rag.generation.faithfulness import check_faithfulness
    from tests.conftest import make_scored_chunk

    answer = "The defendant was held liable for negligence resulting in financial damages."
    chunks = [make_scored_chunk(text="The defendant was held liable for negligence resulting in financial damages.")]

    claims, score = await check_faithfulness(answer, chunks)
    assert score > 0.8
    assert all(c.grounded for c in claims)


@pytest.mark.asyncio
async def test_postgres_tables_created() -> None:
    from rag.storage.postgres import create_tables

    await create_tables()
