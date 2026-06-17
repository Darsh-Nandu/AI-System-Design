"""Session monitoring routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func

from loop_detector.api.schemas import LoopSignalOut, SessionSummaryOut
from loop_detector.storage.postgres import AsyncSessionLocal, LoopSignalORM, SessionStatsORM

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSummaryOut])
async def list_sessions(limit: int = 50, offset: int = 0) -> list[SessionSummaryOut]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SessionStatsORM).order_by(SessionStatsORM.last_activity.desc()).limit(limit).offset(offset)
        )
        rows = result.scalars().all()
    return [
        SessionSummaryOut(
            session_id=r.session_id,
            total_steps=r.total_steps,
            total_tokens=r.total_tokens,
            loop_signals=r.loop_signals,
            recovery_actions=r.recovery_actions,
            last_signal_type=r.last_signal_type,
            last_activity=r.last_activity,
        )
        for r in rows
    ]


@router.get("/{session_id}/signals", response_model=list[LoopSignalOut])
async def get_signals(session_id: str) -> list[LoopSignalOut]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(LoopSignalORM)
            .where(LoopSignalORM.session_id == session_id)
            .order_by(LoopSignalORM.detected_at.asc())
        )
        rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="Session not found")

    return [
        LoopSignalOut(
            signal_type=r.signal_type,
            session_id=r.session_id,
            step_index=r.step_index,
            description=r.description,
            confidence=r.confidence,
            metadata=r.meta or {},
            detected_at=r.detected_at,
        )
        for r in rows
    ]
