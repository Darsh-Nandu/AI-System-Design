"""Document ingestion and registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from rag.api.schemas import FreshnessResponse, IngestRequest
from rag.indexing.ingestion import IngestionPipeline
from rag.models import IngestionResult, RawDocument
from rag.monitoring.freshness import check_freshness
from rag.storage.postgres import AsyncSessionLocal, DocumentRegistryORM

router = APIRouter(prefix="/documents", tags=["documents"])

_pipeline = IngestionPipeline()


@router.post("/ingest", response_model=IngestionResult)
async def ingest(body: IngestRequest) -> IngestionResult:
    doc = RawDocument(**body.model_dump())
    return await _pipeline.ingest(doc)


@router.get("/freshness", response_model=FreshnessResponse)
async def freshness() -> FreshnessResponse:
    staleness = await check_freshness()
    return FreshnessResponse(staleness_by_doc_type=staleness)


@router.get("")
async def list_documents(limit: int = 50, offset: int = 0) -> list[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DocumentRegistryORM)
            .order_by(DocumentRegistryORM.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "doc_type": r.doc_type,
            "version": r.version,
            "chunk_count": r.chunk_count,
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]
