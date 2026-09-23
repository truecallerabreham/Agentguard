"""Governance package: multi-tenancy, human approval gates (HITL), and SSRF defenses."""

from __future__ import annotations

from agentguard.governance.tenant import TenantMiddleware, current_tenant
from agentguard.governance.approval import (
    ApprovalStatus,
    PendingApproval,
    ApprovalManager,
    get_approval_manager,
    require_approval,
)
from agentguard.governance.http_allowlist import (
    validate_url_ssrf,
    is_ip_restricted,
    safe_http_get,
)

__all__ = [
    # Multi-tenancy
    "TenantMiddleware",
    "current_tenant",
    # Human-in-the-Loop (HITL)
    "ApprovalStatus",
    "PendingApproval",
    "ApprovalManager",
    "get_approval_manager",
    "require_approval",
    # SSRF Defense
    "validate_url_ssrf",
    "is_ip_restricted",
    "safe_http_get",
]
