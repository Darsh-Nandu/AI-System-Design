"""GET /audit -- audit log endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from medical_rag.api.schemas import AuditVerifyOut
from medical_rag.audit.audit_log import get_audit_logger

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/entries", response_model=list[dict[str, Any]])
async def list_entries(
    patient_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await get_audit_logger().list_entries(patient_id=patient_id, limit=limit)


@router.get("/verify", response_model=AuditVerifyOut)
async def verify_chain(limit: int = Query(default=1000, ge=1, le=10000)) -> AuditVerifyOut:
    ok, violations = await get_audit_logger().verify_chain(limit=limit)
    return AuditVerifyOut(chain_ok=ok, violations=violations, entries_checked=limit)
