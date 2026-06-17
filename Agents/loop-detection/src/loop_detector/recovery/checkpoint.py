"""Recovery Strategy 3: Human checkpoint queue.

After M consecutive loop detections, the full agent state (messages, tool
results, plan) is serialised and surfaced to a human review queue.
A human can edit the plan and resume -- the agent picks up from the
serialised state, not from scratch.
"""

from __future__ import annotations

import orjson

from loop_detector.logging import get_logger
from loop_detector.metrics import human_checkpoints_total
from loop_detector.models import AgentStep, DetectionResult, HumanCheckpoint
from loop_detector.storage.postgres import AsyncSessionFactory, HumanCheckpointORM

logger = get_logger(__name__)


async def create_human_checkpoint(
    session_id: str,
    step: int,
    result: DetectionResult,
    steps: list[AgentStep],
    full_state: dict,
) -> HumanCheckpoint:
    """Serialise the agent state and write it to the human review queue."""
    checkpoint = HumanCheckpoint(
        session_id=session_id,
        step=step,
        consecutive_detections=result.consecutive_detections,
        signals=result.signals,
        serialized_state={
            "step_history": [s.model_dump(mode="json") for s in steps[-30:]],
            "agent_state": full_state,
        },
    )

    async with AsyncSessionFactory() as session:
        orm = HumanCheckpointORM(
            id=checkpoint.id,
            session_id=session_id,
            step=step,
            consecutive_detections=result.consecutive_detections,
            signal_types=[s.signal_type.value for s in result.signals],
            serialized_state=checkpoint.serialized_state,
        )
        session.add(orm)
        await session.commit()

    human_checkpoints_total.inc()
    logger.warning(
        "human_checkpoint_created",
        session_id=session_id,
        step=step,
        consecutive=result.consecutive_detections,
        checkpoint_id=str(checkpoint.id),
    )
    return checkpoint


async def get_pending_checkpoints() -> list[HumanCheckpointORM]:
    from sqlalchemy import select
    from loop_detector.storage.postgres import HumanCheckpointORM

    async with AsyncSessionFactory() as session:
        rows = await session.scalars(
            select(HumanCheckpointORM)
            .where(HumanCheckpointORM.resolved_at == None)  # noqa: E711
            .order_by(HumanCheckpointORM.created_at)
        )
        return list(rows.all())


async def resolve_checkpoint(
    checkpoint_id: str,
    resolved_by: str,
    resolution_note: str,
) -> None:
    from datetime import datetime, timezone
    from sqlalchemy import update
    from loop_detector.storage.postgres import HumanCheckpointORM

    async with AsyncSessionFactory() as session:
        await session.execute(
            update(HumanCheckpointORM)
            .where(HumanCheckpointORM.id == checkpoint_id)
            .values(
                resolved_at=datetime.now(timezone.utc),
                resolved_by=resolved_by,
                resolution_note=resolution_note,
            )
        )
        await session.commit()
