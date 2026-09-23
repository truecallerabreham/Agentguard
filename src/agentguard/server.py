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
from agentguard.observability import (
    ObservabilityMiddleware,
    generate_metrics_response,
    get_audit_logger,
)
from agentguard.auth.middleware import AuthMiddleware
from agentguard.governance.tenant import TenantMiddleware
from agentguard.ratelimit import RateLimitMiddleware, get_rate_limiter
from agentguard.cache import get_cache_manager
from agentguard.db.pool import get_db_manager
from agentguard.tools.registry import get_tool_registry

# Initialize the Model Context Protocol server
mcp = FastMCP("agentguard")

# Load and register all Three-Level Tool Hierarchy tools (Atomic, Composed, Workflow)
registry = get_tool_registry()
registry.register_with_mcp(mcp)

# Convenience direct exports for backwards compatibility and programmatic invocation
greet = registry.build_decorated_handler(registry.get("greet"))
add = registry.build_decorated_handler(registry.get("add"))
echo = registry.build_decorated_handler(registry.get("echo"))
get_customer = registry.build_decorated_handler(registry.get("get_customer"))
postgres_query = registry.build_decorated_handler(registry.get("postgres_query"))
order_lookup = registry.build_decorated_handler(registry.get("order_lookup"))
kb_search = registry.build_decorated_handler(registry.get("kb_search"))
ticket_create = registry.build_decorated_handler(registry.get("ticket_create"))
customer_360 = registry.build_decorated_handler(registry.get("customer_360"))
troubleshoot_inquiry = registry.build_decorated_handler(registry.get("troubleshoot_inquiry"))
start_return_remediation = registry.build_decorated_handler(registry.get("start_return_remediation"))
get_workflow_status = registry.build_decorated_handler(registry.get("get_workflow_status"))
fetch_url = registry.build_decorated_handler(registry.get("fetch_url"))
issue_high_risk_refund = registry.build_decorated_handler(registry.get("issue_high_risk_refund"))
list_pending_approvals = registry.build_decorated_handler(registry.get("list_pending_approvals"))
approve_action = registry.build_decorated_handler(registry.get("approve_action"))
reject_action = registry.build_decorated_handler(registry.get("reject_action"))


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
