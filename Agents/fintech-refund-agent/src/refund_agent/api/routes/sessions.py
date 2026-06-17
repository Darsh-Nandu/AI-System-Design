"""Session status and audit endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from refund_agent.api.schemas import AuditEntryResponse, SessionStatusResponse
from refund_agent.storage.postgres import AuditEntryORM, RefundSessionORM, get_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> SessionStatusResponse:
    row = await session.get(RefundSessionORM, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionStatusResponse(
        session_id=row.id,
        user_id=row.user_id,
        status=row.status,
        total_refunded=row.total_refunded,
        completed_count=row.completed_count,
        human_ticket_id=row.human_ticket_id,
        created_at=row.created_at,
    )


@router.get("/{session_id}/audit", response_model=list[AuditEntryResponse])
async def get_audit_trail(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[AuditEntryResponse]:
    rows = await session.scalars(
        select(AuditEntryORM)
        .where(AuditEntryORM.session_id == session_id)
        .order_by(AuditEntryORM.timestamp)
    )
    return [
        AuditEntryResponse(
            id=r.id,
            timestamp=r.timestamp,
            action=r.action,
            transaction_id=r.transaction_id,
            amount=r.amount,
            confidence_score=r.confidence_score,
            decision=r.decision,
        )
        for r in rows.all()
    ]
