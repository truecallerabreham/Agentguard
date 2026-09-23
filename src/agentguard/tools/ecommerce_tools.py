"""E-Commerce Support Tools for AgentGuard Tool Hierarchy."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

from agentguard.ecommerce.service import get_ecommerce_service
from agentguard.governance.approval import require_approval


class EcommerceOrderLookupInput(BaseModel):
    store_id: str = Field(default="demo-store", description="Identifier of the merchant store.")
    order_number: str = Field(..., description="E-commerce order number (e.g. '1001' or '#1001').")
    customer_email: str = Field(..., description="Customer billing/checkout email address for identity verification.")


class EcommerceEvaluateReturnInput(BaseModel):
    store_id: str = Field(default="demo-store", description="Identifier of the merchant store.")
    order_number: str = Field(..., description="Order number to evaluate for return.")
    customer_email: str = Field(..., description="Customer billing email address for verification.")
    reason: str = Field(default="Customer requested return", description="Customer's stated reason for return.")


class EcommerceRequestRefundInput(BaseModel):
    store_id: str = Field(default="demo-store", description="Identifier of the merchant store.")
    order_number: str = Field(..., description="Order number to refund.")
    customer_email: str = Field(..., description="Customer billing email address.")
    amount_cents: int = Field(..., ge=1, description="Refund amount in cents (e.g. 9900 for $99.00).")
    reason: str = Field(..., min_length=3, description="Justification for issuing the refund.")
    approval_id: str | None = Field(default=None, description="Cryptographic approval ID if already authorized.")
    approval_token: str | None = Field(default=None, description="Cryptographic single-use token if already authorized.")


class EcommerceExecuteRefundInput(BaseModel):
    store_id: str = Field(default="demo-store", description="Identifier of the merchant store.")
    order_number: str = Field(..., description="Order number.")
    approval_id: str = Field(..., description="Cryptographic approval ID.")
    approval_token: str = Field(..., description="Single-use approval token.")
    amount_cents: int = Field(..., ge=1, description="Refund amount in cents.")
    reason: str = Field(default="Refund authorized by merchant", description="Reason note.")


async def ecommerce_order_lookup(
    store_id: str = "demo-store",
    order_number: str = "",
    customer_email: str = "",
) -> dict[str, Any]:
    """Lookup and verify e-commerce order status, tracking, and fulfillment details with customer email validation."""
    svc = get_ecommerce_service()
    order = await svc.lookup_verified_order(store_id, order_number, customer_email)
    return order.to_dict()


async def ecommerce_evaluate_return(
    store_id: str = "demo-store",
    order_number: str = "",
    customer_email: str = "",
    reason: str = "Customer requested return",
) -> dict[str, Any]:
    """Evaluate return eligibility against store policy for delivered orders."""
    svc = get_ecommerce_service()
    decision = await svc.evaluate_return(store_id, order_number, customer_email, reason)
    return decision.to_dict()


@require_approval(risk_level="HIGH", timeout_seconds=900)
async def ecommerce_request_refund(
    store_id: str = "demo-store",
    order_number: str = "",
    customer_email: str = "",
    amount_cents: int = 0,
    reason: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Initiate refund request for an order.
    
    Protected by Human-in-the-Loop approval gate: requires merchant authorization
    before funds can be disbursed.
    """
    svc = get_ecommerce_service()
    # If this point is reached, the approval token was valid and consumed!
    approval_id = kwargs.get("approval_id", "pre-approved")
    approval_token = kwargs.get("approval_token", "pre-approved")
    return await svc.execute_approved_refund(
        store_id=store_id,
        order_number=order_number,
        approval_id=approval_id,
        approval_token=approval_token,
        amount_cents=amount_cents,
        reason=reason,
    )


async def ecommerce_execute_refund(
    store_id: str = "demo-store",
    order_number: str = "",
    approval_id: str = "",
    approval_token: str = "",
    amount_cents: int = 0,
    reason: str = "Authorized refund",
) -> dict[str, Any]:
    """Execute store refund disbursement using verified single-use approval token."""
    svc = get_ecommerce_service()
    return await svc.execute_approved_refund(
        store_id=store_id,
        order_number=order_number,
        approval_id=approval_id,
        approval_token=approval_token,
        amount_cents=amount_cents,
        reason=reason,
    )
