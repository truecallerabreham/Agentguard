"""Planner Agent: Decomposes unstructured customer inquiries into structured tool execution plans."""

from __future__ import annotations
import logging
import re
from typing import Any

from agentguard.agents.base import AgentRole, ExecutionPlan, PlanStep

logger = logging.getLogger("agentguard.agents.planner")


class PlannerAgent:
    """Specialized agent responsible for query understanding, goal formulation, and tool step decomposition."""

    def __init__(self, role: AgentRole = AgentRole.PLANNER) -> None:
        self.role = role

    async def plan(
        self,
        inquiry: str,
        customer_id: str | None = None,
        tenant_id: str = "default",
    ) -> ExecutionPlan:
        """Analyze customer inquiry and formulate a structured multi-step retrieval and investigation plan."""
        logger.info("Planner analyzing inquiry for tenant '%s', customer '%s'", tenant_id, customer_id)

        inquiry_lower = inquiry.lower()
        steps: list[PlanStep] = []
        step_counter = 1

        # 1. Detect Customer ID if not explicitly provided
        detected_cust_id = customer_id
        if not detected_cust_id:
            cust_match = re.search(r"\b(cust[-_]?\d+|[A-Z0-9]{4,}-[A-Z0-9]+)\b", inquiry, re.IGNORECASE)
            if cust_match:
                detected_cust_id = cust_match.group(0).upper()

        if detected_cust_id:
            steps.append(
                PlanStep(
                    step_number=step_counter,
                    action="Retrieve customer profile, loyalty tier, and contact details",
                    tool_name="get_customer",
                    arguments={"customer_id": detected_cust_id},
                    reason="Verify caller identity and determine tier-based entitlements (e.g. Gold tier benefits).",
                )
            )
            step_counter += 1

        # 2. Detect Order ID in inquiry
        order_match = re.search(r"\b(o[_-]\d+|ord[_-]\d+|[A-Z0-9]{2,}_[0-9]{4,})\b", inquiry, re.IGNORECASE)
        detected_order_id = order_match.group(0) if order_match else None

        if detected_order_id:
            steps.append(
                PlanStep(
                    step_number=step_counter,
                    action=f"Lookup order history and delivery status for {detected_order_id}",
                    tool_name="order_lookup",
                    arguments={"order_id": detected_order_id},
                    reason="Check purchase date, shipment status, and item eligibility for return or warranty.",
                )
            )
            step_counter += 1
        elif detected_cust_id:
            # If no specific order mentioned, query all customer orders
            steps.append(
                PlanStep(
                    step_number=step_counter,
                    action="Fetch recent order history for customer",
                    tool_name="order_lookup",
                    arguments={"customer_id": detected_cust_id},
                    reason="Inspect recent purchases to identify relevant transactions.",
                )
            )
            step_counter += 1

        # 3. Detect Knowledge Base Policy requirements
        if any(w in inquiry_lower for w in ("return", "refund", "exchange", "money back")):
            steps.append(
                PlanStep(
                    step_number=step_counter,
                    action="Search Return and Refund policy articles in knowledge base",
                    tool_name="kb_search",
                    arguments={"query": "return policy refund timeframe restocking fee", "category": "returns"},
                    reason="Retrieve official policy terms, return window deadlines, and restocking fee rules.",
                )
            )
            step_counter += 1

        if any(w in inquiry_lower for w in ("defective", "broken", "damaged", "warranty", "replacement", "repair")):
            steps.append(
                PlanStep(
                    step_number=step_counter,
                    action="Search Warranty and Defective Merchandise policies",
                    tool_name="kb_search",
                    arguments={"query": "defective merchandise warranty direct replacement", "category": "warranty"},
                    reason="Determine coverage guidelines and SLA for damaged or defective equipment.",
                )
            )
            step_counter += 1

        if any(w in inquiry_lower for w in ("billing", "invoice", "charge", "dispute", "payment")):
            steps.append(
                PlanStep(
                    step_number=step_counter,
                    action="Search Billing and Invoicing policies",
                    tool_name="kb_search",
                    arguments={"query": "billing payment dispute posting time", "category": "billing"},
                    reason="Retrieve billing guidelines and payment disbursement schedules.",
                )
            )
            step_counter += 1

        # Fallback if no specific steps could be deduced
        if not steps:
            steps.append(
                PlanStep(
                    step_number=1,
                    action="Search general knowledge base for relevant resolution guidelines",
                    tool_name="kb_search",
                    arguments={"query": inquiry[:100], "category": None},
                    reason="Gather relevant policy or procedural documentation matching customer request.",
                )
            )

        objective = f"Resolve inquiry regarding: {inquiry[:80]}..."
        rationale = (
            f"Decomposed inquiry into {len(steps)} verifiable tool execution steps: "
            + ", ".join(f"[{s.tool_name}]" for s in steps)
        )

        return ExecutionPlan(
            objective=objective,
            steps=steps,
            rationale=rationale,
        )

