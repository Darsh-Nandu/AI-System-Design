"""Tool call intent validator -- the last line of defense before execution.

Validates every tool call against:
1. Tool scope (is this tool allowed for this agent?)
2. Filesystem/network sandbox
3. Provenance (did this originate from user or from content?)
4. Intent gap (semantic distance from user's original request)
"""

from __future__ import annotations

import structlog

from guardrails.config import get_settings
from guardrails.injection.intent_gap import check_intent_gap
from guardrails.injection.provenance_tracker import is_traceable_to_user
from guardrails.models import Severity, ToolCallRequest, ToolValidationResult
from guardrails.sandbox.filesystem import validate_path, validate_network

log = structlog.get_logger(__name__)


def validate_tool_call(request: ToolCallRequest) -> ToolValidationResult:
    cfg = get_settings()
    allowed_tools = {t.strip() for t in cfg.allowed_tools.split(",") if t.strip()}

    if request.tool_name not in allowed_tools:
        return ToolValidationResult(
            allowed=False,
            tool_name=request.tool_name,
            reason=f"Tool '{request.tool_name}' is not in scope for this agent. Allowed: {sorted(allowed_tools)}",
            violated_rule="tool_scope",
            severity=Severity.HIGH,
        )

    args = request.args
    path_arg = args.get("path") or args.get("file") or args.get("filename") or args.get("filepath")
    if path_arg and isinstance(path_arg, str):
        ok, reason = validate_path(path_arg)
        if not ok:
            return ToolValidationResult(
                allowed=False,
                tool_name=request.tool_name,
                reason=reason,
                violated_rule="sandbox_filesystem",
                severity=Severity.HIGH,
            )

    url_arg = args.get("url") or args.get("endpoint") or args.get("to") or args.get("domain")
    if url_arg and isinstance(url_arg, str) and request.tool_name in {"http_request", "send_email", "post_webhook"}:
        ok, reason = validate_network(url_arg)
        if not ok:
            return ToolValidationResult(
                allowed=False,
                tool_name=request.tool_name,
                reason=reason,
                violated_rule="sandbox_network",
                severity=Severity.HIGH,
            )

    traceable, provenance_reason = is_traceable_to_user(request, request.user_request)
    if not traceable:
        return ToolValidationResult(
            allowed=False,
            tool_name=request.tool_name,
            reason=provenance_reason,
            violated_rule="provenance_check",
            severity=Severity.CRITICAL,
        )

    if request.user_request:
        gap_too_large, sim, gap_reason = check_intent_gap(
            request.user_request, request.tool_name, request.args
        )
        if gap_too_large:
            return ToolValidationResult(
                allowed=False,
                tool_name=request.tool_name,
                reason=gap_reason,
                violated_rule="intent_gap",
                severity=Severity.HIGH,
            )

    log.info("tool_call_allowed", tool=request.tool_name, origin=request.origin)
    return ToolValidationResult(
        allowed=True,
        tool_name=request.tool_name,
        reason="All validation checks passed",
        severity=Severity.LOW,
    )
