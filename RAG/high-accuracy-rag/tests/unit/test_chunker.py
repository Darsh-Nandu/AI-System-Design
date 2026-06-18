"""Unit tests for the document chunker."""

from __future__ import annotations

from rag.indexing.chunker import chunk_document


_LONG_TEXT = "\n\n".join([
    f"Section {i}\n\n" + ("This is a paragraph of legal text. " * 30)
    for i in range(1, 10)
])


def test_chunker_produces_chunks() -> None:
    chunks = chunk_document("DOC:001", _LONG_TEXT, chunk_size=1000)
    assert len(chunks) > 1


def test_chunk_ids_are_unique() -> None:
    chunks = chunk_document("DOC:001", _LONG_TEXT, chunk_size=800)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunk_document_id_matches() -> None:
    chunks = chunk_document("MY:DOC:ID", _LONG_TEXT, chunk_size=1000)
    for chunk in chunks:
        assert chunk.document_id == "MY:DOC:ID"


def test_short_text_single_chunk() -> None:
    text = "This is a very short document with only one chunk."
    chunks = chunk_document("DOC:002", text, chunk_size=5000)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_chunk_text_is_nonempty() -> None:
    chunks = chunk_document("DOC:003", _LONG_TEXT, chunk_size=1000)
    for chunk in chunks:
        assert chunk.text.strip()
