"""Server-Side Request Forgery (SSRF) defense and outbound network allowlisting.

Protects against:
- Cloud metadata service access (AWS/GCP/Azure 169.254.169.254)
- Loopback exploitation (127.0.0.1, ::1, localhost)
- Private enterprise network scanning (RFC 1918 subnets: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- Non-HTTP protocol smuggling (file://, gopher://, ftp://)
- Open redirect SSRF bypasses
"""

from __future__ import annotations
import fnmatch
import ipaddress
import logging
import socket
from urllib.parse import urlparse
from typing import Any
import httpx

from agentguard.config import get_settings
from agentguard.errors import SSRFViolationError

logger = logging.getLogger("agentguard.governance.ssrf")

FORBIDDEN_HOSTNAMES = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
})


def is_ip_restricted(ip_str: str) -> tuple[bool, str]:
    """Inspect IP address against loopback, private, link-local, and cloud metadata subnets."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True, f"Malformed IP address: '{ip_str}'"

    if ip.is_loopback:
        return True, f"Loopback address '{ip_str}' is forbidden"
    if ip.is_private:
        return True, f"RFC-1918 private network address '{ip_str}' is forbidden"
    if ip.is_link_local:
        return True, f"Link-local address '{ip_str}' (including cloud metadata) is forbidden"
    if ip.is_multicast:
        return True, f"Multicast address '{ip_str}' is forbidden"
    if ip.is_reserved:
        return True, f"Reserved address '{ip_str}' is forbidden"
    if str(ip) == "169.254.169.254":
        return True, "Cloud metadata endpoint 169.254.169.254 is forbidden"

    return False, ""


def validate_url_ssrf(
    url: str,
    allowlist: list[str] | None = None,
    block_private_ips: bool = True,
) -> tuple[str, list[str]]:
    """Validate that a URL is safe from SSRF vulnerabilities.

    Returns:
        (hostname, resolved_ips)
    Raises:
        SSRFViolationError if URL violates protocol, domain, or IP security constraints.
    """
    if not url or not isinstance(url, str):
        raise SSRFViolationError(url=str(url), reason="URL cannot be empty")

    parsed = urlparse(url.strip())

    # 1. Enforce HTTP/HTTPS scheme only
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFViolationError(
            url=url,
            reason=f"Forbidden protocol '{parsed.scheme}'. Only 'http' and 'https' are permitted",
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFViolationError(url=url, reason="URL must include a valid hostname")

    hostname_lower = hostname.lower()

    # 2. Block well-known forbidden hostnames and metadata endpoints
    if hostname_lower in FORBIDDEN_HOSTNAMES:
        raise SSRFViolationError(
            url=url,
            reason=f"Hostname '{hostname}' is a forbidden internal destination",
        )

    # 3. Check Domain Allowlist
    settings = get_settings()
    effective_allowlist = allowlist or settings.outbound_domain_allowlist
    if effective_allowlist and "*" not in effective_allowlist:
        matched = False
        for pattern in effective_allowlist:
            if fnmatch.fnmatch(hostname_lower, pattern.lower()):
                matched = True
                break
        if not matched:
            raise SSRFViolationError(
                url=url,
                reason=f"Domain '{hostname}' is not in the outbound allowlist ({effective_allowlist})",
            )

    # 4. Resolve DNS and inspect all destination IP addresses
    resolved_ips: list[str] = []
    if block_private_ips:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
            for item in addr_info:
                ip_str = item[4][0]
                resolved_ips.append(ip_str)
                restricted, reason = is_ip_restricted(ip_str)
                if restricted:
                    raise SSRFViolationError(url=url, reason=f"Resolved host '{hostname}' to restricted IP: {reason}")
        except socket.gaierror as exc:
            raise SSRFViolationError(url=url, reason=f"DNS resolution failed for '{hostname}': {exc}") from exc

    return hostname, resolved_ips


async def safe_http_get(
    url: str,
    timeout: float = 5.0,
    max_bytes: int = 500_000,
    allowlist: list[str] | None = None,
) -> dict[str, Any]:
    """Execute an outbound HTTP GET request with SSRF validation and resource limits."""
    # Validate before establishing connection
    validate_url_ssrf(url, allowlist=allowlist)

    # Fetch with follow_redirects=False to prevent open redirect SSRF attacks
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        try:
            resp = await client.get(url)
            
            # If redirected, validate the redirect target before following!
            if resp.is_redirect:
                redirect_url = resp.headers.get("location")
                if redirect_url:
                    validate_url_ssrf(redirect_url, allowlist=allowlist)
                    resp = await client.get(redirect_url)

            content = resp.content[:max_bytes]
            text_snippet = content.decode("utf-8", errors="replace")[:2000]

            return {
                "status_code": resp.status_code,
                "url": str(resp.url),
                "content_type": resp.headers.get("content-type", "application/octet-stream"),
                "content_length": len(content),
                "text_snippet": text_snippet,
            }
        except httpx.RequestError as exc:
            raise SSRFViolationError(url=url, reason=f"HTTP request error: {exc}") from exc
