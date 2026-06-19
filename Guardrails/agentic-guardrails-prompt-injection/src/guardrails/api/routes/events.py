"""GET /events -- security event log."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from guardrails.audit.security_log import list_events

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[dict[str, Any]])
async def get_events(
    severity: str | None = Query(default=None, description="Filter by severity: LOW, MEDIUM, HIGH, CRITICAL"),
    attack_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await list_events(severity=severity, attack_type=attack_type, limit=limit)
