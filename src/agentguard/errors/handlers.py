"""Exception translation and error recovery handlers."""

from __future__ import annotations
import asyncio
from functools import wraps
import logging
from typing import Any, Callable
from pydantic import ValidationError as PydanticValidationError

from agentguard.errors.taxonomy import ErrorCategory, ToolError, ValidationError
from agentguard.errors.envelope import SERFEnvelope

logger = logging.getLogger("agentguard.errors")


def create_serf_envelope(exc: Exception) -> SERFEnvelope:
    """Translate any Python exception into a structured, agent-actionable SERF envelope."""
    # 1. Custom AgentGuard ToolError hierarchy
    if isinstance(exc, ToolError):
        return SERFEnvelope(
            code=exc.code,
            category=exc.category.value if isinstance(exc.category, ErrorCategory) else str(exc.category),
            message=str(exc),
            retryable=exc.retryable,
            hint=exc.hint or "Check the operation parameters and try again.",
            suggested_actions=exc.suggested_actions or ["Review error details and adjust request"],
            context=exc.context or {},
        )

    # 2. Pydantic validation failures
    if isinstance(exc, PydanticValidationError):
        error_items = []
        for err in exc.errors():
            loc = ".".join(str(l) for l in err.get("loc", [])) or "input"
            msg = err.get("msg", "invalid value")
            error_items.append(f"{loc}: {msg}")

        return SERFEnvelope(
            code="INVALID_ARGUMENTS",
            category=ErrorCategory.VALIDATION.value,
            message="Input parameters failed schema validation.",
            retryable=False,
            hint="; ".join(error_items),
            suggested_actions=["Correct parameter types and constraints", "Inspect tool definition schema"],
            context={"validation_errors": exc.errors()},
        )

    # 3. Unhandled unexpected exceptions (suppress internal stack trace for security)
    logger.exception("Unhandled server exception caught in SERF layer: %s", exc)
    return SERFEnvelope(
        code="INTERNAL_SERVER_ERROR",
        category=ErrorCategory.INTERNAL.value,
        message="An unexpected internal server error occurred while processing the request.",
        retryable=True,
        hint="An internal system failure occurred. This is likely transient; retry after a short delay.",
        suggested_actions=[
            "Retry the request using exponential backoff",
            "Contact system administrator if the issue persists",
        ],
        context={"exception_type": exc.__class__.__name__},
    )


def serf_protected(func: Callable) -> Callable:
    """Decorator that intercepts exceptions and returns structured SERF JSON envelopes to agents."""

    if asyncio.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                envelope = create_serf_envelope(exc)
                return envelope.to_mcp_response()
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                envelope = create_serf_envelope(exc)
                return envelope.to_mcp_response()
        return sync_wrapper
