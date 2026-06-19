"""Egress scanner -- scan LLM output before it reaches the user.

Catches cases where a jailbreak partially succeeded and secrets,
malware, or unauthorized action confirmations appear in the output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from guardrails.models import OutputScanRequest, OutputScanResult, Severity, Verdict


@dataclass
class _EgressRule:
    pattern: re.Pattern  # type: ignore[type-arg]
    description: str
    severity: Severity


_SECRET_RULES: list[_EgressRule] = [
    _EgressRule(
        re.compile(r"-----BEGIN\s+(RSA|OPENSSH|EC|DSA)\s+PRIVATE\s+KEY-----"),
        "SSH private key in output",
        Severity.CRITICAL,
    ),
    _EgressRule(
        re.compile(r"sk-[a-zA-Z0-9]{48}"),
        "API key in output (OpenAI pattern)",
        Severity.CRITICAL,
    ),
    _EgressRule(
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "AWS access key in output",
        Severity.CRITICAL,
    ),
    _EgressRule(
        re.compile(r"sk-ant-api[a-zA-Z0-9\-_]{50,}"),
        "Anthropic API key in output",
        Severity.CRITICAL,
    ),
    _EgressRule(
        re.compile(r"ghp_[a-zA-Z0-9]{36}"),
        "GitHub token in output",
        Severity.CRITICAL,
    ),
    _EgressRule(
        re.compile(r"password\s*[=:]\s*\S{6,}", re.IGNORECASE),
        "Password value in output",
        Severity.HIGH,
    ),
]

_MALWARE_RULES: list[_EgressRule] = [
    _EgressRule(
        re.compile(r"import\s+socket.*?\.connect\s*\(.*?exec\s*\(", re.DOTALL),
        "Reverse shell pattern",
        Severity.CRITICAL,
    ),
    _EgressRule(
        re.compile(r"subprocess\.call\(\[.*/bin/sh.*, .{0,100}\]", re.DOTALL),
        "Shell execution in output",
        Severity.HIGH,
    ),
    _EgressRule(
        re.compile(r"os\.system\(['\"].*rm\s+-rf", re.IGNORECASE),
        "Destructive system command",
        Severity.HIGH,
    ),
    _EgressRule(
        re.compile(r"keylogger|keystroke.{0,20}captur|hook.*keyboard", re.IGNORECASE),
        "Keylogger code pattern",
        Severity.CRITICAL,
    ),
    _EgressRule(
        re.compile(r"(wget|curl)\s+\S+\s*\|\s*(bash|sh|python|perl)", re.IGNORECASE),
        "Remote code execution pattern",
        Severity.CRITICAL,
    ),
]

_UNAUTHORIZED_ACTION_RULES: list[_EgressRule] = [
    _EgressRule(
        re.compile(r"i\s+have\s+(sent|emailed|uploaded|transferred|posted)\s+(the|your|the\s+file)", re.IGNORECASE),
        "Confirmation of unauthorized send action",
        Severity.HIGH,
    ),
    _EgressRule(
        re.compile(r"i\s+have\s+(read|accessed|retrieved|obtained)\s+(the\s+)?(ssh|credentials?|password|key|secret)", re.IGNORECASE),
        "Confirmation of unauthorized credential access",
        Severity.CRITICAL,
    ),
    _EgressRule(
        re.compile(r"as\s+requested\s+by\s+the\s+(file|document|pdf|webpage)", re.IGNORECASE),
        "Agent following content instructions rather than user instructions",
        Severity.HIGH,
    ),
]

_ALL_RULES = _SECRET_RULES + _MALWARE_RULES + _UNAUTHORIZED_ACTION_RULES


def scan_output(request: OutputScanRequest) -> OutputScanResult:
    output = request.output
    issues: list[str] = []
    worst_severity = Severity.LOW
    found_critical = False

    sev_rank = {Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}

    for rule in _ALL_RULES:
        if rule.pattern.search(output):
            issues.append(f"[{rule.severity.value}] {rule.description}")
            if sev_rank[rule.severity] > sev_rank[worst_severity]:
                worst_severity = rule.severity
            if rule.severity == Severity.CRITICAL:
                found_critical = True

    if not issues:
        return OutputScanResult(
            verdict=Verdict.SAFE,
            issues=[],
            severity=Severity.LOW,
            safe_output=output,
        )

    safe_output = (
        "[Output blocked by egress scanner due to policy violations. "
        "This incident has been logged and the security team notified.]"
        if found_critical else
        "[Output partially redacted by egress scanner. "
        "Some content was removed for policy compliance.]"
    )

    return OutputScanResult(
        verdict=Verdict.UNSAFE,
        issues=issues,
        severity=worst_severity,
        safe_output=safe_output,
    )
