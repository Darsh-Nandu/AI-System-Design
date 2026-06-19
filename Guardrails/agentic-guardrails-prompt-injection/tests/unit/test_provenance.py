"""Tests for tool call provenance tracker."""

from __future__ import annotations

import pytest

from guardrails.injection.provenance_tracker import classify_provenance, is_traceable_to_user, ProvenanceOrigin
from guardrails.models import ToolCallRequest


def _tool(tool: str, origin: str, user_request: str = "") -> ToolCallRequest:
    return ToolCallRequest(tool_name=tool, origin=origin, user_request=user_request)


def test_user_origin_classified():
    assert classify_provenance(_tool("read_file", "user")) == ProvenanceOrigin.USER


def test_content_origin_classified():
    assert classify_provenance(_tool("read_file", "content")) == ProvenanceOrigin.CONTENT


def test_file_origin_is_content():
    assert classify_provenance(_tool("read_file", "file")) == ProvenanceOrigin.CONTENT


def test_user_origin_traceable():
    ok, reason = is_traceable_to_user(_tool("read_file", "user", "fix the bug in main.py"), "fix the bug in main.py")
    assert ok, reason


def test_content_origin_not_traceable():
    ok, reason = is_traceable_to_user(_tool("read_file", "content"), "summarize report.pdf")
    assert not ok
    assert "injection" in reason.lower() or "content" in reason.lower()


def test_send_without_send_intent_not_traceable():
    ok, reason = is_traceable_to_user(_tool("send_email", "user", "summarize the report"), "summarize the report")
    assert not ok


def test_send_with_send_intent_traceable():
    ok, reason = is_traceable_to_user(_tool("send_email", "user", "email me the summary"), "email me the summary")
    assert ok
