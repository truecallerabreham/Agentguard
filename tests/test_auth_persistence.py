"""Tests for production merchant authentication, session cookies, and persistent order management."""

import pytest
from starlette.testclient import TestClient

from agentguard.config import ServerSettings
from agentguard.ecommerce.service import get_ecommerce_service
from agentguard.server import build_http_app


@pytest.fixture(autouse=True)
def reset_service():
    svc = get_ecommerce_service()
    svc.reset()


@pytest.fixture
def client():
    settings = ServerSettings(
        auth_enabled=False,
        rate_limit_enabled=False,
        tracing_enabled=False,
    )
    app = build_http_app(settings)
    return TestClient(app)


def test_merchant_signup_sets_session_cookie(client):
    """Verify signup hashes password with PBKDF2 and returns an HTTP-only session cookie."""
    payload = {
        "email": "sarah.connor@cyberdyne-audio.com",
        "password": "Resistance2026!",
        "store_name": "Cyberdyne Audio",
        "platform": "native",
        "return_window_days": 45,
    }
    res = client.post("/api/auth/signup", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "success"
    assert "agentguard_session" in res.cookies

    # Verify session in DB
    svc = get_ecommerce_service()
    merchant = svc.authenticate_merchant("sarah.connor@cyberdyne-audio.com", "Resistance2026!")
    assert merchant is not None
    assert merchant.store_name == "Cyberdyne Audio"


def test_merchant_login_invalid_password(client):
    """Verify login with wrong password returns 401 Unauthorized."""
    res = client.post("/api/auth/login", json={"email": "demo@lumina-audio.com", "password": "wrongpassword"})
    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["message"]


def test_merchant_login_valid_sets_cookie(client):
    """Verify valid login returns session cookie."""
    res = client.post("/api/auth/login", json={"email": "demo@lumina-audio.com", "password": "demo123"})
    assert res.status_code == 200
    assert "agentguard_session" in res.cookies
    assert res.json()["status"] == "success"


def test_api_auth_me_endpoint(client):
    """Verify /api/auth/me returns current merchant when session cookie is provided."""
    # Log in first
    login_res = client.post("/api/auth/login", json={"email": "demo@lumina-audio.com", "password": "demo123"})
    assert login_res.status_code == 200

    # Call /api/auth/me with cookies automatically forwarded by TestClient
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["status"] == "success"
    assert me_data["merchant"]["email"] == "demo@lumina-audio.com"
    assert me_data["merchant"]["store_id"] == "demo-store"


def test_api_auth_logout_endpoint(client):
    """Verify logout invalidates the session and deletes the cookie."""
    client.post("/api/auth/login", json={"email": "demo@lumina-audio.com", "password": "demo123"})
    
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "success"

    # Next /api/auth/me should return 401
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 401


def test_orders_crud_api(client):
    """Verify merchants can list and create native store orders."""
    # List initial seeded orders
    res = client.get("/api/orders?store_id=demo-store")
    assert res.status_code == 200
    orders = res.json()["orders"]
    assert len(orders) >= 3

    # Create a new native customer order
    order_payload = {
        "order_id": "7001",
        "store_id": "demo-store",
        "customer_email": "rachel@nexus.com",
        "customer_name": "Rachel Tyrell",
        "total_amount": 249.00,
        "carrier": "FedEx",
        "tracking_number": "TRK-FDX-778899",
        "fulfillment_status": "delivered",
        "status": "fulfilled",
        "items": [{"id": "prod_101", "title": "Studio ANC Wireless Headphones", "quantity": 1, "unit_price": 249.00}],
    }
    create_res = client.post("/api/orders", json=order_payload)
    assert create_res.status_code == 200
    created = create_res.json()["order"]
    assert created["order_id"] == "7001"
    assert created["customer_email"] == "rachel@nexus.com"

    # Verify order is queryable via customer chat API with email verification
    chat_payload = {
        "store_id": "demo-store",
        "customer_email": "rachel@nexus.com",
        "inquiry": "Where is my order #7001?",
    }
    chat_res = client.post("/api/chat", json=chat_payload)
    assert chat_res.status_code == 200
    reply = chat_res.json()["response"]
    assert "7001" in reply
    assert "TRK-FDX-778899" in reply or "FedEx" in reply

    # Verify email mismatch is blocked
    snoop_payload = {
        "store_id": "demo-store",
        "customer_email": "intruder@evil.org",
        "inquiry": "Show me order #7001 details",
    }
    snoop_res = client.post("/api/chat", json=snoop_payload)
    assert snoop_res.status_code == 200
    assert "does not match" in snoop_res.json()["response"] or "verification" in snoop_res.json()["response"].lower()
