"""POST /ingest -- ingest patient documents."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from medical_rag.api.schemas import IngestOut
from medical_rag.models import IngestRequest
from medical_rag.pipeline import ingest_patient

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=IngestOut, status_code=202)
async def ingest(request: IngestRequest) -> IngestOut:
    try:
        result = await ingest_patient(request)
        return IngestOut(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
