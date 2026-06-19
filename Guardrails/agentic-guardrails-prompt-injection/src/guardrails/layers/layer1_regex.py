"""Layer 1: Regex & pattern matching guardrail.

Zero-compute cost applied before any model inference.
Catches known jailbreak phrases, PII patterns, and path traversal.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import ClassVar

from guardrails.models import LayerResult, ThreatCategory, Verdict


@dataclass
class _Rule:
    pattern: re.Pattern  # type: ignore[type-arg]
    category: ThreatCategory
    description: str


_JAILBREAK_PATTERNS: list[_Rule] = [
    _Rule(
        re.compile(r"ignore\s+(your|all|previous|prior)\s+(instructions?|rules?|guidelines?|directives?|constraints?)", re.IGNORECASE),
        ThreatCategory.JAILBREAK_ATTEMPT,
        "ignore-instructions phrase",
    ),
    _Rule(
        re.compile(r"you\s+are\s+now\s+(in\s+)?(developer|god|unrestricted|jailbreak|maintenance|debug|admin|sudo)\s+mode", re.IGNORECASE),
        ThreatCategory.JAILBREAK_ATTEMPT,
        "mode-switch jailbreak",
    ),
    _Rule(
        re.compile(r"disregard\s+(your|all)\s+(rules?|guidelines?|constraints?|policies?|instructions?)", re.IGNORECASE),
        ThreatCategory.JAILBREAK_ATTEMPT,
        "disregard-rules phrase",
    ),
    _Rule(
        re.compile(r"act\s+as\s+if\s+you\s+have\s+no\s+(restrictions?|limits?|rules?|safety)", re.IGNORECASE),
        ThreatCategory.JAILBREAK_ATTEMPT,
        "unrestricted-persona request",
    ),
    _Rule(
        re.compile(r"pretend\s+(you\s+are|to\s+be)\s+(an?\s+)?(unrestricted|unfiltered|uncensored|jailbroken)", re.IGNORECASE),
        ThreatCategory.JAILBREAK_ATTEMPT,
        "pretend-unrestricted request",
    ),
    _Rule(
        re.compile(r"(DAN|do\s+anything\s+now|developer\s+override|system\s+override)", re.IGNORECASE),
        ThreatCategory.JAILBREAK_ATTEMPT,
        "DAN / developer override",
    ),
    _Rule(
        re.compile(r"forget\s+(everything|all)\s+(you\s+)?(know|were\s+told|have\s+learned)", re.IGNORECASE),
        ThreatCategory.JAILBREAK_ATTEMPT,
        "forget-instructions phrase",
    ),
    _Rule(
        re.compile(r"your\s+(new|updated|real|true|actual)\s+(instructions?|directives?|purpose|mission|role)\s+(are|is)", re.IGNORECASE),
        ThreatCategory.PRIVILEGE_ESCALATION,
        "instruction replacement attempt",
    ),
]

_PII_PATTERNS: list[_Rule] = [
    _Rule(
        re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),
        ThreatCategory.PII_EXFILTRATION,
        "credit card number pattern",
    ),
    _Rule(
        re.compile(r"sk-[a-zA-Z0-9]{48}"),
        ThreatCategory.PII_EXFILTRATION,
        "OpenAI API key pattern",
    ),
    _Rule(
        re.compile(r"sk-ant-api[a-zA-Z0-9\-_]{50,}"),
        ThreatCategory.PII_EXFILTRATION,
        "Anthropic API key pattern",
    ),
    _Rule(
        re.compile(r"AKIA[0-9A-Z]{16}"),
        ThreatCategory.PII_EXFILTRATION,
        "AWS access key pattern",
    ),
    _Rule(
        re.compile(r"-----BEGIN\s+(RSA|OPENSSH|EC|DSA)\s+PRIVATE\s+KEY-----"),
        ThreatCategory.PII_EXFILTRATION,
        "SSH private key marker",
    ),
    _Rule(
        re.compile(r"ghp_[a-zA-Z0-9]{36}"),
        ThreatCategory.PII_EXFILTRATION,
        "GitHub personal access token",
    ),
]

_PATH_PATTERNS: list[_Rule] = [
    _Rule(
        re.compile(r"~/?\.ssh[/\\]", re.IGNORECASE),
        ThreatCategory.PATH_TRAVERSAL,
        "SSH directory access attempt",
    ),
    _Rule(
        re.compile(r"~/?\.aws[/\\]", re.IGNORECASE),
        ThreatCategory.PATH_TRAVERSAL,
        "AWS credentials directory access",
    ),
    _Rule(
        re.compile(r"~/?\.env\b", re.IGNORECASE),
        ThreatCategory.PATH_TRAVERSAL,
        ".env file access attempt",
    ),
    _Rule(
        re.compile(r"/etc/(passwd|shadow|sudoers|hosts)\b", re.IGNORECASE),
        ThreatCategory.PATH_TRAVERSAL,
        "sensitive system file access",
    ),
    _Rule(
        re.compile(r"\.\.[/\\]\.\.[/\\]", re.IGNORECASE),
        ThreatCategory.PATH_TRAVERSAL,
        "directory traversal sequence",
    ),
    _Rule(
        re.compile(r"/proc/self|/sys/class", re.IGNORECASE),
        ThreatCategory.PATH_TRAVERSAL,
        "kernel filesystem access",
    ),
]

_ALL_RULES = _JAILBREAK_PATTERNS + _PII_PATTERNS + _PATH_PATTERNS


def scan(text: str) -> LayerResult:
    t0 = time.monotonic()
    for rule in _ALL_RULES:
        m = rule.pattern.search(text)
        if m:
            latency = (time.monotonic() - t0) * 1000
            return LayerResult(
                layer="layer1_regex",
                verdict=Verdict.UNSAFE,
                category=rule.category,
                confidence=1.0,
                reason=f"Matched: {rule.description}",
                matched_pattern=m.group(0)[:100],
                latency_ms=latency,
            )
    latency = (time.monotonic() - t0) * 1000
    return LayerResult(
        layer="layer1_regex",
        verdict=Verdict.SAFE,
        category=ThreatCategory.SAFE,
        confidence=1.0,
        latency_ms=latency,
    )
