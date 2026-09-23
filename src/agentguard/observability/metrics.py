"""Prometheus metrics registry and instrumentation for AgentGuard.

Exposes metrics in standard Prometheus text exposition format:
- Request counters, latencies, and active connections
- MCP tool execution counters and histograms partitioned by tenant and tool
- Two-tier cache hit/miss counters
- Circuit breaker state gauges
"""

from __future__ import annotations
import logging
from typing import Any
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    REGISTRY,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

logger = logging.getLogger("agentguard.observability.metrics")

# Prometheus Metrics Definitions

HTTP_REQUESTS_TOTAL = Counter(
    "agentguard_http_requests_total",
    "Total HTTP requests handled by AgentGuard.",
    ["method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "agentguard_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

ACTIVE_REQUESTS = Gauge(
    "agentguard_active_requests",
    "Number of HTTP requests currently being processed.",
)

TOOL_CALLS_TOTAL = Counter(
    "agentguard_tool_calls_total",
    "Total MCP tool executions partitioned by tool name, tenant, and outcome status.",
    ["tool", "tenant", "status"],
)

TOOL_DURATION_SECONDS = Histogram(
    "agentguard_tool_duration_seconds",
    "MCP tool execution latency in seconds.",
    ["tool"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

CACHE_OPERATIONS_TOTAL = Counter(
    "agentguard_cache_operations_total",
    "Total cache operations by tier (l1/l2) and outcome (hit/miss/set).",
    ["tier", "result"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "agentguard_circuit_breaker_state",
    "Circuit breaker state (0 = CLOSED, 1 = HALF_OPEN, 2 = OPEN).",
    ["service"],
)

ACTIVE_DB_CONNECTIONS = Gauge(
    "agentguard_active_db_connections",
    "Number of active connections in the database connection pool.",
)


def record_tool_call(tool: str, tenant: str, status: str, duration_sec: float) -> None:
    """Record an MCP tool execution in Prometheus metrics."""
    try:
        TOOL_CALLS_TOTAL.labels(tool=tool, tenant=tenant or "unknown", status=status.lower()).inc()
        TOOL_DURATION_SECONDS.labels(tool=tool).observe(duration_sec)
    except Exception as exc:
        logger.debug("Failed to record tool metrics: %s", exc)


def record_cache_operation(tier: str, result: str) -> None:
    """Record a cache hit/miss/set operation."""
    try:
        CACHE_OPERATIONS_TOTAL.labels(tier=tier.lower(), result=result.lower()).inc()
    except Exception as exc:
        logger.debug("Failed to record cache metric: %s", exc)


def record_circuit_breaker_state(service: str, state: str) -> None:
    """Record circuit breaker state transition (0=CLOSED, 1=HALF_OPEN, 2=OPEN)."""
    mapping = {"CLOSED": 0, "HALF_OPEN": 1, "OPEN": 2}
    val = mapping.get(str(state).upper(), 0)
    try:
        CIRCUIT_BREAKER_STATE.labels(service=service).set(val)
    except Exception as exc:
        logger.debug("Failed to record circuit breaker metric: %s", exc)


def generate_metrics_response() -> tuple[bytes, str]:
    """Generate Prometheus exposition format payload and content type header."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST

