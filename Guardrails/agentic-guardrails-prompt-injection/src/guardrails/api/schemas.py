"""API response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HealthOut(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    timestamp: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
