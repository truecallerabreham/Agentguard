"""Composed tool: cross-references customer history and knowledge base policies to diagnose support inquiries."""

from __future__ import annotations
from typing import Any
from agentguard.tools.atomic.customer import customer_lookup
from agentguard.tools.atomic.order import order_lookup
from agentguard.tools.atomic.kb import kb_search


async def troubleshoot_inquiry(customer_id: str, issue_description: str) -> dict[str, Any]:
    """Diagnose customer support issue by combining profile, order history, and policy search.

    Reduces multiple agent tool queries into a single coordinated analysis step.
    """
    # 1. Fetch customer context
    customer = await customer_lookup(customer_id)

    # 2. Fetch order history
    orders = await order_lookup(customer_id=customer_id)

    # 3. Search knowledge base for policy guidance
    articles = await kb_search(query=issue_description)

    # 4. Synthesize diagnostic context
    tier = customer.get("tier", "standard")
    orders_summary = [
        f"Order {o.get('id')}: {o.get('status')} (${o.get('total_cents', 0) / 100:.2f})"
        for o in orders
    ]

    top_policy = articles[0] if articles else None
    policy_title = top_policy.get("title", "Standard Support Procedure") if top_policy else "Standard Procedure"
    policy_content = top_policy.get("content", "Follow standard support guidelines.") if top_policy else ""

    # Assessment
    has_refund = any("refund" in o.get("status", "") for o in orders)
    if has_refund:
        recommendation = (
            f"Customer has a pending refund order. Under {tier.upper()} tier rules, "
            f"expedite settlement via return remediation workflow with zero restocking fee."
        )
    else:
        recommendation = (
            f"Review issue against policy '{policy_title}'. "
            f"Customer tier is {tier.upper()}. Proceed with standard remediation if valid."
        )

    return {
        "customer": {
            "id": customer["id"],
            "name": customer["name"],
            "tier": tier,
        },
        "orders_evaluated": orders_summary,
        "matched_policies": [
            {"id": a["id"], "title": a["title"], "category": a["category"]}
            for a in articles[:3]
        ],
        "primary_policy_guideline": policy_content,
        "recommendation": recommendation,
    }
