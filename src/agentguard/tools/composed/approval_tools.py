"""Tools for inspecting, approving, and rejecting Human-in-the-Loop confirmation gates."""

from __future__ import annotations
from typing import Any
from agentguard.auth.oauth import current_principal
from agentguard.governance.tenant import current_tenant
from agentguard.governance.approval import get_approval_manager
from agentguard.observability.audit import get_audit_logger


async def list_pending_approvals(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """List all currently pending human approval gates."""
    effective_tenant = tenant_id or current_tenant.get()
    manager = get_approval_manager()
    return manager.list_pending(tenant_id=effective_tenant)


async def approve_action(approval_id: str, approval_token: str) -> dict[str, Any]:
    """Authorize and approve a pending high-risk action with its confirmation token."""
    p = current_principal.get()
    approver = p.subject if p else "supervisor"
    manager = get_approval_manager()

    appr = manager.approve(approval_id=approval_id, approver=approver, token=approval_token)

    audit = get_audit_logger()
    audit.log_action(
        action=f"approval_decision:approved",
        parameters={"approval_id": approval_id, "tool_name": appr.tool_name},
        status="APPROVED",
        tenant_id=appr.tenant_id,
    )

    return {
        "status": "APPROVED",
        "approval_id": approval_id,
        "tool_name": appr.tool_name,
        "approved_by": approver,
        "message": "Action approved. The tool can now be executed by passing this approval_id and approval_token.",
    }


async def reject_action(approval_id: str, reason: str = "Rejected by supervisor") -> dict[str, Any]:
    """Reject and cancel a pending high-risk action."""
    p = current_principal.get()
    approver = p.subject if p else "supervisor"
    manager = get_approval_manager()

    appr = manager.reject(approval_id=approval_id, approver=approver, reason=reason)

    audit = get_audit_logger()
    audit.log_action(
        action=f"approval_decision:rejected",
        parameters={"approval_id": approval_id, "tool_name": appr.tool_name, "reason": reason},
        status="REJECTED",
        tenant_id=appr.tenant_id,
    )

    return {
        "status": "REJECTED",
        "approval_id": approval_id,
        "tool_name": appr.tool_name,
        "rejected_by": approver,
        "reason": reason,
        "message": "Action rejected and cancelled.",
    }
