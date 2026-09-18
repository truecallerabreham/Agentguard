"""Structured Error Recovery Framework (SERF) for AgentGuard.

Agents cannot recover from raw Python tracebacks. They recover from structured
errors that provide:
1. code: machine-readable identifier of the failure.
2. retryable: boolean telling the agent whether retrying could succeed.
3. hint: actionable suggestion for the agent on how to adjust its behavior.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolError(Exception):
    """Base class for every error AgentGuard surfaces to an agent."""

    code: str
    retryable: bool = False
    hint: str | None = None
    context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "retryable": self.retryable,
            "hint": self.hint,
            "context": self.context or {},
        }

    def __str__(self) -> str:
        return f"{self.code}: {self.hint}" if self.hint else self.code


class AuthError(ToolError):
    """Token missing, expired, forged, or invalid."""


class PolicyError(ToolError):
    """Caller authenticated but not permitted by policy."""


class ValidationError(ToolError):
    """Input failed schema or constraint validation."""


class UpstreamError(ToolError):
    """Backend (Postgres, Redis, external API) failed."""

