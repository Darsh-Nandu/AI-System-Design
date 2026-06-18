"""Unit tests for the faithfulness checker."""

from __future__ import annotations

import pytest

from tests.conftest import make_scored_chunk


@pytest.mark.asyncio
async def test_grounded_claim_passes() -> None:
    from rag.generation.faithfulness import check_faithfulness

    chunk_text = "The defendant was held liable for data breach."
    answer = "The defendant was held liable for data breach."
    chunks = [make_scored_chunk(text=chunk_text)]

    claims, score = await check_faithfulness(answer, chunks)
    assert score > 0.5
    assert len(claims) > 0


@pytest.mark.asyncio
async def test_unrelated_answer_flags_ungrounded() -> None:
    from rag.generation.faithfulness import check_faithfulness

    chunk_text = "The defendant was held liable for data breach."
    answer = "The Eiffel Tower is located in Paris and was built in 1889."
    chunks = [make_scored_chunk(text=chunk_text)]

    claims, score = await check_faithfulness(answer, chunks)
    ungrounded = [c for c in claims if not c.grounded]
    assert len(ungrounded) > 0
    assert score < 1.0


@pytest.mark.asyncio
async def test_empty_answer_returns_perfect_score() -> None:
    from rag.generation.faithfulness import check_faithfulness

    chunks = [make_scored_chunk()]
    claims, score = await check_faithfulness("", chunks)
    assert score == 1.0
    assert claims == []


@pytest.mark.asyncio
async def test_empty_chunks_returns_perfect_score() -> None:
    from rag.generation.faithfulness import check_faithfulness

    claims, score = await check_faithfulness("Some answer.", [])
    assert score == 1.0
