"""Tests for Merchant Control Panel and Widget HTTP API Routes."""

import json
import pytest
from starlette.testclient import TestClient

from agentguard.config import ServerSettings
from agentguard.ecommerce.service import get_ecommerce_service
from agentguard.governance.approval import get_approval_manager
from agentguard.server import build_http_app


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset store and approval state before each test."""
    get_ecommerce_service().reset()
    mgr = get_approval_manager()
    with mgr._lock:
        mgr._approvals.clear()


@pytest.fixture
def client():
    """Build test client for the Starlette app."""
    settings = ServerSettings(
        auth_enabled=False,
        rate_limit_enabled=False,
        tracing_enabled=False,
    )
    app = build_http_app(settings)
    return TestClient(app)


def test_dashboard_routes(client):
    """Verify that / and /dashboard serve the Merchant Control Panel HTML."""
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "AgentGuard" in res_root.text
    assert "Live Support Console" in res_root.text

    res_dash = client.get("/dashboard")
    assert res_dash.status_code == 200
    assert "AgentGuard" in res_dash.text


def test_widget_script_route(client):
    """Verify that /widget.js serves the customer embeddable JavaScript."""
    res = client.get("/widget.js")
    assert res.status_code == 200
    assert "application/javascript" in res.headers["content-type"]
    assert "ag-widget-container" in res.text
    assert "Lumina Audio Support" in res.text


def test_store_config_get_and_post(client):
    """Verify reading and updating store configuration via /api/store."""
    # GET default store
    res_get = client.get("/api/store?store_id=demo-store")
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["status"] == "success"
    assert data["store"]["store_id"] == "demo-store"
    assert data["store"]["return_window_days"] == 30

    # POST update store
    res_post = client.post(
        "/api/store",
        json={
            "store_id": "demo-store",
            "store_name": "Lumina Audio Pro Shop",
            "platform": "simulator",
            "api_url": "https://pro.lumina-audio.com",
            "return_window_days": 45,
        },
    )
    assert res_post.status_code == 200
    post_data = res_post.json()
    assert post_data["store"]["store_name"] == "Lumina Audio Pro Shop"
    assert post_data["store"]["return_window_days"] == 45


def test_api_chat_order_tracking(client):
    """Verify /api/chat handles WISMO order tracking."""
    res = client.post(
        "/api/chat",
        json={
            "inquiry": "Where is my order #1001?",
            "store_id": "demo-store",
            "customer_email": "sarah.connor@example.com",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "1001" in data["response"]
    assert "critique" in data
    assert data["critique"]["passed"] is True
    assert len(data["plan"]) > 0


def test_api_chat_return_requires_approval(client):
    """Verify /api/chat handles return request and queues HITL approval."""
    res = client.post(
        "/api/chat",
        json={
            "inquiry": "I want to return order #1001 because the sound is defective. Can I get a refund?",
            "store_id": "demo-store",
            "customer_email": "sarah.connor@example.com",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    # Response mentions approval / review
    assert any(term in data["response"].lower() for term in ["approval", "submitted", "review", "merchant", "human"])

    # Verify pending approvals endpoint sees the request
    res_approvals = client.get("/api/approvals")
    assert res_approvals.status_code == 200
    appr_data = res_approvals.json()
    assert len(appr_data["approvals"]) >= 1

    pending_id = appr_data["approvals"][0]["approval_id"]

    # Test approving the request via /api/approvals/decide
    res_decide = client.post(
        "/api/approvals/decide",
        json={
            "approval_id": pending_id,
            "decision": "approve",
            "reason": "Authorized by QA Test Suite",
        },
    )
    assert res_decide.status_code == 200
    decide_data = res_decide.json()
    assert decide_data["decision"] == "approved"
    assert "settlement" in decide_data
    assert decide_data["settlement"]["status"].lower() in ("success", "settled")


def test_api_chat_privacy_snooping_blocked(client):
    """Verify unauthorized email gets rejected without revealing order details."""
    res = client.post(
        "/api/chat",
        json={
            "inquiry": "Where is order #1001?",
            "store_id": "demo-store",
            "customer_email": "attacker@evil.com",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    # Does NOT reveal tracking number or items
    assert "TRK-LUMINA-1001" not in data["response"]


def test_api_audit_log(client):
    """Verify cryptographic audit log API endpoint."""
    res = client.get("/api/audit")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "chain_valid" in data
    assert isinstance(data["entries"], list)
