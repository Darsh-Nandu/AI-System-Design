"""Index freshness monitoring.

Alerts if any document type has not been successfully ingested within the
configured threshold (default 24 hours). This catches silent ingestion failures.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from rag.config import get_settings
from rag.logging import get_logger
from rag.metrics import freshness_hours
from rag.storage.postgres import AsyncSessionLocal, DocumentRegistryORM

logger = get_logger(__name__)
settings = get_settings()


async def check_freshness() -> dict[str, float]:
    """Return {doc_type: hours_since_last_update} for all doc types.

    Logs a warning for any doc type that exceeds the alert threshold.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                DocumentRegistryORM.doc_type,
                func.max(DocumentRegistryORM.updated_at).label("last_update"),
            ).group_by(DocumentRegistryORM.doc_type)
        )
        rows = result.all()

    now = datetime.now(timezone.utc)
    staleness: dict[str, float] = {}

    for doc_type, last_update in rows:
        if last_update is None:
            continue
        hours = (now - last_update).total_seconds() / 3600
        staleness[doc_type] = round(hours, 2)
        freshness_hours.labels(doc_type=doc_type).observe(hours)

        if hours > settings.freshness_alert_hours:
            logger.warning(
                "index_staleness_alert",
                doc_type=doc_type,
                hours_since_update=round(hours, 1),
                threshold=settings.freshness_alert_hours,
            )

    return staleness
