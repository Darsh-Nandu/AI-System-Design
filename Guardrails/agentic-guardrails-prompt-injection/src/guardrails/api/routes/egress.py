"""POST /scan-output -- egress scan on LLM output."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from guardrails.models import OutputScanRequest
from guardrails.pipeline import scan_egress

router = APIRouter(tags=["egress"])


@router.post("/scan-output", response_model=dict)
async def scan_output_route(request: OutputScanRequest) -> dict[str, Any]:
    try:
        return await scan_egress(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
