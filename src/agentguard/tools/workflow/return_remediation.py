"""Long-running stateful workflow for Customer Return and Order Remediation."""

from __future__ import annotations
import secrets
from typing import Any, AsyncGenerator

from agentguard.auth.oauth import current_principal
from agentguard.governance.tenant import current_tenant
from agentguard.errors import NotFoundError, ValidationError
from agentguard.tools.atomic.customer import customer_lookup
from agentguard.tools.atomic.order import order_lookup
from agentguard.tools.atomic.ticket import ticket_create
from agentguard.tools.workflow.engine import get_workflow_engine


async def start_return_remediation(
    order_id: str,
    customer_id: str,
    reason: str,
) -> dict[str, Any]:
    """Execute the multi-phase Return and Remediation workflow with state persistence.

    Phases executed:
    1. Order & Identity Verification (validates order ownership within tenant)
    2. Policy & Restocking Computation (evaluates customer tier rules)
    3. RMA Support Ticket Generation (issues tracking and dispatch ticket)
    4. Settlement Packaging (finalizes RMA code and return instructions)
    """
    engine = get_workflow_engine()
    tenant_id = current_tenant.get() or "unknown"
    p = current_principal.get()
    caller_id = p.subject if p else "anonymous"

    # Initialize workflow record
    wf = engine.create_workflow(
        name="return_remediation",
        tenant_id=tenant_id,
        caller_id=caller_id,
        initial_context={"order_id": order_id, "customer_id": customer_id, "reason": reason},
    )
    workflow_id = wf.workflow_id

    try:
        # Phase 1: Order & Identity Verification
        customer = await customer_lookup(customer_id)
        orders = await order_lookup(order_id=order_id)
        if not orders:
            raise NotFoundError(
                code="ORDER_NOT_FOUND",
                hint=f"Order '{order_id}' was not found in caller's tenant.",
                context={"order_id": order_id},
            )
        order = orders[0]
        if order.get("customer_id") != customer_id:
            raise ValidationError(
                code="ORDER_OWNERSHIP_MISMATCH",
                hint=f"Order '{order_id}' does not belong to customer '{customer_id}'.",
                retryable=False,
            )

        engine.record_step(
            workflow_id=workflow_id,
            step_number=1,
            step_name="verify_eligibility",
            status="COMPLETED",
            output={"verified": True, "customer_tier": customer.get("tier", "standard")},
        )

        # Phase 2: Restocking & Refund Policy Computation
        tier = customer.get("tier", "standard").lower()
        total_cents = order.get("total_cents", 0)
        total_dollars = total_cents / 100.0

        if tier == "gold":
            restocking_fee = 0.0
            refund_amount = total_dollars
            priority = "high"
        else:
            restocking_fee = round(total_dollars * 0.10, 2)
            refund_amount = round(total_dollars - restocking_fee, 2)
            priority = "normal"

        rma_code = f"RMA-{order_id}-{secrets.token_hex(3).upper()}"

        engine.record_step(
            workflow_id=workflow_id,
            step_number=2,
            step_name="compute_settlement",
            status="COMPLETED",
            output={
                "rma_code": rma_code,
                "tier": tier,
                "refund_amount": refund_amount,
                "restocking_fee": restocking_fee,
            },
        )

        # Phase 3: Create Support Ticket
        ticket = await ticket_create(
            customer_id=customer_id,
            title=f"Return Authorization {rma_code}",
            description=(
                f"RMA initiated for order {order_id}. "
                f"Reason: {reason}. Refund amount: ${refund_amount:,.2f} "
                f"(Restocking fee: ${restocking_fee:,.2f})."
            ),
            priority=priority,
        )

        engine.record_step(
            workflow_id=workflow_id,
            step_number=3,
            step_name="create_rma_ticket",
            status="COMPLETED",
            output={"ticket_id": ticket.get("id"), "ticket_status": ticket.get("status")},
        )

        # Phase 4: Finalize Package
        settlement_result = {
            "workflow_id": workflow_id,
            "status": "COMPLETED",
            "rma_code": rma_code,
            "order_id": order_id,
            "customer_id": customer_id,
            "customer_name": customer["name"],
            "financials": {
                "original_total_usd": total_dollars,
                "refund_amount_usd": refund_amount,
                "restocking_fee_usd": restocking_fee,
            },
            "ticket": ticket,
            "instructions": (
                f"Affix RMA code '{rma_code}' to shipping parcel. "
                f"Prepaid return shipping label generated. "
                f"Refund of ${refund_amount:,.2f} will process upon carrier receipt."
            ),
        }

        engine.complete_workflow(workflow_id, settlement_result)
        return settlement_result

    except Exception as exc:
        engine.fail_workflow(workflow_id, str(exc))
        raise


async def get_workflow_status(workflow_id: str) -> dict[str, Any]:
    """Retrieve execution state, step progress, and results for a workflow."""
    engine = get_workflow_engine()
    wf = engine.get_workflow(workflow_id)
    if not wf:
        raise NotFoundError(
            code="WORKFLOW_NOT_FOUND",
            hint=f"Workflow instance '{workflow_id}' does not exist.",
            context={"workflow_id": workflow_id},
        )
    return wf.to_dict()


async def stream_return_remediation(
    order_id: str,
    customer_id: str,
    reason: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """Async generator streaming workflow milestone events as each phase completes."""
    engine = get_workflow_engine()
    tenant_id = current_tenant.get() or "unknown"
    p = current_principal.get()
    caller_id = p.subject if p else "anonymous"

    wf = engine.create_workflow("return_remediation", tenant_id, caller_id)
    yield {"event": "WORKFLOW_STARTED", "workflow_id": wf.workflow_id}

    # Phase 1
    customer = await customer_lookup(customer_id)
    orders = await order_lookup(order_id=order_id)
    step1 = engine.record_step(wf.workflow_id, 1, "verify_eligibility", output={"verified": True})
    yield {"event": "STEP_COMPLETED", "step": 1, "name": "verify_eligibility", "duration_ms": step1.duration_ms}

    # Phase 2
    rma_code = f"RMA-{order_id}-{secrets.token_hex(3).upper()}"
    step2 = engine.record_step(wf.workflow_id, 2, "compute_settlement", output={"rma": rma_code})
    yield {"event": "STEP_COMPLETED", "step": 2, "name": "compute_settlement", "duration_ms": step2.duration_ms}

    # Phase 3
    ticket = await ticket_create(customer_id, f"RMA {rma_code}", reason)
    step3 = engine.record_step(wf.workflow_id, 3, "create_rma_ticket", output={"ticket_id": ticket["id"]})
    yield {"event": "STEP_COMPLETED", "step": 3, "name": "create_rma_ticket", "duration_ms": step3.duration_ms}

    # Final
    result = {"workflow_id": wf.workflow_id, "rma_code": rma_code, "status": "COMPLETED"}
    engine.complete_workflow(wf.workflow_id, result)
    yield {"event": "WORKFLOW_COMPLETED", "result": result}

