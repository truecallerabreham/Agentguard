"""Human-in-the-Loop (HITL) approval gates for high-risk and destructive tool operations."""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
import inspect
import logging
import secrets
import threading
import time
from typing import Any, Callable

from agentguard.auth.oauth import current_principal
from agentguard.config import get_settings
from agentguard.errors import ApprovalRequiredError, PolicyError
from agentguard.governance.tenant import current_tenant

logger = logging.getLogger("agentguard.governance.approval")


def _get_audit():
    from agentguard.observability.audit import get_audit_logger
    return get_audit_logger()


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class PendingApproval:
    approval_id: str
    approval_token: str
    tool_name: str
    arguments: dict[str, Any]
    tenant_id: str
    requested_by: str
    risk_level: str = "HIGH"
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 900)
    decision_by: str | None = None
    decision_at: float | None = None
    decision_reason: str | None = None

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        # Redact the raw approval token in public listings
        data["approval_token"] = self.approval_token[:8] + "..."
        data["expires_in_seconds"] = max(0, round(self.expires_at - time.time(), 1))
        return data


class ApprovalManager:
    """Thread-safe manager coordinating human confirmation gates for sensitive actions."""

    def __init__(self) -> None:
        self._approvals: dict[str, PendingApproval] = {}
        self._lock = threading.Lock()

    def request_approval(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        tenant_id: str,
        requested_by: str,
        risk_level: str = "HIGH",
        timeout_seconds: int = 900,
    ) -> PendingApproval:
        """Create a pending human confirmation gate with a secure cryptographic token."""
        approval_id = f"appr-{secrets.token_hex(4)}"
        token = secrets.token_urlsafe(32)
        now = time.time()

        appr = PendingApproval(
            approval_id=approval_id,
            approval_token=token,
            tool_name=tool_name,
            arguments=dict(arguments),
            tenant_id=tenant_id,
            requested_by=requested_by,
            risk_level=risk_level,
            created_at=now,
            expires_at=now + timeout_seconds,
        )

        with self._lock:
            self._approvals[approval_id] = appr

        logger.warning(
            "HITL approval gate triggered for %s (id=%s, tenant=%s, user=%s).",
            tool_name,
            approval_id,
            tenant_id,
            requested_by,
        )
        return appr

    def get_approval(self, approval_id: str) -> PendingApproval | None:
        with self._lock:
            appr = self._approvals.get(approval_id)
            if appr and appr.status == ApprovalStatus.PENDING and appr.is_expired:
                appr.status = ApprovalStatus.EXPIRED
            return appr

    def list_pending(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """List active pending approvals, optionally filtered by tenant."""
        with self._lock:
            results = []
            for appr in self._approvals.values():
                if appr.status == ApprovalStatus.PENDING:
                    if appr.is_expired:
                        appr.status = ApprovalStatus.EXPIRED
                    elif tenant_id is None or appr.tenant_id == tenant_id:
                        results.append(appr.to_dict())
            return results

    def approve(self, approval_id: str, approver: str, token: str) -> PendingApproval:
        """Confirm and authorize a pending action."""
        with self._lock:
            appr = self._approvals.get(approval_id)
            if not appr:
                raise PolicyError(f"Approval request '{approval_id}' was not found.")
            if appr.is_expired:
                appr.status = ApprovalStatus.EXPIRED
                raise PolicyError(f"Approval request '{approval_id}' has expired.")
            if appr.status != ApprovalStatus.PENDING:
                raise PolicyError(f"Approval request '{approval_id}' is already {appr.status.value}.")
            if not secrets.compare_digest(appr.approval_token, token):
                raise PolicyError("Invalid approval token provided.")

            appr.status = ApprovalStatus.APPROVED
            appr.decision_by = approver
            appr.decision_at = time.time()
            return appr

    def reject(self, approval_id: str, approver: str, reason: str = "Rejected by supervisor") -> PendingApproval:
        """Reject and cancel a pending action."""
        with self._lock:
            appr = self._approvals.get(approval_id)
            if not appr:
                raise PolicyError(f"Approval request '{approval_id}' was not found.")
            appr.status = ApprovalStatus.REJECTED
            appr.decision_by = approver
            appr.decision_at = time.time()
            appr.decision_reason = reason
            return appr

    def verify_and_consume(self, approval_id: str, token: str) -> bool:
        """Verify that an approved token is valid and consume it to prevent replay."""
        with self._lock:
            appr = self._approvals.get(approval_id)
            if not appr:
                return False
            if appr.status != ApprovalStatus.APPROVED:
                return False
            if not secrets.compare_digest(appr.approval_token, token):
                return False

            # Consume approval to prevent replay
            del self._approvals[approval_id]
            return True


_GLOBAL_APPROVAL_MANAGER: ApprovalManager | None = None
_APPROVAL_LOCK = threading.Lock()


def get_approval_manager() -> ApprovalManager:
    """Singleton getter for the global ApprovalManager."""
    global _GLOBAL_APPROVAL_MANAGER
    with _APPROVAL_LOCK:
        if _GLOBAL_APPROVAL_MANAGER is None:
            _GLOBAL_APPROVAL_MANAGER = ApprovalManager()
        return _GLOBAL_APPROVAL_MANAGER


def require_approval(risk_level: str = "HIGH", timeout_seconds: int = 900) -> Callable:
    """Decorator guarding a high-risk tool behind human supervisor confirmation.

    If invoked without an approved token, execution pauses and raises an
    ApprovalRequiredError containing the pending approval_id and recovery instructions.
    """

    def decorator(func: Callable) -> Callable:
        tool_name = func.__name__

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                approval_id = kwargs.pop("approval_id", None)
                approval_token = kwargs.pop("approval_token", None)

                manager = get_approval_manager()

                # If approval token was provided, verify and consume it
                if approval_id and approval_token:
                    if not manager.verify_and_consume(approval_id, approval_token):
                        raise PolicyError(
                            code="APPROVAL_INVALID",
                            hint=f"Approval '{approval_id}' is invalid, unapproved, or has expired.",
                        )
                    # Approved: proceed with execution
                    return await func(*args, **kwargs)

                # Not approved yet: trigger approval gate
                tenant_id = current_tenant.get() or "unknown"
                p = current_principal.get()
                caller_id = p.subject if p else "anonymous"

                appr = manager.request_approval(
                    tool_name=tool_name,
                    arguments=kwargs,
                    tenant_id=tenant_id,
                    requested_by=caller_id,
                    risk_level=risk_level,
                    timeout_seconds=timeout_seconds,
                )

                # Record in audit log that high-risk action was held for approval
                audit = _get_audit()
                audit.log_action(
                    action=f"approval_gate:{tool_name}",
                    parameters=kwargs,
                    status="PENDING_APPROVAL",
                    error={"approval_id": appr.approval_id, "risk_level": risk_level},
                    tenant_id=tenant_id,
                )

                raise ApprovalRequiredError(
                    approval_id=appr.approval_id,
                    tool_name=tool_name,
                    context={
                        "approval_id": appr.approval_id,
                        "approval_token": appr.approval_token,
                        "risk_level": risk_level,
                        "expires_in_seconds": timeout_seconds,
                    },
                )

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                approval_id = kwargs.pop("approval_id", None)
                approval_token = kwargs.pop("approval_token", None)

                manager = get_approval_manager()

                if approval_id and approval_token:
                    if not manager.verify_and_consume(approval_id, approval_token):
                        raise PolicyError(
                            code="APPROVAL_INVALID",
                            hint=f"Approval '{approval_id}' is invalid, unapproved, or has expired.",
                        )
                    return func(*args, **kwargs)

                tenant_id = current_tenant.get() or "unknown"
                p = current_principal.get()
                caller_id = p.subject if p else "anonymous"

                appr = manager.request_approval(
                    tool_name=tool_name,
                    arguments=kwargs,
                    tenant_id=tenant_id,
                    requested_by=caller_id,
                    risk_level=risk_level,
                    timeout_seconds=timeout_seconds,
                )

                audit = _get_audit()
                audit.log_action(
                    action=f"approval_gate:{tool_name}",
                    parameters=kwargs,
                    status="PENDING_APPROVAL",
                    error={"approval_id": appr.approval_id, "risk_level": risk_level},
                    tenant_id=tenant_id,
                )

                raise ApprovalRequiredError(
                    approval_id=appr.approval_id,
                    tool_name=tool_name,
                    context={
                        "approval_id": appr.approval_id,
                        "approval_token": appr.approval_token,
                        "risk_level": risk_level,
                        "expires_in_seconds": timeout_seconds,
                    },
                )

            return sync_wrapper

    return decorator
