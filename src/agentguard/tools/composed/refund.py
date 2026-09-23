"""High-risk financial refund tool protected by Human-in-the-Loop (HITL) approval gate."""

from __future__ import annotations
import secrets
from typing import Any
from agentguard.governance.approval import require_approval
from agentguard.tools.atomic.customer import customer_lookup
from agentguard.tools.atomic.order import order_lookup
from agentguard.tools.atomic.ticket import ticket_create
from agentguard.errors import NotFoundError


@require_approval(risk_level="CRITICAL", timeout_seconds=900)
async def issue_high_risk_refund(
    order_id: str,
    customer_id: str,
    amount_usd: float,
    reason: str,
    approval_id: str | None = None,
    approval_token: str | None = None,
) -> dict[str, Any]:
    """Issue a high-risk financial refund to a customer account.

    This operation is classified as CRITICAL risk. It cannot be executed automatically
    by an autonomous agent without a validated human supervisor confirmation token.
    """
    # 1. Verify customer and order existence
    customer = await customer_lookup(customer_id)
    orders = await order_lookup(order_id=order_id)
    if not orders:
        raise NotFoundError(
            code="ORDER_NOT_FOUND",
            hint=f"Order '{order_id}' was not found.",
            context={"order_id": order_id},
        )

    # 2. Generate refund transaction receipt
    refund_tx_id = f"TX-REFUND-{secrets.token_hex(4).upper()}"

    # 3. Create tracking ticket
    ticket = await ticket_create(
        customer_id=customer_id,
        title=f"High-Risk Refund Executed: ${amount_usd:,.2f}",
        description=f"Transaction {refund_tx_id} executed for order {order_id}. Reason: {reason}.",
        priority="urgent",
    )

    return {
        "status": "SETTLED",
        "refund_transaction_id": refund_tx_id,
        "order_id": order_id,
        "customer_id": customer_id,
        "customer_name": customer["name"],
        "amount_usd": round(amount_usd, 2),
        "reason": reason,
        "ticket_id": ticket["id"],
        "confirmation": f"High-risk refund of ${amount_usd:,.2f} successfully disbursed to {customer['name']}.",
    }
