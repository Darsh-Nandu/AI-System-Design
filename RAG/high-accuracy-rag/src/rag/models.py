"""Domain models for the high-accuracy RAG system."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field


class DocType(str, Enum):
    CASE_LAW = "case_law"
    STATUTE = "statute"
    REGULATION = "regulation"
    CONTRACT = "contract"
    ADVISORY = "advisory"


class ChunkRelevance(str, Enum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    AMBIGUOUS = "ambiguous"


class DocumentCard(BaseModel):
    """Summary-level document record stored in the Tier-1 Qdrant collection."""

    id: str
    name: str
    date: date
    doc_type: DocType
    jurisdiction: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    summary: str
    stats: dict[str, Any] = Field(default_factory=dict)
    chunk_ids: list[str] = Field(default_factory=list)
    version: int = 1
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentChunk(BaseModel):
    """A text chunk with provenance metadata stored in the Tier-2 Qdrant collection."""

    id: str
    document_id: str
    text: str
    section: str = ""
    page: int | None = None
    chunk_index: int = 0

    @computed_field
    @property
    def citation(self) -> str:
        parts = [self.document_id]
        if self.section:
            parts.append(self.section)
        if self.page is not None:
            parts.append(f"p.{self.page}")
        return " | ".join(parts)


class RawDocument(BaseModel):
    """Input document before indexing."""

    country_code: str
    state_code: str
    district_code: str
    year: int
    doc_type: DocType
    serial: str
    name: str
    date: date
    text: str
    jurisdiction: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    version: int = 1


class SubQuery(BaseModel):
    """One decomposed sub-query with optional structured metadata filters."""

    text: str
    metadata_filters: dict[str, Any] = Field(default_factory=dict)


class DecomposedQuery(BaseModel):
    """Output of the query decomposition stage."""

    original: str
    sub_queries: list[SubQuery] = Field(default_factory=list)
    clarification_needed: bool = False
    clarification_reason: str | None = None


class ScoredChunk(BaseModel):
    """A retrieved chunk annotated with relevance score and CRAG grade."""

    chunk: DocumentChunk
    score: float
    rerank_score: float = 0.0
    relevance: ChunkRelevance = ChunkRelevance.RELEVANT


class CitedClaim(BaseModel):
    """A single sentence from the answer mapped to its source chunk."""

    sentence: str
    chunk_id: str | None = None
    citation: str | None = None
    similarity: float = 0.0
    grounded: bool = True


class RAGResponse(BaseModel):
    """Final response from the query pipeline."""

    query: str
    answer: str
    citations: list[str] = Field(default_factory=list)
    cited_claims: list[CitedClaim] = Field(default_factory=list)
    faithfulness_score: float = 1.0
    ungrounded_claims: list[str] = Field(default_factory=list)
    retrieved_chunk_count: int = 0
    chunks_passed_crag: int = 0
    decomposition: DecomposedQuery | None = None


class IngestionResult(BaseModel):
    """Result of ingesting a single document."""

    document_id: str
    success: bool
    chunk_count: int = 0
    pii_entities_found: int = 0
    error: str | None = None
