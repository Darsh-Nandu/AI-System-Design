"""Structured metadata pre-filter for Tier-1 card search.

Converts query constraints (jurisdiction, date range, doc_type, tags)
into Qdrant payload filters. Structured fields are evaluated exactly --
no embedding needed.
"""

from __future__ import annotations

from datetime import date
from typing import Any


def build_card_filter(
    jurisdiction: list[str] | None = None,
    doc_type: str | None = None,
    tags: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Return a dict that QdrantStore._build_filter can consume."""
    f: dict[str, Any] = {}

    if jurisdiction:
        f["jurisdiction"] = jurisdiction
    if doc_type:
        f["doc_type"] = doc_type
    if tags:
        f["tags"] = tags

    if date_from or date_to:
        date_range: dict[str, str] = {}
        if date_from:
            date_range["gte"] = date_from.isoformat()
        if date_to:
            date_range["lte"] = date_to.isoformat()
        f["date"] = date_range

    return f


def extract_filters_from_sub_query(metadata_filters: dict[str, Any]) -> dict[str, Any]:
    """Normalize sub-query metadata filters into the canonical filter dict format."""
    result: dict[str, Any] = {}
    for key, value in metadata_filters.items():
        if key in ("jurisdiction", "tags") and isinstance(value, str):
            result[key] = [value]
        else:
            result[key] = value
    return result
