"""Starlette middleware enforcing distributed token-bucket rate limits."""

from __future__ import annotations
import math
import time
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agentguard.config import ServerSettings, get_settings
from agentguard.ratelimit.limiter import get_rate_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces per-tenant and per-agent token-bucket quotas on incoming HTTP/SSE requests."""

    def __init__(self, app, settings: ServerSettings | None = None) -> None:
        super().__init__(app)
        self.settings = settings or get_settings()
        self.limiter = get_rate_limiter(self.settings)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Public health and monitoring endpoints bypass rate limiting
        if request.url.path in ("/healthz", "/metrics", "/docs", "/openapi.json"):
            return await call_next(request)

        # Extract tenant and agent identifier from request state (populated by upstream middleware)
        tenant = getattr(request.state, "tenant", "default")
        principal = getattr(request.state, "principal", None)
        agent_id = principal.sub if principal else "anonymous"

        # Key partition: ratelimit:{tenant}:{agent}
        rate_key = f"ratelimit:{tenant}:{agent_id}"

        result = await self.limiter.check(rate_key)

        if not result.allowed:
            reset_ts = math.ceil(time.time() + result.retry_after)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded for agent '{agent_id}' in tenant '{tenant}'.",
                        "hint": f"Your burst capacity is exhausted. Retry after {result.retry_after} seconds.",
                        "retryable": True,
                        "retry_after": result.retry_after,
                    }
                },
                headers={
                    "Retry-After": str(math.ceil(result.retry_after)),
                    "X-RateLimit-Limit": str(result.capacity),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(result.capacity)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        return response
