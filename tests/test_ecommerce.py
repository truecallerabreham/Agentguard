"""Automated test suite for E-Commerce Connectors, Verification, and Refund Gates."""

import asyncio
import json
import pytest

from agentguard.ecommerce.connectors import (
    ShopifyConnector,
    SimulatorStoreConnector,
    WooCommerceConnector,
)
from agentguard.ecommerce.models import (
    OrderFulfillmentStatus,
    StoreConfig,
    StorePlatform,
)
from agentguard.ecommerce.service import EcommerceService, get_ecommerce_service
from agentguard.errors import (
    ApprovalRequiredError,
    NotFoundError,
    PolicyError,
    SSRFViolationError,
    ValidationError,
)
from agentguard.governance.approval import get_approval_manager
from agentguard.tools.ecommerce_tools import (
    ecommerce_evaluate_return,
    ecommerce_execute_refund,
    ecommerce_order_lookup,
    ecommerce_request_refund,
)
from agentguard.tools.registry import get_tool_registry


@pytest.fixture(autouse=True)
def reset_store():
    get_ecommerce_service().reset()


@pytest.fixture
def ecommerce_service():
    """Provides a fresh EcommerceService instance."""
    return EcommerceService()


@pytest.mark.asyncio
async def test_order_lookup_success(ecommerce_service):
    """Verify that order lookup succeeds when order number and billing email match."""
    order = await ecommerce_service.lookup_verified_order(
        store_id="demo-store",
        order_number="1001",
        customer_email="sarah.connor@example.com",
    )
    assert order.order_number == "1001"
    assert order.customer_name == "Sarah Connor"
    assert order.fulfillment_status == OrderFulfillmentStatus.DELIVERED
    assert order.tracking_company == "USPS"
    assert len(order.items) == 2
    assert order.total_cents == 11400


@pytest.mark.asyncio
async def test_order_lookup_privacy_defense_email_mismatch(ecommerce_service):
    """Verify that looking up an order with an incorrect email is blocked with ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        await ecommerce_service.lookup_verified_order(
            store_id="demo-store",
            order_number="1001",
            customer_email="snooper@random.com",
        )
    assert exc_info.value.code == "EMAIL_VERIFICATION_FAILED"


@pytest.mark.asyncio
async def test_order_lookup_not_found(ecommerce_service):
    """Verify that a non-existent order raises NotFoundError."""
    with pytest.raises(NotFoundError) as exc_info:
        await ecommerce_service.lookup_verified_order(
            store_id="demo-store",
            order_number="9999",
            customer_email="sarah.connor@example.com",
        )
    assert exc_info.value.code == "ORDER_NOT_FOUND"


@pytest.mark.asyncio
async def test_return_evaluation_eligible(ecommerce_service):
    """Verify that an order delivered 6 days ago is marked eligible within 30-day window."""
    decision = await ecommerce_service.evaluate_return(
        store_id="demo-store",
        order_number="1001",
        customer_email="sarah.connor@example.com",
        reason="Ear pads are uncomfortable",
    )
    assert decision.eligible is True
    assert decision.status == "ELIGIBLE"
    assert decision.days_since_delivery == 6
    assert decision.total_refund_cents == 11400
    assert decision.requires_human_approval is True


@pytest.mark.asyncio
async def test_return_evaluation_outside_window(ecommerce_service):
    """Verify that an order delivered 48 days ago is rejected for exceeding 30-day window."""
    decision = await ecommerce_service.evaluate_return(
        store_id="demo-store",
        order_number="1003",
        customer_email="elena.rostova@example.com",
        reason="Changed mind",
    )
    assert decision.eligible is False
    assert decision.status == "OUTSIDE_RETURN_WINDOW"
    assert decision.days_since_delivery == 48


@pytest.mark.asyncio
async def test_return_evaluation_in_transit(ecommerce_service):
    """Verify that an undelivered in-transit order cannot be returned."""
    decision = await ecommerce_service.evaluate_return(
        store_id="demo-store",
        order_number="1002",
        customer_email="alex.chen@example.com",
    )
    assert decision.eligible is False
    assert decision.status == "NOT_DELIVERED"


@pytest.mark.asyncio
async def test_hitl_refund_gate_workflow():
    """Verify the end-to-end Human-in-the-Loop refund flow:
    1. Initial refund call triggers ApprovalRequiredError.
    2. Pending approval card exists in ApprovalManager.
    3. Approving with token allows refund settlement.
    4. Replaying the token is blocked.
    """
    manager = get_approval_manager()

    # Step 1: Request refund -> Held by HITL gate
    with pytest.raises(ApprovalRequiredError) as exc_info:
        await ecommerce_request_refund(
            store_id="demo-store",
            order_number="1001",
            customer_email="sarah.connor@example.com",
            amount_cents=11400,
            reason="Defective audio cable",
        )

    approval_id = exc_info.value.approval_id
    token = exc_info.value.context["approval_token"]
    assert approval_id.startswith("appr-")
    assert len(token) > 20

    # Step 2: Confirm pending approval in manager
    pending_list = manager.list_pending()
    assert any(p["approval_id"] == approval_id for p in pending_list)

    # Step 3: Approve and disburse refund using token
    appr = manager.approve(approval_id=approval_id, approver="merchant@lumina.com", token=token)
    assert appr.status.value == "APPROVED"

    result = await ecommerce_execute_refund(
        store_id="demo-store",
        order_number="1001",
        approval_id=approval_id,
        approval_token=token,
        amount_cents=11400,
        reason="Approved by store owner",
    )
    assert result["status"] == "success"
    assert result["amount_cents"] == 11400

    # Step 4: Verify single-use token consumption (replay prevention)
    with pytest.raises(PolicyError) as replay_exc:
        await ecommerce_execute_refund(
            store_id="demo-store",
            order_number="1001",
            approval_id=approval_id,
            approval_token=token,
            amount_cents=11400,
        )
    assert replay_exc.value.code == "APPROVAL_TOKEN_INVALID"


def test_ssrf_prevention_on_store_connectors():
    """Verify that attempting to configure a connector with cloud metadata or loopback IP raises SSRFViolationError."""
    # Cloud metadata IP (AWS/GCP 169.254.169.254)
    with pytest.raises(SSRFViolationError):
        ShopifyConnector(
            StoreConfig(
                store_id="malicious-store",
                store_name="Evil Store",
                platform=StorePlatform.SHOPIFY,
                api_url="http://169.254.169.254",
                api_token="fake_token",
            )
        )

    # Loopback IP
    with pytest.raises(SSRFViolationError):
        WooCommerceConnector(
            StoreConfig(
                store_id="malicious-woo",
                store_name="Evil Woo",
                platform=StorePlatform.WOOCOMMERCE,
                api_url="http://127.0.0.1:8000",
                api_token="key",
                api_secret="secret",
            )
        )


def test_tool_registry_contains_ecommerce_tools():
    """Verify all 4 ecommerce tools are registered in the global ToolRegistry."""
    registry = get_tool_registry()
    for tool_name in (
        "ecommerce_order_lookup",
        "ecommerce_evaluate_return",
        "ecommerce_request_refund",
        "ecommerce_execute_refund",
    ):
        tool = registry.get(tool_name)
        assert tool is not None, f"Tool '{tool_name}' must be registered"
        assert tool.level.value == "COMPOSED"

