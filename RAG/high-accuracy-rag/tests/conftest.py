"""Shared fixtures for RAG tests."""

from __future__ import annotations

from datetime import date

import pytest

from rag.models import DocType, DocumentChunk, RawDocument, ScoredChunk


def make_raw_doc(
    serial: str = "0001",
    version: int = 1,
    text: str = "Section 1\n\nThe defendant was found liable for negligence.\n\nSection 2\n\nDamages were awarded at $500,000.",
) -> RawDocument:
    return RawDocument(
        country_code="IN",
        state_code="MH",
        district_code="MUM",
        year=2019,
        doc_type=DocType.CASE_LAW,
        serial=serial,
        name=f"Test Case {serial}",
        date=date(2019, 3, 14),
        text=text,
        jurisdiction=["IN", "MH"],
        tags=["liability", "negligence"],
        version=version,
    )


def make_chunk(
    text: str = "The defendant was found liable for negligence.",
    document_id: str = "IN:MH:MUM:2019:CR:0001:v1",
    chunk_index: int = 0,
) -> DocumentChunk:
    return DocumentChunk(
        id=f"{document_id}:{chunk_index:04d}",
        document_id=document_id,
        text=text,
        section="Section 1",
        chunk_index=chunk_index,
    )


def make_scored_chunk(
    text: str = "The defendant was found liable for negligence.",
    score: float = 0.9,
) -> ScoredChunk:
    return ScoredChunk(chunk=make_chunk(text=text), score=score)
