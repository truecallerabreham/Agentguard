"""Observability stack for AgentGuard: distributed tracing, Prometheus metrics, and tamper-proof audit logging."""

from __future__ import annotations

from agentguard.observability.tracing import (
    Span,
    start_span,
    get_current_trace_id,
    get_current_span_id,
    get_current_traceparent,
    parse_traceparent,
    format_traceparent,
    current_trace_id,
    current_span_id,
    current_traceparent,
)
from agentguard.observability.metrics import (
    generate_metrics_response,
    record_tool_call,
    record_cache_operation,
    record_circuit_breaker_state,
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    ACTIVE_REQUESTS,
    TOOL_CALLS_TOTAL,
    TOOL_DURATION_SECONDS,
    CACHE_OPERATIONS_TOTAL,
    CIRCUIT_BREAKER_STATE,
)
from agentguard.observability.audit import (
    AuditLogger,
    AuditRecord,
    get_audit_logger,
    verify_audit_log,
    sanitize_parameters,
)
from agentguard.observability.middleware import ObservabilityMiddleware
from agentguard.observability.decorators import observe_tool

__all__ = [
    # Tracing
    "Span",
    "start_span",
    "get_current_trace_id",
    "get_current_span_id",
    "get_current_traceparent",
    "parse_traceparent",
    "format_traceparent",
    "current_trace_id",
    "current_span_id",
    "current_traceparent",
    # Metrics
    "generate_metrics_response",
    "record_tool_call",
    "record_cache_operation",
    "record_circuit_breaker_state",
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_DURATION_SECONDS",
    "ACTIVE_REQUESTS",
    "TOOL_CALLS_TOTAL",
    "TOOL_DURATION_SECONDS",
    "CACHE_OPERATIONS_TOTAL",
    "CIRCUIT_BREAKER_STATE",
    # Audit
    "AuditLogger",
    "AuditRecord",
    "get_audit_logger",
    "verify_audit_log",
    "sanitize_parameters",
    # Middleware & Decorators
    "ObservabilityMiddleware",
    "observe_tool",
]
