"""Unit tests for the cosine similarity pre-filter."""

from __future__ import annotations

import numpy as np
import pytest

from eval_pipeline.pipeline.similarity import SimilarityFilter, cosine_similarity


def test_cosine_similarity_identical() -> None:
    a = np.array([1.0, 0.0, 0.0])
    b = np.array([1.0, 0.0, 0.0])
    assert abs(cosine_similarity(a, b) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal() -> None:
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert abs(cosine_similarity(a, b)) < 1e-6


@pytest.mark.asyncio
async def test_filter_identical_texts() -> None:
    f = SimilarityFilter(threshold=0.95)
    text = "def add(a, b): return a + b"
    score, skip = await f.check(text, text)
    assert score > 0.99
    assert skip is True


@pytest.mark.asyncio
async def test_filter_different_texts() -> None:
    f = SimilarityFilter(threshold=0.95)
    old = "def add(a, b): return a + b"
    new = "The capital of France is Paris and Napoleon was a famous leader."
    score, skip = await f.check(old, new)
    assert score < 0.95
    assert skip is False


@pytest.mark.asyncio
async def test_filter_empty_text() -> None:
    f = SimilarityFilter(threshold=0.95)
    score, skip = await f.check("", "some content")
    assert skip is False
