"""Atomic tool for creating customer support tickets."""

from __future__ import annotations
from datetime import datetime, timezone
import secrets
from typing import Any
from agentguard.db.pool import get_db_manager
from agentguard.governance.tenant import current_tenant
from agentguard.errors import PolicyError


async def ticket_create(
    customer_id: str,
    title: str,
    description: str,
    priority: str = "normal",
) -> dict[str, Any]:
    """Create and persist a new customer support ticket in the caller's tenant."""
    tenant_id = current_tenant.get()
    if not tenant_id:
        raise PolicyError("Missing tenant context: Cannot create support ticket without a verified tenant.")

    ticket_id = f"TICK-{secrets.token_hex(4).upper()}"
    timestamp = datetime.now(timezone.utc).isoformat()

    ticket_data = {
        "id": ticket_id,
        "customer_id": customer_id,
        "title": title,
        "description": description,
        "priority": priority,
        "status": "open",
        "created_at": timestamp,
    }

    db = get_db_manager()
    return db.create_ticket(tenant_id, ticket_data)
