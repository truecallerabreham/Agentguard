"""Starlette middleware: validates OAuth 2.1 bearer tokens on every incoming request."""

from __future__ import annotations
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from agentguard.auth.oauth import current_principal, get_validator
from agentguard.config import ServerSettings
from agentguard.errors import AuthError

# Endpoints that bypass authentication (liveness probes and discovery)
_PUBLIC_PATHS = frozenset({"/.well-known/mcp-server", "/healthz", "/readyz", "/metrics"})


class AuthMiddleware(BaseHTTPMiddleware):
    """Intercepts incoming HTTP requests and enforces valid OAuth 2.1 bearer tokens."""

    def __init__(self, app, settings: ServerSettings):
        super().__init__(app)
        self.settings = settings
        self.validator = get_validator(settings)

    async def dispatch(self, request: Request, call_next):
        # 1. Allow public endpoints (health checks, monitoring, UI dashboard and widget) without authentication
        path = request.url.path
        if (
            path in _PUBLIC_PATHS
            or path in ("/", "/landing", "/dashboard", "/widget.js", "/store", "/demo")
            or path.startswith("/dashboard/")
            or path.startswith("/store/")
            or path.startswith("/demo/")
            or path.startswith("/static/")
            or path.startswith("/api/")
        ):
            return await call_next(request)

        # 2. Extract Authorization header
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return self._unauthenticated("missing_token", "An OAuth 2.1 bearer token is required in the Authorization header.")

        bearer = header[7:].strip()
        if not bearer:
            return self._unauthenticated("empty_token", "Bearer token is empty.")

        # 3. Cryptographically validate the token and extract Principal
        try:
            principal = self.validator.validate(bearer)
        except AuthError as exc:
            return self._unauthenticated(exc.code, exc.hint)

        # 4. Attach verified Principal to request state and task-safe context variable
        request.state.principal = principal
        token = current_principal.set(principal)
        try:
            return await call_next(request)
        finally:
            current_principal.reset(token)

    def _unauthenticated(self, error_code: str, hint: str | None = None) -> JSONResponse:
        """Return RFC 6750 401 Unauthorized response with WWW-Authenticate challenge header."""
        return JSONResponse(
            {"error": error_code, "hint": hint},
            status_code=401,
            headers={
                "WWW-Authenticate": (
                    f'Bearer realm="{self.settings.auth_audience}", '
                    f'error="{error_code}", '
                    f'authorization_uri="{self.settings.auth_issuer}"'
                )
            },
        )

