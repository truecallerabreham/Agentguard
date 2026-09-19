"""Structured Error Recovery Framework (SERF) for AgentGuard."""

from agentguard.errors.taxonomy import (
    ErrorCategory,
    ToolError,
    AuthError,
    PolicyError,
    ValidationError,
    RateLimitError,
    UpstreamError,
    CircuitBreakerError,
    TimeoutBudgetError,
)
from agentguard.errors.envelope import SERFEnvelope
from agentguard.errors.handlers import create_serf_envelope, serf_protected

__all__ = [
    "ErrorCategory",
    "ToolError",
    "AuthError",
    "PolicyError",
    "ValidationError",
    "RateLimitError",
    "UpstreamError",
    "CircuitBreakerError",
    "TimeoutBudgetError",
    "SERFEnvelope",
    "create_serf_envelope",
    "serf_protected",
]
