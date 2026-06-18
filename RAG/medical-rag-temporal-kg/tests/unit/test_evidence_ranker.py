"""Tests for evidence ranking and confidence tier assignment."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from medical_rag.models import ConfidenceTier, EvidenceItem
from medical_rag.retrieval.evidence_ranker import rank_evidence, _recency_decay


def _make_ev(score: float, source: str = "vector_search", days_old: int = 0) -> EvidenceItem:
    finding_date = date.today() - timedelta(days=days_old)
    return EvidenceItem(
        source_type=source,
        source_id="test",
        content="test content",
        confidence=score,
        finding_date=finding_date,
    )


def test_high_tier_assigned():
    ev = _make_ev(0.95, source="rxnorm_rules")
    ranked = rank_evidence([ev])
    assert ranked[0].tier == ConfidenceTier.HIGH


def test_low_tier_for_weak_evidence():
    ev = _make_ev(0.40, source="vector_search")
    ranked = rank_evidence([ev])
    assert ranked[0].tier == ConfidenceTier.LOW


def test_sorted_descending():
    evs = [_make_ev(0.5), _make_ev(0.9), _make_ev(0.3), _make_ev(0.7)]
    ranked = rank_evidence(evs)
    scores = [e.confidence for e in ranked]
    assert scores == sorted(scores, reverse=True)


def test_recency_decay_reduces_score():
    recent = _recency_decay(date.today())
    old = _recency_decay(date.today() - timedelta(days=730))
    assert recent > old


def test_rxnorm_weighted_higher_than_vector():
    rxnorm_ev = _make_ev(0.80, source="rxnorm_rules")
    vector_ev = _make_ev(0.80, source="vector_search")
    ranked = rank_evidence([vector_ev, rxnorm_ev])
    assert ranked[0].source_type == "rxnorm_rules"
