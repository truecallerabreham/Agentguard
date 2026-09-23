"""Centralized Tool Registry for Atomic, Composed, and Workflow tools."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
from typing import Any, Callable, Type
from pydantic import BaseModel

from agentguard.cache import cached_tool
from agentguard.errors import serf_protected
from agentguard.observability import observe_tool
from agentguard.auth.policy import enforce_policy
from agentguard.tools.base import validate_input

logger = logging.getLogger("agentguard.tools.registry")


class ToolLevel(str, Enum):
    ATOMIC = "ATOMIC"      # Single database / resource access primitive (<50ms SLA)
    COMPOSED = "COMPOSED"  # Multi-step aggregation coordinating multiple atomic tools
    WORKFLOW = "WORKFLOW"  # Long-running, multi-phase stateful process with checkpoints


@dataclass
class ToolMetadata:
    name: str
    level: ToolLevel
    description: str
    input_schema: Type[BaseModel]
    handler: Callable
    cacheable: bool = False
    ttl_l1: int = 30
    ttl_l2: int = 300
    required_scopes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level.value,
            "description": self.description,
            "input_schema": self.input_schema.model_json_schema(),
            "cacheable": self.cacheable,
            "required_scopes": self.required_scopes,
        }


class ToolRegistry:
    """Enterprise registry discovering, organizing, and securing all tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolMetadata] = {}

    def register(self, meta: ToolMetadata) -> None:
        """Register tool metadata into registry."""
        self._tools[meta.name] = meta
        logger.debug("Registered %s tool '%s'.", meta.level.value, meta.name)

    def get(self, name: str) -> ToolMetadata | None:
        return self._tools.get(name)

    def list_tools(self, level: ToolLevel | None = None) -> list[ToolMetadata]:
        """List all tools, optionally filtered by ToolLevel."""
        if level is None:
            return list(self._tools.values())
        return [t for t in self._tools.values() if t.level == level]

    def build_decorated_handler(self, meta: ToolMetadata) -> Callable:
        """Wrap tool handler with the full AgentGuard production security and reliability pipeline.

        Pipeline hierarchy:
        @serf_protected -> @observe_tool -> @enforce_policy -> @validate_input -> @cached_tool -> handler
        """
        fn = meta.handler

        # 1. Caching (innermost if enabled)
        if meta.cacheable:
            fn = cached_tool(ttl_l1=meta.ttl_l1, ttl_l2=meta.ttl_l2)(fn)

        # 2. Strict Input Validation via Pydantic
        fn = validate_input(meta.input_schema)(fn)

        # 3. RBAC Policy Enforcement
        fn = enforce_policy(meta.name)(fn)

        # 4. Observability (Tracing span, Prometheus metrics, Audit logging)
        fn = observe_tool(meta.name)(fn)

        # 5. Structured Error Recovery Framework (SERF) (outermost)
        fn = serf_protected(fn)

        return fn

    def register_with_mcp(self, mcp_server: Any) -> None:
        """Register all tools with a FastMCP server instance."""
        for meta in self._tools.values():
            decorated = self.build_decorated_handler(meta)
            # Register with FastMCP using tool name and description
            mcp_server.tool(name=meta.name, description=meta.description)(decorated)
            logger.info("Mounted %s tool '%s' to FastMCP server.", meta.level.value, meta.name)


_GLOBAL_REGISTRY: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Singleton getter for the global ToolRegistry populated with all three tool tiers."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        reg = ToolRegistry()
        _populate_default_tools(reg)
        _GLOBAL_REGISTRY = reg
    return _GLOBAL_REGISTRY


def _populate_default_tools(reg: ToolRegistry) -> None:
    """Populate default Atomic, Composed, and Workflow tools."""
    from agentguard.validation.schemas import (
        GreetInput,
        AddInput,
        EchoInput,
        CustomerInput,
        PostgresQueryInput,
        OrderLookupInput,
        KBSearchInput,
        TicketCreateInput,
        Customer360Input,
        TroubleshootInquiryInput,
        ReturnRemediationInput,
        WorkflowStatusInput,
    )
    from agentguard.tools.atomic import (
        postgres_query,
        customer_lookup,
        order_lookup,
        kb_search,
        ticket_create,
    )
    from agentguard.tools.composed import customer_360, troubleshoot_inquiry
    from agentguard.tools.workflow import start_return_remediation, get_workflow_status

    # Primitive helpers
    def _greet(name: str = "World") -> str:
        return f"Hello, {name}!"

    def _add(a: int, b: int) -> int:
        return a + b

    def _echo(message: str) -> str:
        return f"AgentGuard received: {message}"

    async def _postgres_wrapper(sql: str) -> str:
        rows = await postgres_query(sql)
        return json.dumps(rows, indent=2)

    async def _customer_wrapper(customer_id: str) -> str:
        res = await customer_lookup(customer_id)
        return json.dumps(res, indent=2)

    async def _order_wrapper(customer_id: str | None = None, order_id: str | None = None) -> str:
        res = await order_lookup(customer_id=customer_id, order_id=order_id)
        return json.dumps(res, indent=2)

    async def _kb_wrapper(query: str, category: str | None = None) -> str:
        res = await kb_search(query=query, category=category)
        return json.dumps(res, indent=2)

    async def _ticket_wrapper(customer_id: str, title: str, description: str, priority: str = "normal") -> str:
        res = await ticket_create(customer_id=customer_id, title=title, description=description, priority=priority)
        return json.dumps(res, indent=2)

    async def _c360_wrapper(customer_id: str) -> str:
        res = await customer_360(customer_id)
        return json.dumps(res, indent=2)

    async def _troubleshoot_wrapper(customer_id: str, issue_description: str) -> str:
        res = await troubleshoot_inquiry(customer_id=customer_id, issue_description=issue_description)
        return json.dumps(res, indent=2)

    async def _return_wrapper(order_id: str, customer_id: str, reason: str) -> str:
        res = await start_return_remediation(order_id=order_id, customer_id=customer_id, reason=reason)
        return json.dumps(res, indent=2)

    async def _wf_status_wrapper(workflow_id: str) -> str:
        res = await get_workflow_status(workflow_id)
        return json.dumps(res, indent=2)

    # 1. ATOMIC TOOLS
    reg.register(ToolMetadata(
        name="greet",
        level=ToolLevel.ATOMIC,
        description="Public friendly greeting for an agent or user.",
        input_schema=GreetInput,
        handler=_greet,
    ))
    reg.register(ToolMetadata(
        name="add",
        level=ToolLevel.ATOMIC,
        description="Mathematical computation adding two integers.",
        input_schema=AddInput,
        handler=_add,
    ))
    reg.register(ToolMetadata(
        name="echo",
        level=ToolLevel.ATOMIC,
        description="Echo message back to caller.",
        input_schema=EchoInput,
        handler=_echo,
    ))
    reg.register(ToolMetadata(
        name="get_customer",
        level=ToolLevel.ATOMIC,
        description="Lookup confidential customer records by customer ID.",
        input_schema=CustomerInput,
        handler=_customer_wrapper,
        cacheable=True,
    ))
    reg.register(ToolMetadata(
        name="order_lookup",
        level=ToolLevel.ATOMIC,
        description="Retrieve order records by customer ID or order ID.",
        input_schema=OrderLookupInput,
        handler=_order_wrapper,
        cacheable=True,
    ))
    reg.register(ToolMetadata(
        name="kb_search",
        level=ToolLevel.ATOMIC,
        description="Search knowledge base articles for return, warranty, or billing policies.",
        input_schema=KBSearchInput,
        handler=_kb_wrapper,
        cacheable=True,
    ))
    reg.register(ToolMetadata(
        name="ticket_create",
        level=ToolLevel.ATOMIC,
        description="Create and persist a new customer support ticket.",
        input_schema=TicketCreateInput,
        handler=_ticket_wrapper,
    ))
    reg.register(ToolMetadata(
        name="postgres_query",
        level=ToolLevel.ATOMIC,
        description="Execute read-only SQL queries within tenant-isolated database session.",
        input_schema=PostgresQueryInput,
        handler=_postgres_wrapper,
        cacheable=True,
    ))

    # 2. COMPOSED TOOLS
    reg.register(ToolMetadata(
        name="customer_360",
        level=ToolLevel.COMPOSED,
        description="Synthesizes customer profile, order history, and spending metrics in a single turn.",
        input_schema=Customer360Input,
        handler=_c360_wrapper,
        cacheable=True,
    ))
    reg.register(ToolMetadata(
        name="troubleshoot_inquiry",
        level=ToolLevel.COMPOSED,
        description="Diagnoses customer inquiry by cross-referencing orders and knowledge base policies.",
        input_schema=TroubleshootInquiryInput,
        handler=_troubleshoot_wrapper,
    ))

    # 3. WORKFLOW TOOLS
    reg.register(ToolMetadata(
        name="start_return_remediation",
        level=ToolLevel.WORKFLOW,
        description="Executes the multi-phase stateful Return and Remediation workflow.",
        input_schema=ReturnRemediationInput,
        handler=_return_wrapper,
    ))
    reg.register(ToolMetadata(
        name="get_workflow_status",
        level=ToolLevel.WORKFLOW,
        description="Query execution state, step progress, and outcomes for a workflow instance.",
        input_schema=WorkflowStatusInput,
        handler=_wf_status_wrapper,
    ))
