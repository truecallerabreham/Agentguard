"""Atomic tool for order lookup by customer ID or order ID."""

from __future__ import annotations
from typing import Any
from agentguard.tools.atomic.postgres import postgres_query


async def order_lookup(
    customer_id: str | None = None,
    order_id: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve orders for a customer or a specific order within the caller's tenant boundary."""
    if order_id:
        return await postgres_query("SELECT * FROM orders WHERE id = $1", [order_id])
    elif customer_id:
        return await postgres_query("SELECT * FROM orders WHERE customer_id = $1", [customer_id])
    return []

