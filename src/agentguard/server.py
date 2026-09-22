"""AgentGuard MCP Server supporting stdio, authenticated HTTP, multi-tenant RLS, and input validation."""

from __future__ import annotations
from contextlib import asynccontextmanager
import json
import os
from typing import Any
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
import uvicorn
from mcp.server.fastmcp import FastMCP

from agentguard.config import ServerSettings, get_settings
from agentguard.errors import serf_protected
from agentguard.observability import (
    ObservabilityMiddleware,
    observe_tool,
    generate_metrics_response,
    get_audit_logger,
)
from agentguard.auth.middleware import AuthMiddleware
from agentguard.auth.policy import enforce_policy
from agentguard.governance.tenant import TenantMiddleware
from agentguard.ratelimit import RateLimitMiddleware, get_rate_limiter
from agentguard.cache import cached_tool, get_cache_manager
from agentguard.db.pool import get_db_manager
from agentguard.tools.atomic.postgres import postgres_query as run_postgres_query
from agentguard.tools.base import validate_input
from agentguard.validation.schemas import (
    GreetInput,
    AddInput,
    EchoInput,
    CustomerInput,
    PostgresQueryInput,
)

# Initialize the Model Context Protocol server
mcp = FastMCP("agentguard")


@mcp.tool()
@serf_protected
@observe_tool("greet")
@enforce_policy("greet")
@validate_input(GreetInput)
def greet(name: str = "World") -> str:
    """Return a personalized greeting for an agent or user."""
    return f"Hello, {name}!"


@mcp.tool()
@serf_protected
@observe_tool("add")
@enforce_policy("add")
@validate_input(AddInput)
def add(a: int, b: int) -> int:
    """Add two integers together."""
    return a + b


@mcp.tool()
@serf_protected
@observe_tool("echo")
@enforce_policy("echo")
@validate_input(EchoInput)
def echo(message: str) -> str:
    """Echo back the input message."""
    return f"AgentGuard received: {message}"


@mcp.tool()
@serf_protected
@observe_tool("get_customer")
@enforce_policy("get_customer")
@validate_input(CustomerInput)
@cached_tool(ttl_l1=30, ttl_l2=300)
async def get_customer(customer_id: str) -> str:
    """Fetch customer record by customer ID, strictly isolated to the caller's tenant."""
    rows = await run_postgres_query("SELECT * FROM customers WHERE id = $1", [customer_id])
    if rows:
        return json.dumps(rows[0], indent=2)
    return f"Customer '{customer_id}' not found in caller's tenant records."


@mcp.tool()
@serf_protected
@observe_tool("postgres_query")
@enforce_policy("postgres_query")
@validate_input(PostgresQueryInput)
@cached_tool(ttl_l1=30, ttl_l2=300)
async def postgres_query(sql: str) -> str:
    """Execute a read-only SQL query inside the caller's tenant-isolated database session.

    PostgreSQL Row-Level Security (RLS) automatically ensures that records belonging
    to other tenants are completely invisible to this session.
    """
    rows = await run_postgres_query(sql)
    return json.dumps(rows, indent=2)


def build_http_app(settings: ServerSettings | None = None) -> Starlette:
    """Build the Starlette ASGI application with Observability, Auth, and Tenant isolation middlewares."""
    settings = settings or get_settings()
    app = mcp.sse_app()
    app.add_route("/healthz", lambda req: JSONResponse({"status": "ok"}), methods=["GET"])

    if settings.metrics_enabled:
        def metrics_endpoint(req):
            content, media_type = generate_metrics_response()
            return Response(content=content, media_type=media_type)

        app.add_route("/metrics", metrics_endpoint, methods=["GET"])

    # Starlette wraps middleware in reverse order (outermost to innermost):
    # Request enters: ObservabilityMiddleware -> AuthMiddleware -> TenantMiddleware -> RateLimitMiddleware -> App endpoint
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(TenantMiddleware, settings=settings)
    app.add_middleware(AuthMiddleware, settings=settings)
    if settings.tracing_enabled:
        app.add_middleware(ObservabilityMiddleware)

    @asynccontextmanager
    async def lifespan(asgi_app):
        db = get_db_manager(settings)
        limiter = get_rate_limiter(settings)
        cache = get_cache_manager(settings)
        audit = get_audit_logger(
            log_path=settings.audit_log_path,
            enabled=settings.audit_logging_enabled,
        )
        await db.initialize()
        await limiter.initialize()
        await cache.initialize()
        yield
        await db.close()
        await limiter.close()
        await cache.close()

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
