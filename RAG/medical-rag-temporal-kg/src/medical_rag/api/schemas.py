"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HealthOut(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    timestamp: datetime = None  # type: ignore[assignment]

    def model_post_init(self, __context: Any) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class IngestOut(BaseModel):
    patient_id: str
    findings_ingested: int
    message: str = "Ingestion complete"


class AuditVerifyOut(BaseModel):
    chain_ok: bool
    violations: list[str]
    entries_checked: int
