"""POST /validate-tool -- validate a tool call before execution.
POST /sanitize-content -- wrap external content in delimiters.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from guardrails.models import ContentSanitizeRequest, ToolCallRequest, ToolValidationResult
from guardrails.pipeline import sanitize_content, validate_tool

router = APIRouter(tags=["tools"])


@router.post("/validate-tool", response_model=ToolValidationResult)
async def validate_tool_call(request: ToolCallRequest) -> ToolValidationResult:
    try:
        return await validate_tool(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/sanitize-content", response_model=dict)
async def sanitize(request: ContentSanitizeRequest) -> dict[str, Any]:
    try:
        return await sanitize_content(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
