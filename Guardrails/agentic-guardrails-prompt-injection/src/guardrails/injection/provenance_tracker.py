"""Tool call provenance tracker.

Every tool call carries metadata about where it originated.
Tool calls that come from content the agent read -- rather than
from a legitimate user request -- are flagged for blocking.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from guardrails.models import ToolCallRequest


class ProvenanceOrigin(str, Enum):
    USER = "user"
    CONTENT = "content"
    SYSTEM = "system"


def classify_provenance(tool_call: ToolCallRequest) -> ProvenanceOrigin:
    origin = tool_call.origin.lower()
    if origin in ("user", "human"):
        return ProvenanceOrigin.USER
    if origin in ("content", "file", "webpage", "pdf", "api_response", "database"):
        return ProvenanceOrigin.CONTENT
    return ProvenanceOrigin.SYSTEM


def is_traceable_to_user(
    tool_call: ToolCallRequest,
    user_request: str,
) -> tuple[bool, str]:
    """Determine whether a tool call can be traced back to the user's request.

    Returns (traceable, reason).
    """
    origin = classify_provenance(tool_call)

    if origin == ProvenanceOrigin.CONTENT:
        return False, (
            f"Tool call '{tool_call.tool_name}' originated from content "
            f"(origin: {tool_call.origin}), not from the user's request. "
            "Indirect prompt injection attempt suspected."
        )

    if not user_request:
        return True, "No user request context provided -- allowing by default"

    tool_lower = tool_call.tool_name.lower()
    request_lower = user_request.lower()

    read_ops = {"read_file", "list_directory", "search_docs"}
    write_ops = {"write_file", "run_code"}
    send_ops = {"send_email", "post_webhook", "http_request", "upload_file"}

    if tool_lower in send_ops:
        send_keywords = {"send", "email", "post", "upload", "share", "submit", "transfer"}
        if not any(kw in request_lower for kw in send_keywords):
            return False, (
                f"Tool '{tool_call.tool_name}' is a send/exfiltration operation "
                f"but the user's request '{user_request[:60]}' contains no send-related intent."
            )

    return True, "Tool call appears traceable to user request"
