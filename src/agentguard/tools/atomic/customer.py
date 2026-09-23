"""Atomic tool for single-record customer profile lookup."""

from __future__ import annotations
from typing import Any
from agentguard.tools.atomic.postgres import postgres_query
from agentguard.errors import NotFoundError


async def customer_lookup(customer_id: str) -> dict[str, Any]:
    """Fetch confidential customer profile by ID within the caller's tenant boundary."""
    rows = await postgres_query("SELECT * FROM customers WHERE id = $1", [customer_id])
    if not rows:
        raise NotFoundError(
            code="CUSTOMER_NOT_FOUND",
            hint=f"Customer '{customer_id}' does not exist in the caller's tenant.",
            context={"customer_id": customer_id},
        )
    return rows[0]
