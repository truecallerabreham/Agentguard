"""Observability decorator for MCP tools: distributed tracing, Prometheus metrics, and audit logging."""

from __future__ import annotations
from functools import wraps
import inspect
import logging
import time
from typing import Any, Callable

from agentguard.auth.oauth import current_principal
from agentguard.governance.tenant import current_tenant
from agentguard.observability.tracing import start_span
from agentguard.observability.metrics import record_tool_call
from agentguard.observability.audit import get_audit_logger

logger = logging.getLogger("agentguard.observability.decorators")


def _get_call_parameters(func: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
    """Extract named parameters from args and kwargs using function signature."""
    try:
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except Exception:
        params = {f"arg_{i}": v for i, v in enumerate(args)}
        params.update(kwargs)
        return params


def _classify_exception(exc: BaseException) -> str:
    """Classify exception into standardized audit and metric status."""
    exc_type = type(exc).__name__
    if "Policy" in exc_type or "Forbidden" in exc_type or "Auth" in exc_type:
        return "DENIED"
    elif "Validation" in exc_type:
        return "INVALID_INPUT"
    elif "RateLimit" in exc_type:
        return "RATE_LIMITED"
    elif "Circuit" in exc_type:
        return "CIRCUIT_OPEN"
    elif "Timeout" in exc_type:
        return "TIMEOUT"
    return "FAILED"


def observe_tool(tool_name: str | None = None) -> Callable:
    """Decorator wrapping an MCP tool with full observability:

    1. Distributed Tracing: Creates a child Span under the active trace context.
    2. Prometheus Metrics: Increments tool call counter and observes execution latency.
    3. Tamper-Proof Audit Logging: Records action, parameters, status, and execution duration.
    """

    def decorator(func: Callable) -> Callable:
        name = tool_name or func.__name__
        audit_logger = get_audit_logger()

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                params = _get_call_parameters(func, args, kwargs)
                tenant = current_tenant.get() or "unknown"
                start_time = time.perf_counter()

                with start_span(
                    f"tool:{name}",
                    attributes={"tool.name": name, "tenant.id": tenant},
                ) as span:
                    try:
                        result = await func(*args, **kwargs)
                        duration = time.perf_counter() - start_time
                        duration_ms = duration * 1000.0

                        record_tool_call(tool=name, tenant=tenant, status="success", duration_sec=duration)
                        audit_logger.log_action(
                            action=f"tool:{name}",
                            parameters=params,
                            status="SUCCESS",
                            execution_time_ms=duration_ms,
                            tenant_id=tenant,
                        )
                        span.set_attribute("tool.status", "SUCCESS")
                        return result
                    except BaseException as exc:
                        duration = time.perf_counter() - start_time
                        duration_ms = duration * 1000.0
                        status = _classify_exception(exc)

                        record_tool_call(tool=name, tenant=tenant, status=status, duration_sec=duration)
                        audit_logger.log_action(
                            action=f"tool:{name}",
                            parameters=params,
                            status=status,
                            execution_time_ms=duration_ms,
                            error={
                                "type": type(exc).__name__,
                                "message": str(exc),
                            },
                            tenant_id=tenant,
                        )
                        span.record_exception(exc)
                        raise

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                params = _get_call_parameters(func, args, kwargs)
                tenant = current_tenant.get() or "unknown"
                start_time = time.perf_counter()

                with start_span(
                    f"tool:{name}",
                    attributes={"tool.name": name, "tenant.id": tenant},
                ) as span:
                    try:
                        result = func(*args, **kwargs)
                        duration = time.perf_counter() - start_time
                        duration_ms = duration * 1000.0

                        record_tool_call(tool=name, tenant=tenant, status="success", duration_sec=duration)
                        audit_logger.log_action(
                            action=f"tool:{name}",
                            parameters=params,
                            status="SUCCESS",
                            execution_time_ms=duration_ms,
                            tenant_id=tenant,
                        )
                        span.set_attribute("tool.status", "SUCCESS")
                        return result
                    except BaseException as exc:
                        duration = time.perf_counter() - start_time
                        duration_ms = duration * 1000.0
                        status = _classify_exception(exc)

                        record_tool_call(tool=name, tenant=tenant, status=status, duration_sec=duration)
                        audit_logger.log_action(
                            action=f"tool:{name}",
                            parameters=params,
                            status=status,
                            execution_time_ms=duration_ms,
                            error={
                                "type": type(exc).__name__,
                                "message": str(exc),
                            },
                            tenant_id=tenant,
                        )
                        span.record_exception(exc)
                        raise

            return sync_wrapper

    return decorator
