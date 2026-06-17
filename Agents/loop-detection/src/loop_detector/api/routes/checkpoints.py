"""Human checkpoint management routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from loop_detector.api.schemas import CheckpointOut, ResolveCheckpointRequest
from loop_detector.recovery.checkpoint import resolve_checkpoint
from loop_detector.storage.postgres import AsyncSessionLocal, HumanCheckpointORM

router = APIRouter(prefix="/checkpoints", tags=["checkpoints"])


@router.get("", response_model=list[CheckpointOut])
async def list_checkpoints(resolved: bool | None = None, limit: int = 50) -> list[CheckpointOut]:
    async with AsyncSessionLocal() as db:
        q = select(HumanCheckpointORM).order_by(HumanCheckpointORM.created_at.desc()).limit(limit)
        if resolved is not None:
            q = q.where(HumanCheckpointORM.resolved == resolved)
        result = await db.execute(q)
        rows = result.scalars().all()
    return [
        CheckpointOut(
            id=r.id,
            session_id=r.session_id,
            reason=r.reason,
            context=r.context or {},
            resolved=r.resolved,
            created_at=r.created_at,
            resolved_at=r.resolved_at,
        )
        for r in rows
    ]


@router.post("/{checkpoint_id}/resolve", response_model=CheckpointOut)
async def resolve(checkpoint_id: UUID, body: ResolveCheckpointRequest) -> CheckpointOut:
    updated = await resolve_checkpoint(str(checkpoint_id), body.resolution_note)
    if updated is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return CheckpointOut(
        id=updated.id,
        session_id=updated.session_id,
        reason=updated.reason,
        context=updated.context or {},
        resolved=updated.resolved,
        created_at=updated.created_at,
        resolved_at=updated.resolved_at,
    )
