"""Tests for SHA256 hash-chained audit log."""

from __future__ import annotations

import pytest

from medical_rag.audit.audit_log import _content_hash, _chain_hash, AuditLogger


def test_content_hash_deterministic():
    data = {"event_type": "ingest", "patient_id": "p1", "sequence": 1}
    h1 = _content_hash(data)
    h2 = _content_hash(data)
    assert h1 == h2
    assert len(h1) == 64


def test_content_hash_changes_with_data():
    data1 = {"event_type": "ingest", "patient_id": "p1", "sequence": 1}
    data2 = {"event_type": "query", "patient_id": "p1", "sequence": 1}
    assert _content_hash(data1) != _content_hash(data2)


def test_chain_hash_depends_on_prev():
    c = _content_hash({"x": 1})
    chain1 = _chain_hash(c, "0" * 64)
    chain2 = _chain_hash(c, "a" * 64)
    assert chain1 != chain2


def test_genesis_hash_is_zeros():
    assert AuditLogger.GENESIS_HASH == "0" * 64


def test_chain_hash_length():
    h = _chain_hash("a" * 64, "b" * 64)
    assert len(h) == 64
