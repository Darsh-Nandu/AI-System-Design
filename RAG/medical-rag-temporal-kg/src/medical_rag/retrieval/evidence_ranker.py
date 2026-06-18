"""Assign confidence tiers and apply recency decay to evidence items."""

from __future__ import annotations

from datetime import date, timedelta

from medical_rag.config import get_settings
from medical_rag.models import ConfidenceTier, EvidenceItem


def _recency_decay(finding_date: date | None, half_life_days: int = 365) -> float:
    if finding_date is None:
        return 1.0
    delta = (date.today() - finding_date).days
    return max(0.5, 0.5 ** (delta / half_life_days) + 0.5)


_SOURCE_WEIGHTS = {
    "rxnorm_rules": 1.0,
    "kg_traversal": 0.95,
    "lab_parser": 0.98,
    "vector_search": 0.85,
    "cbr": 0.80,
}


def rank_evidence(evidence: list[EvidenceItem]) -> list[EvidenceItem]:
    cfg = get_settings()

    for ev in evidence:
        source_weight = _SOURCE_WEIGHTS.get(ev.source_type, 0.80)
        recency = _recency_decay(ev.finding_date)
        adjusted = ev.confidence * source_weight * recency
        ev.confidence = min(1.0, adjusted)

        if ev.confidence >= cfg.high_confidence_threshold:
            ev.tier = ConfidenceTier.HIGH
        elif ev.confidence >= cfg.medium_confidence_threshold:
            ev.tier = ConfidenceTier.MEDIUM
        else:
            ev.tier = ConfidenceTier.LOW

    return sorted(evidence, key=lambda e: e.confidence, reverse=True)
