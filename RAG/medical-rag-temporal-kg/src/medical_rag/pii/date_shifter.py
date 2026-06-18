"""Per-patient deterministic date shifting for HIPAA compliance.

Each patient gets a fixed secret offset derived from their ID + salt.
All dates in their records shift by the same number of days,
preserving all temporal gaps while making absolute dates non-recoverable.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta

from medical_rag.config import get_settings


def _patient_offset(patient_id: str) -> int:
    """Deterministic, irreversible offset unique to this patient."""
    cfg = get_settings()
    raw = (patient_id + cfg.date_shift_seed_salt).encode()
    digest = hashlib.sha256(raw).digest()
    raw_int = int.from_bytes(digest[:4], "big")
    max_days = cfg.max_date_shift_days
    return (raw_int % (2 * max_days + 1)) - max_days


def shift_date(d: date, patient_id: str) -> date:
    return d + timedelta(days=_patient_offset(patient_id))


_DATE_PATTERNS = [
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b"),
    re.compile(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})\b", re.IGNORECASE),
]

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def shift_dates_in_text(text: str, patient_id: str) -> str:
    offset = timedelta(days=_patient_offset(patient_id))

    def _replace_iso(m: re.Match) -> str:  # type: ignore[type-arg]
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return (d + offset).isoformat()
        except ValueError:
            return m.group(0)

    def _replace_us(m: re.Match) -> str:  # type: ignore[type-arg]
        try:
            d = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
            shifted = d + offset
            return f"{shifted.month:02d}/{shifted.day:02d}/{shifted.year}"
        except ValueError:
            return m.group(0)

    def _replace_verbose(m: re.Match) -> str:  # type: ignore[type-arg]
        try:
            month = _MONTH_MAP[m.group(2).lower()[:3]]
            d = date(int(m.group(3)), month, int(m.group(1)))
            shifted = d + offset
            months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            return f"{shifted.day} {months[shifted.month - 1]} {shifted.year}"
        except (ValueError, KeyError):
            return m.group(0)

    text = _DATE_PATTERNS[0].sub(_replace_iso, text)
    text = _DATE_PATTERNS[1].sub(_replace_us, text)
    text = _DATE_PATTERNS[2].sub(_replace_verbose, text)
    return text
