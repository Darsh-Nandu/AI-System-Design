"""Recursive character chunker with section-aware metadata.

Splits documents into overlapping chunks while preserving section headings
as provenance metadata. No external chunking library dependency.
"""

from __future__ import annotations

import re

from rag.config import get_settings
from rag.indexing.document_id import make_chunk_id
from rag.models import DocumentChunk

settings = get_settings()

_SECTION_RE = re.compile(r"^(#+\s+.+|[A-Z][A-Z\s]+:)", re.MULTILINE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _split_into_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]


def _detect_section(paragraph: str) -> str:
    m = _SECTION_RE.match(paragraph)
    return m.group(0).strip() if m else ""


def chunk_document(
    document_id: str,
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[DocumentChunk]:
    size = chunk_size or settings.chunk_size
    ovlp = overlap or settings.chunk_overlap

    paragraphs = _split_into_paragraphs(text)
    chunks: list[DocumentChunk] = []
    current_text = ""
    current_section = ""
    chunk_index = 0

    for para in paragraphs:
        section = _detect_section(para)
        if section:
            current_section = section

        if len(current_text) + len(para) + 1 > size and current_text:
            chunk_id = make_chunk_id(document_id, chunk_index)
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    document_id=document_id,
                    text=current_text.strip(),
                    section=current_section,
                    chunk_index=chunk_index,
                )
            )
            chunk_index += 1
            # Keep overlap from end of current chunk
            words = current_text.split()
            overlap_words = max(0, len(words) - ovlp // 5)
            current_text = " ".join(words[overlap_words:]) + "\n\n" + para
        else:
            current_text = (current_text + "\n\n" + para).strip() if current_text else para

    if current_text.strip():
        chunk_id = make_chunk_id(document_id, chunk_index)
        chunks.append(
            DocumentChunk(
                id=chunk_id,
                document_id=document_id,
                text=current_text.strip(),
                section=current_section,
                chunk_index=chunk_index,
            )
        )

    return chunks
