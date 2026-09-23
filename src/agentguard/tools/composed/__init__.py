"""Composed Tools package: multi-step operations aggregating multiple atomic tools."""

from __future__ import annotations

from agentguard.tools.composed.customer_360 import customer_360
from agentguard.tools.composed.troubleshoot import troubleshoot_inquiry
from agentguard.tools.composed.refund import issue_high_risk_refund
from agentguard.tools.composed.approval_tools import (
    list_pending_approvals,
    approve_action,
    reject_action,
)

__all__ = [
    "customer_360",
    "troubleshoot_inquiry",
    "issue_high_risk_refund",
    "list_pending_approvals",
    "approve_action",
    "reject_action",
]


