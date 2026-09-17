"""AgentGuard — now with dual transport (stdio and Streamable HTTP)."""

from __future__ import annotations

import os
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
import uvicorn

# Initialize the MCP Server
mcp = FastMCP("agentguard")


# Register the greet tool (shared across both stdio and HTTP transports)
@mcp.tool()
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


# Liveness health-check endpoint for load balancers (AWS ALB, Kubernetes)
async def healthz(_request):
    return JSONResponse({"status": "ok", "service": "agentguard"})


def build_http_app() -> Starlette:
    """Build the production Starlette ASGI web application.
    
    Exposes:
    - /healthz: Liveness probe for load balancers
    - /sse: Server-Sent Events stream for MCP notifications and responses
    - /messages: Endpoint for clients to POST JSON-RPC messages to the server
    """
    # Obtain the MCP HTTP/SSE sub-application
    app = mcp.sse_app()

    # Add the top-level /healthz route for load balancer monitoring
    app.add_route("/healthz", healthz, methods=["GET"])

    return app


def run_stdio() -> None:
    """Run the server using stdio transport (stdin/stdout)."""
    mcp.run(transport="stdio")


def main() -> None:
    transport = os.environ.get("AGENTGUARD_TRANSPORT", "stdio")

    if transport == "stdio":
        run_stdio()
    else:
        # Build and launch the HTTP web application on port 8080
        app = build_http_app()
        uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
