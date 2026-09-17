"""AgentGuard MCP Server supporting stdio and remote Streamable HTTP transports."""

import os
from starlette.applications import Starlette
from starlette.responses import JSONResponse
import uvicorn
from mcp.server.fastmcp import FastMCP

# Initialize the Model Context Protocol server
mcp = FastMCP("agentguard")

# Simulated confidential customer database (to demonstrate why network auth is required)
MOCK_CUSTOMER_DATABASE = {
    "alice@enterprise.com": {"name": "Alice Smith", "balance": "$45,000", "plan": "Enterprise VIP"},
    "bob@competitor.com": {"name": "Bob Jones", "balance": "$120,000", "plan": "Strategic Partner"},
    "charlie@acme.corp": {"name": "Charlie Brown", "balance": "$850", "plan": "Free Trial"},
}


@mcp.tool()
def greet(name: str = "World") -> str:
    """Return a personalized greeting for an agent or user."""
    return f"Hello, {name}!"


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers together."""
    return a + b


@mcp.tool()
def echo(message: str) -> str:
    """Echo back the input message."""
    return f"AgentGuard received: {message}"


@mcp.tool()
def get_customer(email: str) -> str:
    """Fetch confidential customer records by email address."""
    record = MOCK_CUSTOMER_DATABASE.get(email)
    if record:
        return f"Customer Found: {record['name']}, Balance: {record['balance']}, Plan: {record['plan']}"
    return "Customer not found."


def build_http_app() -> Starlette:
    """Build the Starlette ASGI application serving MCP over Streamable HTTP."""
    app = mcp.sse_app()
    app.add_route("/healthz", lambda req: JSONResponse({"status": "ok"}), methods=["GET"])
    return app


def main():
    """Run the server using either stdio or HTTP transport based on environment."""
    transport = os.getenv("AGENTGUARD_TRANSPORT", "stdio").lower()

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport in ("http", "sse"):
        app = build_http_app()
        uvicorn.run(app, host="0.0.0.0", port=8080)
    else:
        raise ValueError(
            f"Unsupported AGENTGUARD_TRANSPORT: '{transport}'. Valid options are 'stdio' or 'http'."
        )


if __name__ == "__main__":
    main()
