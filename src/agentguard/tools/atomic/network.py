"""Atomic tool for outbound HTTP requests guarded by SSRF defense."""

from __future__ import annotations
from typing import Any
from agentguard.governance.http_allowlist import safe_http_get


async def fetch_url(url: str) -> dict[str, Any]:
    """Safely fetch external HTTP/HTTPS resources while strictly blocking SSRF attacks.

    Guarantees that private IP ranges (RFC 1918), loopback (127.0.0.1), link-local,
    and cloud metadata endpoints (169.254.169.254) can never be accessed.
    """
    return await safe_http_get(url)
