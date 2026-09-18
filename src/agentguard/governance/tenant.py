"""Multi-tenant context isolation and governance middleware."""

from __future__ import annotations
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agentguard.auth.oauth import Principal
from agentguard.config import ServerSettings, get_settings

# Thread-safe / Task-safe context variable holding the current active tenant
current_tenant: ContextVar[str | None] = ContextVar("current_tenant", default=None)


class TenantMiddleware(BaseHTTPMiddleware):
    """Enforces tenant isolation from validated JWT principal and handles authorized impersonation."""

    def __init__(self, app, settings: ServerSettings | None = None) -> None:
        super().__init__(app)
        self.settings = settings or get_settings()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Public endpoints bypass tenant isolation checks
        if request.url.path in ("/healthz", "/docs", "/openapi.json"):
            return await call_next(request)

        principal: Principal | None = getattr(request.state, "principal", None)
        tenant = principal.tenant if principal else None

        # Check for tenant impersonation header (e.g. for superadmins/platform ops)
        header_name = self.settings.tenant_header
        requested_tenant = request.headers.get(header_name)
        if requested_tenant:
            requested_tenant = requested_tenant.strip()
            # Impersonation requires explicit permission scope
            has_impersonate_scope = principal and (
                principal.has_scope("tenant:*:impersonate")
                or principal.has_scope(f"tenant:{requested_tenant}:impersonate")
                or principal.has_scope("admin")
            )
            if not has_impersonate_scope:
                caller_sub = principal.sub if principal else "anonymous"
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "TENANT_IMPERSONATION_DENIED",
                            "message": (
                                f"Principal '{caller_sub}' lacks permission scope "
                                f"'tenant:*:impersonate' to impersonate tenant '{requested_tenant}'."
                            ),
                        }
                    },
                )
            tenant = requested_tenant

        # If tenant is required, reject requests that have no valid tenant
        if self.settings.require_tenant and not tenant:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "TENANT_REQUIRED",
                        "message": (
                            "Multi-tenant isolation requires a 'tenant' claim in the authenticated token "
                            f"or an authorized '{header_name}' header."
                        ),
                    }
                },
            )

        # Attach tenant to request state and context variable
        request.state.tenant = tenant
        token = current_tenant.set(tenant)

        try:
            return await call_next(request)
        finally:
            current_tenant.reset(token)

