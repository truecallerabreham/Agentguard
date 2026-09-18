"""AgentGuard MCP Server supporting stdio, authenticated HTTP, and multi-tenant RLS."""

from __future__ import annotations
from contextlib import asynccontextmanager
import json
import os
from typing import Any
from starlette.applications import Starlette
from starlette.responses import JSONResponse
import uvicorn
from mcp.server.fastmcp import FastMCP

from agentguard.config import get_settings
from agentguard.auth.middleware import AuthMiddleware
from agentguard.governance.tenant import TenantMiddleware
from agentguard.db.pool import get_db_manager
from agentguard.tools.atomic.postgres import postgres_query as run_postgres_query

# Initialize the Model Context Protocol server
mcp = FastMCP("agentguard")


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
async def postgres_query(sql: str) -> str:
    """Execute a read-only SQL query inside the caller's tenant-isolated database session.

    PostgreSQL Row-Level Security (RLS) automatically ensures that records belonging
    to other tenants are completely invisible to this session.
    """
    rows = await run_postgres_query(sql)
    return json.dumps(rows, indent=2)


@mcp.tool()
async def get_customer(customer_id: str) -> str:
    """Fetch customer record by customer ID, strictly isolated to the caller's tenant."""
    rows = await run_postgres_query("SELECT * FROM customers WHERE id = $1", [customer_id])
    if rows:
        return json.dumps(rows[0], indent=2)
    return f"Customer '{customer_id}' not found in caller's tenant records."


def build_http_app(settings: ServerSettings | None = None) -> Starlette:
    """Build the Starlette ASGI application with Auth and Tenant isolation middlewares."""
    settings = settings or get_settings()
    app = mcp.sse_app()
    app.add_route("/healthz", lambda req: JSONResponse({"status": "ok"}), methods=["GET"])

    # Starlette wraps middleware in reverse order (outermost to innermost):
    # Request enters: AuthMiddleware -> TenantMiddleware -> App endpoint
    app.add_middleware(TenantMiddleware, settings=settings)
    app.add_middleware(AuthMiddleware, settings=settings)

    @asynccontextmanager
    async def lifespan(asgi_app):
        db = get_db_manager(settings)
        await db.initialize()
        yield
        await db.close()

    app.router.lifespan_context = lifespan
    return app


def main():
    """Run the server using either stdio or HTTP transport based on environment."""
    settings = get_settings()
    transport = os.getenv("AGENTGUARD_TRANSPORT", settings.transport).lower()

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport in ("http", "sse"):
        app = build_http_app()
        uvicorn.run(app, host=settings.http_host, port=settings.http_port)
    else:
        raise ValueError(
            f"Unsupported AGENTGUARD_TRANSPORT: '{transport}'. Valid options are 'stdio' or 'http'."
        )


if __name__ == "__main__":
    main()
