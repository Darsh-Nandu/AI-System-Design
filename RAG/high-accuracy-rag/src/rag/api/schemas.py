"""API request and response schemas."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from rag.models import CitedClaim, DecomposedQuery, DocType, IngestionResult


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    jurisdiction: list[str] | None = None
    doc_type: DocType | None = None
    tags: list[str] | None = None
    date_from: date | None = None
    date_to: date | None = None


class QueryResponse(BaseModel):
    query: str
    answer: str
    citations: list[str]
    cited_claims: list[CitedClaim]
    faithfulness_score: float
    ungrounded_claims: list[str]
    retrieved_chunk_count: int
    chunks_passed_crag: int
    decomposition: DecomposedQuery | None


class IngestRequest(BaseModel):
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


class FreshnessResponse(BaseModel):
    staleness_by_doc_type: dict[str, float]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
