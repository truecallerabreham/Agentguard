"""Retriever Agent: Executes decomposed tool plans against AgentGuard MCP tools to compile evidence."""

from __future__ import annotations
import json
import logging
import time
from typing import Any

from agentguard.agents.base import AgentRole, EvidenceDossier, EvidenceItem, ExecutionPlan
from agentguard.auth.oauth import Principal, current_principal
from agentguard.errors import ToolError
from agentguard.governance.tenant import current_tenant
from agentguard.tools.registry import get_tool_registry

logger = logging.getLogger("agentguard.agents.retriever")


class RetrieverAgent:
    """Specialized agent responsible for tool execution, tenant isolation, and evidence compilation."""

    def __init__(self, role: AgentRole = AgentRole.RETRIEVER) -> None:
        self.role = role
        self.registry = get_tool_registry()

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        tenant_id: str,
    ) -> EvidenceDossier:
        """Execute each step in the plan against the tool registry within the tenant boundary."""
        logger.info("Retriever starting plan execution: %d steps for tenant '%s'", len(plan.steps), tenant_id)
        current_tenant.set(tenant_id)

        # Ensure task-safe principal is configured with analyst role for tool access
        if current_principal.get() is None:
            current_principal.set(
                Principal(
                    subject="agent:support-copilot",
                    delegator="supervisor",
                    tenant=tenant_id,
                    scopes=frozenset({"tool:*", "tool:read", "tool:write"}),
                    roles=frozenset({"analyst"}),
                )
            )

        items: list[EvidenceItem] = []

        for step in plan.steps:
            t0 = time.perf_counter()
            tool_meta = self.registry.get(step.tool_name)

            if not tool_meta:
                dur_ms = round((time.perf_counter() - t0) * 1000, 2)
                items.append(
                    EvidenceItem(
                        step_number=step.step_number,
                        tool_name=step.tool_name,
                        arguments=step.arguments,
                        result=None,
                        execution_time_ms=dur_ms,
                        status="NOT_FOUND",
                        error=f"Tool '{step.tool_name}' is not registered in AgentGuard.",
                    )
                )
                continue

            try:
                # Dispatch handler
                handler = self.registry.build_decorated_handler(tool_meta)
                raw_res = await handler(**step.arguments)

                # Parse JSON string output if returned as string
                parsed_res = raw_res
                if isinstance(raw_res, str):
                    try:
                        parsed_res = json.loads(raw_res)
                    except Exception:
                        parsed_res = raw_res

                dur_ms = round((time.perf_counter() - t0) * 1000, 2)

                # Detect if SERF error envelope was returned
                if isinstance(parsed_res, dict) and parsed_res.get("status") == "ERROR":
                    err_info = parsed_res.get("error", {})
                    err_msg = err_info.get("hint") or err_info.get("message") or "Tool execution failed"
                    items.append(
                        EvidenceItem(
                            step_number=step.step_number,
                            tool_name=step.tool_name,
                            arguments=step.arguments,
                            result=None,
                            execution_time_ms=dur_ms,
                            status="FAILED",
                            error=err_msg,
                        )
                    )
                    logger.warning("Retriever step %d (%s) returned SERF error: %s", step.step_number, step.tool_name, err_msg)
                else:
                    items.append(
                        EvidenceItem(
                            step_number=step.step_number,
                            tool_name=step.tool_name,
                            arguments=step.arguments,
                            result=parsed_res,
                            execution_time_ms=dur_ms,
                            status="SUCCESS",
                        )
                    )
                    logger.info(
                        "Retriever step %d (%s) succeeded in %.2fms",
                        step.step_number,
                        step.tool_name,
                        dur_ms,
                    )

            except ToolError as te:
                dur_ms = round((time.perf_counter() - t0) * 1000, 2)
                logger.warning("Retriever step %d (%s) raised ToolError: %s", step.step_number, step.tool_name, te)
                items.append(
                    EvidenceItem(
                        step_number=step.step_number,
                        tool_name=step.tool_name,
                        arguments=step.arguments,
                        result=None,
                        execution_time_ms=dur_ms,
                        status="FAILED",
                        error=te.message,
                    )
                )
            except Exception as exc:
                dur_ms = round((time.perf_counter() - t0) * 1000, 2)
                logger.error("Retriever step %d (%s) unexpected failure: %s", step.step_number, step.tool_name, exc)
                items.append(
                    EvidenceItem(
                        step_number=step.step_number,
                        tool_name=step.tool_name,
                        arguments=step.arguments,
                        result=None,
                        execution_time_ms=dur_ms,
                        status="ERROR",
                        error=str(exc),
                    )
                )

        successful_count = sum(1 for it in items if it.status == "SUCCESS")
        summary = f"Retrieved {successful_count}/{len(plan.steps)} evidence items successfully across tenant '{tenant_id}'."

        return EvidenceDossier(
            items=items,
            summary=summary,
        )
