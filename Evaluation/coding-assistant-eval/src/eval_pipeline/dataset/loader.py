"""Load and query production log entries from Postgres."""

from __future__ import annotations

import json
from typing import AsyncIterator

from sqlalchemy import select

from eval_pipeline.models import ImplicitSignals, LogEntry, TaskType, TestCase
from eval_pipeline.storage.postgres import AsyncSessionLocal, LogEntryORM


async def iter_log_entries(
    task_type: TaskType | None = None,
    limit: int = 10_000,
) -> AsyncIterator[LogEntry]:
    """Stream log entries from the database."""
    async with AsyncSessionLocal() as db:
        q = select(LogEntryORM).limit(limit).order_by(LogEntryORM.created_at.desc())
        if task_type is not None:
            q = q.where(LogEntryORM.task_type == task_type.value)
        result = await db.execute(q)
        rows = result.scalars().all()

    for row in rows:
        yield _orm_to_model(row)


async def get_log_entry(entry_id: str) -> LogEntry | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(LogEntryORM).where(LogEntryORM.id == entry_id))
        row = result.scalar_one_or_none()
    return _orm_to_model(row) if row else None


async def insert_log_entry(entry: LogEntry) -> None:
    async with AsyncSessionLocal() as db:
        orm = LogEntryORM(
            id=entry.id,
            prompt=entry.prompt,
            old_model_output=entry.old_model_output,
            task_type=entry.task_type.value,
            language=entry.language,
            implicit_signals=entry.implicit_signals.model_dump(),
            test_cases=[tc.model_dump() for tc in entry.test_cases],
            repo_path=entry.repo_path,
            bug_description=entry.bug_description,
            ground_truth_patch=entry.ground_truth_patch,
            reference_explanation=entry.reference_explanation,
            raw_code=entry.raw_code,
        )
        db.add(orm)
        await db.commit()


def _orm_to_model(row: LogEntryORM) -> LogEntry:
    signals = row.implicit_signals or {}
    test_cases = row.test_cases or []
    return LogEntry(
        id=row.id,
        prompt=row.prompt,
        old_model_output=row.old_model_output,
        task_type=TaskType(row.task_type),
        language=row.language or "python",
        implicit_signals=ImplicitSignals(**signals),
        test_cases=[TestCase(**tc) for tc in test_cases],
        repo_path=row.repo_path,
        bug_description=row.bug_description,
        ground_truth_patch=row.ground_truth_patch,
        reference_explanation=row.reference_explanation,
        raw_code=row.raw_code,
    )
