"""POST /query -- clinical decision support query."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from medical_rag.models import MedicalRAGResponse, QueryRequest
from medical_rag.pipeline import query_patient

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=MedicalRAGResponse)
async def query(request: QueryRequest) -> MedicalRAGResponse:
    try:
        return await query_patient(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
