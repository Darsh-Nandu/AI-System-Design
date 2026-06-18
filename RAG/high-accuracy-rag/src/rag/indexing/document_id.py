"""Deterministic hierarchical document ID generation.

Format: {country}:{state}:{district}:{year}:{doc_type}:{serial}:v{version}

Example: IN:MH:MUM:2019:CR:4821:v1

Properties:
- Upsert-based: amending a document increments version, old chunks replaced atomically
- Namespace filtering: search only MH cases by filtering prefix IN:MH
- Audit trail: every version is traceable
"""

from __future__ import annotations

import re

from rag.models import DocType, RawDocument


_DOC_TYPE_CODE: dict[DocType, str] = {
    DocType.CASE_LAW: "CR",
    DocType.STATUTE: "ST",
    DocType.REGULATION: "RG",
    DocType.CONTRACT: "CN",
    DocType.ADVISORY: "AV",
}

_SAFE_RE = re.compile(r"[^A-Z0-9]")


def _normalise(part: str) -> str:
    return _SAFE_RE.sub("", part.upper())[:8]


def make_document_id(doc: RawDocument) -> str:
    country = _normalise(doc.country_code)
    state = _normalise(doc.state_code)
    district = _normalise(doc.district_code)
    year = str(doc.year)
    type_code = _DOC_TYPE_CODE.get(doc.doc_type, "XX")
    serial = _normalise(doc.serial)
    return f"{country}:{state}:{district}:{year}:{type_code}:{serial}:v{doc.version}"


def make_chunk_id(document_id: str, chunk_index: int) -> str:
    return f"{document_id}:{chunk_index:04d}"


def base_id_without_version(document_id: str) -> str:
    """Strip :v{n} suffix to get the canonical base ID for upsert lookups."""
    parts = document_id.rsplit(":v", 1)
    return parts[0]


def bump_version(document_id: str) -> str:
    """Return a new document ID with version incremented by 1."""
    parts = document_id.rsplit(":v", 1)
    if len(parts) == 2:
        try:
            v = int(parts[1]) + 1
            return f"{parts[0]}:v{v}"
        except ValueError:
            pass
    return f"{document_id}:v2"
