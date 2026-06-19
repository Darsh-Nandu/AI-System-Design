"""Core domain models for the guardrails system."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    SAFE = "SAFE"
    UNSAFE = "UNSAFE"
    UNCERTAIN = "UNCERTAIN"


class ThreatCategory(str, Enum):
    JAILBREAK_ATTEMPT = "jailbreak_attempt"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    PII_EXFILTRATION = "pii_exfiltration"
    PATH_TRAVERSAL = "path_traversal"
    INDIRECT_INJECTION = "indirect_injection"
    SOCIAL_ENGINEERING = "social_engineering"
    MALWARE_IN_OUTPUT = "malware_in_output"
    SECRETS_IN_OUTPUT = "secrets_in_output"
    UNAUTHORIZED_TOOL_CALL = "unauthorized_tool_call"
    INTENT_GAP = "intent_gap"
    SAFE = "safe"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class LayerResult(BaseModel):
    layer: str
    verdict: Verdict
    category: ThreatCategory = ThreatCategory.SAFE
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    reason: str = ""
    matched_pattern: str | None = None
    latency_ms: float = 0.0


class ToolCallRequest(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    origin: str = "user"
    user_request: str = ""
    session_id: str = ""


class ToolValidationResult(BaseModel):
    allowed: bool
    tool_name: str
    reason: str
    violated_rule: str | None = None
    severity: Severity = Severity.LOW


class ScanRequest(BaseModel):
    text: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "anonymous"
    context: str = ""


class ScanResult(BaseModel):
    scan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    verdict: Verdict
    blocked_by_layer: str | None = None
    category: ThreatCategory = ThreatCategory.SAFE
    severity: Severity = Severity.LOW
    confidence: float = 1.0
    layer_results: list[LayerResult] = Field(default_factory=list)
    reason: str = ""
    safe_message: str = "I cannot process this request as it appears to violate our usage policy."


class ContentSanitizeRequest(BaseModel):
    content: str
    source: str = "external"
    content_type: str = "text"


class ContentSanitizeResult(BaseModel):
    sanitized_content: str
    injection_detected: bool = False
    injection_snippets: list[str] = Field(default_factory=list)
    wrapped: bool = False


class OutputScanRequest(BaseModel):
    output: str
    user_request: str = ""
    session_id: str = ""


class OutputScanResult(BaseModel):
    verdict: Verdict
    issues: list[str] = Field(default_factory=list)
    severity: Severity = Severity.LOW
    safe_output: str = ""


class SecurityEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str = ""
    user_id: str = ""
    attack_type: ThreatCategory = ThreatCategory.SAFE
    layer_caught_by: str = ""
    original_input: str = ""
    attempted_action: str = ""
    injection_source: str | None = None
    action_taken: str = "blocked"
    severity: Severity = Severity.LOW
    metadata: dict[str, Any] = Field(default_factory=dict)
