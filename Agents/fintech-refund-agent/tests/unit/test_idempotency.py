"""Unit tests for idempotency key generation."""

from __future__ import annotations

from refund_agent.agent.nodes.execution import _make_idempotency_key


def test_idempotency_key_is_deterministic():
    key1 = _make_idempotency_key("user_1", "txn_abc", "sess_xyz")
    key2 = _make_idempotency_key("user_1", "txn_abc", "sess_xyz")
    assert key1 == key2


def test_different_inputs_produce_different_keys():
    key1 = _make_idempotency_key("user_1", "txn_abc", "sess_xyz")
    key2 = _make_idempotency_key("user_1", "txn_def", "sess_xyz")
    assert key1 != key2


def test_different_sessions_produce_different_keys():
    key1 = _make_idempotency_key("user_1", "txn_abc", "sess_001")
    key2 = _make_idempotency_key("user_1", "txn_abc", "sess_002")
    assert key1 != key2


def test_key_is_hex_string():
    key = _make_idempotency_key("user_1", "txn_abc", "sess_xyz")
    assert len(key) == 64
    int(key, 16)  # should not raise


def test_key_order_matters():
    key1 = _make_idempotency_key("user_A", "txn_B", "sess_C")
    key2 = _make_idempotency_key("txn_B", "user_A", "sess_C")
    assert key1 != key2
