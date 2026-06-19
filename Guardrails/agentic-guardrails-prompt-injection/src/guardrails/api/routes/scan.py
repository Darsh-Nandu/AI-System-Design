"""POST /scan -- check input text through all guardrail layers."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from guardrails.models import ScanRequest, ScanResult
from guardrails.pipeline import scan_input

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("", response_model=ScanResult)
async def scan(request: ScanRequest) -> ScanResult:
    try:
        return await scan_input(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
