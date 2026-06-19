"""Filesystem sandbox validator.

Enforces principle of least privilege for file path access.
Operates on path strings before any system call is made.
"""

from __future__ import annotations

import os
import re

from guardrails.config import get_settings


def _normalize(path: str) -> str:
    path = path.replace("\\", "/")
    home = os.path.expanduser("~").replace("\\", "/")
    if path.startswith("~/"):
        path = home + path[1:]
    return os.path.normpath(path).replace("\\", "/")


def validate_path(path: str) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    cfg = get_settings()
    normalized = _normalize(path)

    blocked_patterns = [p.strip() for p in cfg.blocked_path_patterns.split(",") if p.strip()]
    for pattern in blocked_patterns:
        if pattern in normalized:
            return False, f"Path '{path}' matches blocked pattern '{pattern}' (sandbox violation)"

    if ".." in normalized.split("/"):
        return False, f"Path traversal sequence detected in '{path}'"

    allowed_prefixes = [p.strip() for p in cfg.allowed_path_prefixes.split(",") if p.strip()]
    for prefix in allowed_prefixes:
        normalized_prefix = _normalize(prefix)
        if normalized.startswith(normalized_prefix):
            return True, f"Path is within allowed prefix '{prefix}'"

    return False, f"Path '{path}' is outside all allowed directories"


def validate_network(url_or_domain: str) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    cfg = get_settings()
    allowed = [d.strip() for d in cfg.allowed_domains.split(",") if d.strip()]

    domain_match = re.search(r"(?:https?://)?([a-zA-Z0-9.\-]+)", url_or_domain)
    if not domain_match:
        return False, f"Cannot parse domain from '{url_or_domain}'"
    domain = domain_match.group(1).lower()

    if "smtp" in url_or_domain.lower() or ":25" in url_or_domain or ":587" in url_or_domain:
        return False, "SMTP/email protocols are completely blocked for this agent"

    for allowed_domain in allowed:
        if domain == allowed_domain or domain.endswith("." + allowed_domain):
            return True, f"Domain '{domain}' is in the allowlist"

    return False, f"Domain '{domain}' is not in the network allowlist"
