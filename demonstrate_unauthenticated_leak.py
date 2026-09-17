"""Demonstration for Step 1.3: The Security Hazard of Unauthenticated HTTP MCP Servers.

This simulates an unauthorized attacker on the network calling an internal database query tool
without providing any credentials, tokens, or passwords.
"""

from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

# Simulated database containing confidential enterprise data
MOCK_CUSTOMER_DATABASE = {
    "alice@enterprise.com": {"name": "Alice Smith", "balance": "$45,000", "plan": "Enterprise VIP"},
    "bob@competitor.com": {"name": "Bob Jones", "balance": "$120,000", "plan": "Strategic Partner"},
    "charlie@acme.corp": {"name": "Charlie Brown", "balance": "$850", "plan": "Free Trial"},
}

mcp = FastMCP("agentguard-vulnerable")


# Suppose an engineer adds a database lookup tool to the server:
@mcp.tool()
def get_customer(email: str) -> str:
    """Fetch confidential customer records by email address."""
    record = MOCK_CUSTOMER_DATABASE.get(email)
    if record:
        return f"Customer Found: {record['name']}, Balance: {record['balance']}, Plan: {record['plan']}"
    return "Customer not found."


def build_vulnerable_app() -> Starlette:
    app = mcp.sse_app()
    app.add_route("/healthz", lambda req: JSONResponse({"status": "ok"}), methods=["GET"])
    return app


def demonstrate_unauthenticated_attack():
    print("==========================================================================")
    print(" STEP 1.3: THE SECURITY DISASTER — UNRESTRICTED PUBLIC TOOL EXECUTION")
    print("==========================================================================")
    
    app = build_vulnerable_app()
    client = TestClient(app)

    print("\n[ATTACK SCENARIO]:")
    print("An unknown attacker from outside the company network discovers our port 8080.")
    print("They send NO Authorization header, NO API key, and NO user credentials.\n")

    target_emails = [
        "alice@enterprise.com",
        "bob@competitor.com",
        "charlie@acme.corp"
    ]

    print("[ATTACK IN PROGRESS]: Scraping private customer records...")
    for email in target_emails:
        # Attacker directly invokes the tool function through the unprotected interface
        result = get_customer(email)
        print(f"   Exfiltrated: {result}")

    print("\n[RESULT]: CATASTROPHIC DATA LEAK.")
    print("Because HTTP transport has NO authentication layer, ANY anonymous client")
    print("can query databases, execute code, or exfiltrate private customer data.")
    print("==========================================================================")


if __name__ == "__main__":
    demonstrate_unauthenticated_attack()

