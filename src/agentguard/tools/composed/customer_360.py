"""Composed tool: Customer 360 unifying profile, order history, and spending analytics."""

from __future__ import annotations
from typing import Any
from agentguard.tools.atomic.customer import customer_lookup
from agentguard.tools.atomic.order import order_lookup


async def customer_360(customer_id: str) -> dict[str, Any]:
    """Multi-step tool synthesizing a unified 360-degree view of a customer.

    Aggregates profile data, order history, and lifetime spending metrics across
    atomic tools to give the calling LLM a comprehensive snapshot in a single turn.
    """
    # 1. Fetch profile
    profile = await customer_lookup(customer_id)

    # 2. Fetch order history
    orders = await order_lookup(customer_id=customer_id)

    # 3. Compute analytics
    total_orders = len(orders)
    total_cents = sum(o.get("total_cents", 0) for o in orders)
    total_spend = round(total_cents / 100.0, 2)

    has_pending = any(o.get("status") in ("refund_pending", "disputed") for o in orders)
    account_health = "ACTION_REQUIRED" if has_pending else "HEALTHY"

    return {
        "customer": {
            "id": profile["id"],
            "name": profile["name"],
            "email": profile["email"],
            "tier": profile.get("tier", "standard"),
        },
        "metrics": {
            "total_orders": total_orders,
            "total_spend_usd": total_spend,
            "account_health": account_health,
        },
        "recent_orders": orders,
        "summary": (
            f"Customer '{profile['name']}' ({profile.get('tier', 'standard').upper()} tier) "
            f"has {total_orders} order(s) totaling ${total_spend:,.2f}. "
            f"Account status is {account_health}."
        ),
    }
