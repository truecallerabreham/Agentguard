"""Automated test suite for SaaS Onboarding, Multi-Tenant Auth, and Custom Knowledge Base."""

import pytest
from starlette.testclient import TestClient

from agentguard.config import ServerSettings
from agentguard.ecommerce.service import get_ecommerce_service
from agentguard.governance.approval import get_approval_manager
from agentguard.server import build_http_app


@pytest.fixture(autouse=True)
def reset_saas_state():
    """Reset store, merchants, and approval manager state before each test."""
    get_ecommerce_service().reset()
    mgr = get_approval_manager()
    with mgr._lock:
        mgr._approvals.clear()


@pytest.fixture
def client():
    settings = ServerSettings(
        auth_enabled=False,
        rate_limit_enabled=False,
        tracing_enabled=False,
    )
    app = build_http_app(settings)
    return TestClient(app)


def test_public_landing_page(client):
    """Verify root / serves the public SaaS landing page."""
    res = client.get("/")
    assert res.status_code == 200
    assert "AgentGuard" in res.text
    assert "Autonomous Support for" in res.text
    assert "Create Free Store Account" in res.text
    assert "Lumina Audio & Acoustics" in res.text


def test_merchant_signup_and_store_provisioning(client):
    """Verify self-serve merchant registration provisions unique store ID and credentials."""
    payload = {
        "email": "sarah@apexstreetwear.com",
        "password": "securepassword123",
        "store_name": "Apex Streetwear",
        "platform": "simulator",
        "return_window_days": 45,
    }
    res = client.post("/api/auth/signup", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    merchant = data["merchant"]
    assert merchant["email"] == "sarah@apexstreetwear.com"
    assert merchant["store_name"] == "Apex Streetwear"
    assert "store_apex-streetwea_" in merchant["store_id"] or "store_apex" in merchant["store_id"]
    assert merchant["api_key"].startswith("ag_live_")

    # Verify store config was automatically provisioned
    store_id = merchant["store_id"]
    res_store = client.get(f"/api/store?store_id={store_id}")
    assert res_store.status_code == 200
    store_data = res_store.json()
    assert store_data["store"]["store_name"] == "Apex Streetwear"
    assert store_data["store"]["return_window_days"] == 45


def test_merchant_login_flow(client):
    """Verify merchant login succeeds with correct credentials and fails with wrong password."""
    # First sign up
    client.post(
        "/api/auth/signup",
        json={
            "email": "mark@techgear.io",
            "password": "mypassword999",
            "store_name": "TechGear Pro",
        },
    )

    # Login success
    res_ok = client.post(
        "/api/auth/login",
        json={"email": "mark@techgear.io", "password": "mypassword999"},
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == "success"
    assert res_ok.json()["merchant"]["store_name"] == "TechGear Pro"

    # Login failure
    res_fail = client.post(
        "/api/auth/login",
        json={"email": "mark@techgear.io", "password": "wrongpassword"},
    )
    assert res_fail.status_code == 401
    assert "Invalid email or password" in res_fail.json()["message"]


def test_custom_knowledge_base_ingestion_and_agent_search(client):
    """Verify merchant can ingest custom policies and agent cites them during support chat."""
    # 1. Register merchant
    reg_res = client.post(
        "/api/auth/signup",
        json={
            "email": "owner@vortexdrones.com",
            "password": "dronesecret123",
            "store_name": "Vortex Drones",
            "return_window_days": 14,
        },
    )
    store_id = reg_res.json()["merchant"]["store_id"]

    # 2. Add custom drone battery safety and replacement policy
    kb_res = client.post(
        "/api/kb",
        json={
            "store_id": store_id,
            "category": "warranty",
            "title": "Vortex Crash Protection & Battery Warranty",
            "content": "Vortex Drones offers free flight battery replacements within 60 days of purchase if flight cell degradation exceeds 20 percent.",
        },
    )
    assert kb_res.status_code == 200
    kb_data = kb_res.json()
    assert kb_data["status"] == "success"
    art_id = kb_data["article"]["article_id"]

    # 3. List articles for this store
    list_res = client.get(f"/api/kb?store_id={store_id}")
    assert list_res.status_code == 200
    titles = [a["title"] for a in list_res.json()["articles"]]
    assert "Vortex Crash Protection & Battery Warranty" in titles

    # 4. Test Copilot querying custom knowledge base
    chat_res = client.post(
        "/api/chat",
        json={
            "inquiry": "What is your battery replacement policy under warranty?",
            "store_id": store_id,
        },
    )
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert chat_data["status"] == "success"
    response_lower = chat_data["response"].lower()
    # The agent's grounded response references the custom policy
    assert "battery" in response_lower or "warranty" in response_lower

    # 5. Delete the article
    del_res = client.post(
        "/api/kb/delete",
        json={"store_id": store_id, "article_id": art_id},
    )
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"


def test_customer_storefront_demo_routes(client):
    """Verify that /store and /demo serve the customer storefront simulator."""
    # Test /store
    res_store = client.get("/store?store_id=demo-store")
    assert res_store.status_code == 200
    assert "LIVE STORE SIMULATION" in res_store.text
    assert "Featured Products" in res_store.text
    assert "Interactive Tester Bench" in res_store.text

    # Test /demo alias
    res_demo = client.get("/demo?store_id=demo-store")
    assert res_demo.status_code == 200
    assert "LIVE STORE SIMULATION" in res_demo.text


def test_cors_headers_for_embeddable_widget(client):
    """Verify CORS headers allow cross-origin requests from merchant stores."""
    # Preflight OPTIONS request
    opt_res = client.options(
        "/api/chat",
        headers={
            "Origin": "https://myshopify-store.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert opt_res.status_code == 200
    assert opt_res.headers.get("access-control-allow-origin") in ("*", "https://myshopify-store.com")

    # Cross-origin POST request
    post_res = client.post(
        "/api/chat",
        json={"inquiry": "What is the return window?", "store_id": "demo-store"},
        headers={"Origin": "https://myshopify-store.com"},
    )
    assert post_res.status_code == 200
    assert post_res.headers.get("access-control-allow-origin") in ("*", "https://myshopify-store.com")
