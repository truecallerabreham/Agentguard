"""Tools package for AgentGuard MCP server providing a Three-Level Tool Hierarchy."""

from __future__ import annotations

from agentguard.tools.base import (
    BaseTool,
    ToolDispatcher,
    get_dispatcher,
    validate_input,
)
from agentguard.tools.registry import (
    ToolLevel,
    ToolMetadata,
    ToolRegistry,
    get_tool_registry,
)
from agentguard.tools.atomic import (
    postgres_query,
    customer_lookup,
    order_lookup,
    kb_search,
    ticket_create,
    fetch_url,
)
from agentguard.tools.composed import (
    customer_360,
    troubleshoot_inquiry,
    issue_high_risk_refund,
    list_pending_approvals,
    approve_action,
    reject_action,
)
from agentguard.tools.workflow import (
    WorkflowStatus,
    WorkflowStep,
    WorkflowExecution,
    WorkflowEngine,
    get_workflow_engine,
    start_return_remediation,
    get_workflow_status,
    stream_return_remediation,
)

__all__ = [
    # Base & Registry
    "BaseTool",
    "ToolDispatcher",
    "get_dispatcher",
    "validate_input",
    "ToolLevel",
    "ToolMetadata",
    "ToolRegistry",
    "get_tool_registry",
    # Level 1: Atomic
    "postgres_query",
    "customer_lookup",
    "order_lookup",
    "kb_search",
    "ticket_create",
    "fetch_url",
    # Level 2: Composed
    "customer_360",
    "troubleshoot_inquiry",
    "issue_high_risk_refund",
    "list_pending_approvals",
    "approve_action",
    "reject_action",
    # Level 3: Workflow
    "WorkflowStatus",
    "WorkflowStep",
    "WorkflowExecution",
    "WorkflowEngine",
    "get_workflow_engine",
    "start_return_remediation",
    "get_workflow_status",
    "stream_return_remediation",
]

