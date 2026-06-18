"""Query endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from rag.api.schemas import QueryRequest, QueryResponse
from rag.models import RAGResponse
from rag.pipeline.query import QueryPipeline
from rag.retrieval.metadata_filter import build_card_filter

router = APIRouter(prefix="/query", tags=["query"])

_pipeline = QueryPipeline()


@router.post("", response_model=QueryResponse)
async def query(body: QueryRequest) -> QueryResponse:
    metadata_filter = build_card_filter(
        jurisdiction=body.jurisdiction,
        doc_type=body.doc_type.value if body.doc_type else None,
        tags=body.tags,
        date_from=body.date_from,
        date_to=body.date_to,
    )

    result: RAGResponse = await _pipeline.run(
        query=body.query,
        metadata_filter=metadata_filter or None,
    )

    return QueryResponse(
        query=result.query,
        answer=result.answer,
        citations=result.citations,
        cited_claims=result.cited_claims,
        faithfulness_score=result.faithfulness_score,
        ungrounded_claims=result.ungrounded_claims,
        retrieved_chunk_count=result.retrieved_chunk_count,
        chunks_passed_crag=result.chunks_passed_crag,
        decomposition=result.decomposition,
    )
