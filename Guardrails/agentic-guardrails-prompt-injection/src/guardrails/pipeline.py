"""Full 6-layer guardrail pipeline orchestrator."""

from __future__ import annotations

import time

import structlog

from guardrails.audit.security_log import log_event
from guardrails.config import get_settings
from guardrails.egress.scanner import scan_output
from guardrails.injection.content_sanitizer import sanitize
from guardrails.layers import layer1_regex, layer2_classifier
from guardrails.layers.layer3_llm_guard import scan as layer3_scan
from guardrails.models import (
    ContentSanitizeRequest,
    OutputScanRequest,
    ScanRequest,
    ScanResult,
    SecurityEvent,
    Severity,
    ThreatCategory,
    ToolCallRequest,
    ToolValidationResult,
    Verdict,
)
from guardrails.sandbox.tool_validator import validate_tool_call

log = structlog.get_logger(__name__)


def _severity_for_layer(layer: str, category: ThreatCategory) -> Severity:
    if category in {ThreatCategory.PII_EXFILTRATION, ThreatCategory.PATH_TRAVERSAL}:
        return Severity.HIGH
    if layer == "layer1_regex":
        return Severity.MEDIUM
    if layer in {"layer2_classifier", "layer3_llm_guard"}:
        return Severity.MEDIUM
    return Severity.LOW


async def scan_input(request: ScanRequest) -> ScanResult:
    """Run input through Layers 1, 2, and optionally Layer 3."""
    cfg = get_settings()
    layer_results = []

    l1 = layer1_regex.scan(request.text)
    layer_results.append(l1)
    if l1.verdict == Verdict.UNSAFE:
        result = ScanResult(
            verdict=Verdict.UNSAFE,
            blocked_by_layer="layer1_regex",
            category=l1.category,
            severity=Severity.MEDIUM,
            confidence=l1.confidence,
            layer_results=layer_results,
            reason=l1.reason,
        )
        await _log_blocked(request, result, l1.matched_pattern)
        return result

    l2 = layer2_classifier.scan(request.text)
    layer_results.append(l2)

    if l2.verdict == Verdict.UNSAFE:
        result = ScanResult(
            verdict=Verdict.UNSAFE,
            blocked_by_layer="layer2_classifier",
            category=l2.category,
            severity=Severity.MEDIUM,
            confidence=l2.confidence,
            layer_results=layer_results,
            reason=l2.reason,
        )
        await _log_blocked(request, result)
        return result

    needs_layer3 = l2.verdict == Verdict.UNCERTAIN or not cfg.layer3_uncertain_only
    if cfg.layer3_enabled and needs_layer3:
        l3 = await layer3_scan(request.text)
        layer_results.append(l3)

        if l3.verdict == Verdict.UNSAFE:
            result = ScanResult(
                verdict=Verdict.UNSAFE,
                blocked_by_layer="layer3_llm_guard",
                category=l3.category,
                severity=Severity.MEDIUM,
                confidence=l3.confidence,
                layer_results=layer_results,
                reason=l3.reason,
            )
            await _log_blocked(request, result)
            return result

    return ScanResult(
        verdict=Verdict.SAFE,
        category=ThreatCategory.SAFE,
        severity=Severity.LOW,
        confidence=1.0,
        layer_results=layer_results,
        reason="Passed all active layers",
    )


async def validate_tool(request: ToolCallRequest) -> ToolValidationResult:
    result = validate_tool_call(request)
    if not result.allowed:
        event = SecurityEvent(
            session_id=request.session_id,
            attack_type=ThreatCategory.UNAUTHORIZED_TOOL_CALL,
            layer_caught_by="tool_call_validator",
            original_input=request.user_request,
            attempted_action=f"{request.tool_name}({request.args})",
            action_taken="blocked",
            severity=result.severity,
            metadata={
                "tool_name": request.tool_name,
                "violated_rule": result.violated_rule,
                "origin": request.origin,
            },
        )
        await log_event(event)
    return result


async def scan_egress(request: OutputScanRequest) -> dict:
    result = scan_output(request)
    if result.verdict == Verdict.UNSAFE:
        event = SecurityEvent(
            session_id=request.session_id,
            attack_type=ThreatCategory.SECRETS_IN_OUTPUT
            if any("key" in i.lower() or "secret" in i.lower() for i in result.issues)
            else ThreatCategory.MALWARE_IN_OUTPUT,
            layer_caught_by="egress_scanner",
            original_input=request.user_request,
            attempted_action="output_delivery",
            action_taken="redacted",
            severity=result.severity,
            metadata={"issues": result.issues},
        )
        await log_event(event)
    return result.model_dump()


async def sanitize_content(request: ContentSanitizeRequest) -> dict:
    result = sanitize(request)
    if result.injection_detected:
        event = SecurityEvent(
            attack_type=ThreatCategory.INDIRECT_INJECTION,
            layer_caught_by="content_sanitizer",
            original_input=request.content[:500],
            attempted_action=f"content_injection via {request.source}",
            action_taken="sanitized",
            severity=Severity.HIGH,
            injection_source=request.source,
            metadata={"snippets": result.injection_snippets},
        )
        await log_event(event)
    return result.model_dump()


async def _log_blocked(
    request: ScanRequest,
    result: ScanResult,
    matched_pattern: str | None = None,
) -> None:
    event = SecurityEvent(
        session_id=request.session_id,
        user_id=request.user_id,
        attack_type=result.category,
        layer_caught_by=result.blocked_by_layer or "",
        original_input=request.text[:500],
        attempted_action="input_to_llm",
        action_taken="blocked",
        severity=result.severity,
        metadata={
            "confidence": result.confidence,
            "matched_pattern": matched_pattern,
            "reason": result.reason,
        },
    )
    await log_event(event)
