"""Verification test for Step 1.1: Verify Starlette app routing and endpoints."""

from starlette.testclient import TestClient
from agentguard.server import build_http_app


def test_http_app_endpoints():
    print("1. Initializing Starlette TestClient with AgentGuard HTTP app...")
    app = build_http_app()
    client = TestClient(app)

    print("2. Testing /healthz liveness probe endpoint...")
    response = client.get("/healthz")
    print(f"   Status code: {response.status_code}")
    print(f"   JSON payload: {response.json()}")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "agentguard"
    print("   -> /healthz endpoint works perfectly!")

    print("3. Testing MCP SSE stream endpoint discovery...")
    routes = [r.path for r in app.routes]
    print(f"   Configured routes on Starlette application: {routes}")
    assert "/healthz" in routes
    assert "/sse" in routes
    assert "/messages" in routes
    print("   -> All required HTTP/SSE endpoints are properly mounted!")

    print("\n*** ALL TESTS PASSED: Step 1.1 HTTP transport is fully operational! ***")


if __name__ == "__main__":
    test_http_app_endpoints()

