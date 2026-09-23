"""Structured Error Recovery Framework (SERF) error taxonomy and categorization."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    """Broad classification of tool and execution failures."""
    AUTHENTICATION = "AUTHENTICATION"  # Missing, expired, or forged token
    AUTHORIZATION = "AUTHORIZATION"    # Token valid, but lacks scope or role
    VALIDATION = "VALIDATION"          # Malformed input schema or SQL mutation
    RATE_LIMIT = "RATE_LIMIT"          # Quota burst exceeded
    UPSTREAM = "UPSTREAM"              # Database, Redis, or downstream API failure
    INTERNAL = "INTERNAL"              # Unexpected runtime failure


@dataclass
class ToolError(Exception):
    """Base class for every error AgentGuard surfaces to an LLM agent."""

    code: str
    category: ErrorCategory = ErrorCategory.INTERNAL
    retryable: bool = False
    hint: str | None = None
    suggested_actions: list[str] = field(default_factory=list)
    context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category.value if isinstance(self.category, ErrorCategory) else str(self.category),
            "retryable": self.retryable,
            "hint": self.hint,
            "suggested_actions": self.suggested_actions,
            "context": self.context or {},
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.hint}" if self.hint else self.code


class AuthError(ToolError):
    """Token missing, expired, forged, or invalid."""

    def __init__(
        self,
        code: str = "AUTH_FAILED",
        hint: str | None = None,
        retryable: bool = False,
        suggested_actions: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            category=ErrorCategory.AUTHENTICATION,
            retryable=retryable,
            hint=hint or "Authentication failed. Provide a valid Bearer token.",
            suggested_actions=suggested_actions or ["Obtain a refreshed OAuth 2.1 access token"],
            context=context,
        )


class PolicyError(ToolError):
    """Caller authenticated but lacks required permission scope or role."""

    def __init__(
        self,
        code: str = "POLICY_DENIED",
        hint: str | None = None,
        retryable: bool = False,
        suggested_actions: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            category=ErrorCategory.AUTHORIZATION,
            retryable=retryable,
            hint=hint or "You do not have permission to invoke this tool.",
            suggested_actions=suggested_actions or ["Use an allowed alternative tool", "Request role elevation"],
            context=context,
        )


class ValidationError(ToolError):
    """Input failed schema or constraint validation."""

    def __init__(
        self,
        code: str = "VALIDATION_ERROR",
        hint: str | None = None,
        retryable: bool = False,
        suggested_actions: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            category=ErrorCategory.VALIDATION,
            retryable=retryable,
            hint=hint or "Invalid argument provided.",
            suggested_actions=suggested_actions or ["Inspect parameter schema and correct the input"],
            context=context,
        )


class NotFoundError(ToolError):
    """Requested resource (e.g. customer, order, workflow) was not found."""

    def __init__(
        self,
        code: str = "NOT_FOUND",
        hint: str | None = None,
        retryable: bool = False,
        suggested_actions: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            category=ErrorCategory.VALIDATION,
            retryable=retryable,
            hint=hint or "The requested resource was not found.",
            suggested_actions=suggested_actions or ["Verify resource identifier and retry", "List available resources"],
            context=context,
        )



class RateLimitError(ToolError):
    """Tenant or agent exceeded burst capacity."""

    def __init__(
        self,
        code: str = "RATE_LIMIT_EXCEEDED",
        hint: str | None = None,
        retry_after: float = 1.0,
        suggested_actions: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        ctx = context or {}
        ctx["retry_after"] = retry_after
        super().__init__(
            code=code,
            category=ErrorCategory.RATE_LIMIT,
            retryable=True,
            hint=hint or f"Rate limit exceeded. Retry after {retry_after}s.",
            suggested_actions=suggested_actions or [f"Pause execution and retry in {retry_after}s"],
            context=ctx,
        )


class UpstreamError(ToolError):
    """Downstream service (PostgreSQL, Redis, external API) failed or timed out."""

    def __init__(
        self,
        code: str = "UPSTREAM_ERROR",
        hint: str | None = None,
        retryable: bool = True,
        suggested_actions: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            category=ErrorCategory.UPSTREAM,
            retryable=retryable,
            hint=hint or "Upstream backend dependency failed or is temporarily unavailable.",
            suggested_actions=suggested_actions or ["Retry with exponential backoff", "Check service status"],
            context=context,
        )


class CircuitBreakerError(UpstreamError):
    """Circuit breaker is OPEN; fast-failing downstream call."""

    def __init__(
        self,
        service: str,
        cooldown_remaining: float,
        context: dict[str, Any] | None = None,
    ) -> None:
        ctx = context or {}
        ctx.update({"service": service, "cooldown_remaining": cooldown_remaining})
        super().__init__(
            code="CIRCUIT_BREAKER_OPEN",
            hint=(
                f"Circuit breaker for service '{service}' is OPEN to prevent cascading failure. "
                f"Cooldown remaining: {cooldown_remaining:.1f}s."
            ),
            retryable=False,
            suggested_actions=[
                f"Wait {cooldown_remaining:.1f}s until circuit enters trial state",
                "Execute fallback tool if available",
            ],
            context=ctx,
        )


class TimeoutBudgetError(UpstreamError):
    """Overall SLA timeout budget exhausted."""

    def __init__(
        self,
        total_budget: float,
        context: dict[str, Any] | None = None,
    ) -> None:
        ctx = context or {}
        ctx["total_budget"] = total_budget
        super().__init__(
            code="TIMEOUT_BUDGET_EXHAUSTED",
            hint=f"Total SLA timeout budget of {total_budget}s was exhausted across workflow steps.",
            retryable=True,
            suggested_actions=["Reduce workflow steps or simplify input query", "Retry operation"],
            context=ctx,
        )
