"""ASGI middleware for W3C distributed tracing and Prometheus request instrumentation."""

from __future__ import annotations
import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from agentguard.observability.tracing import (
    current_trace_id,
    current_span_id,
    current_traceparent,
    generate_trace_id,
    generate_span_id,
    parse_traceparent,
    format_traceparent,
    start_span,
)
from agentguard.observability.metrics import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    ACTIVE_REQUESTS,
)

logger = logging.getLogger("agentguard.observability.middleware")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Extracts or initiates W3C Trace Context and collects Prometheus HTTP metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 1. Parse or initialize W3C trace context
        incoming_traceparent = request.headers.get("traceparent")
        parsed = parse_traceparent(incoming_traceparent)

        if parsed:
            trace_id, parent_id, _flags = parsed
        else:
            trace_id = generate_trace_id()
            parent_id = None

        server_span_id = generate_span_id()
        outgoing_traceparent = format_traceparent(trace_id, server_span_id, sampled=True)

        # Set context variables for this coroutine/task
        t_token = current_trace_id.set(trace_id)
        s_token = current_span_id.set(server_span_id)
        tp_token = current_traceparent.set(outgoing_traceparent)

        # Store in request.state for downstream access
        request.state.trace_id = trace_id
        request.state.span_id = server_span_id
        request.state.traceparent = outgoing_traceparent

        ACTIVE_REQUESTS.inc()
        start_time = time.perf_counter()

        endpoint_path = request.url.path
        status_code = 500

        try:
            with start_span(
                f"HTTP {request.method} {endpoint_path}",
                attributes={
                    "http.method": request.method,
                    "http.url": str(request.url),
                    "http.route": endpoint_path,
                },
            ) as span:
                response = await call_next(request)
                status_code = response.status_code
                span.set_attribute("http.status_code", status_code)
                return response
        except Exception as exc:
            logger.error("Unhandled exception processing request: %s", exc)
            raise
        finally:
            duration = time.perf_counter() - start_time
            ACTIVE_REQUESTS.dec()

            # Record Prometheus metrics
            try:
                HTTP_REQUESTS_TOTAL.labels(
                    method=request.method,
                    endpoint=endpoint_path,
                    status=str(status_code),
                ).inc()
                HTTP_REQUEST_DURATION_SECONDS.labels(
                    method=request.method,
                    endpoint=endpoint_path,
                ).observe(duration)
            except Exception as exc:
                logger.debug("Failed recording request metrics: %s", exc)

            # Reset contextvars
            current_trace_id.reset(t_token)
            current_span_id.reset(s_token)
            current_traceparent.reset(tp_token)

            # Note: headers are injected on response if response was created
            if "response" in locals() and isinstance(response, Response):
                response.headers["traceparent"] = outgoing_traceparent
                response.headers["X-Trace-Id"] = trace_id

