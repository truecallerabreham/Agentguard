"""Distributed tracing implementing W3C Trace Context and OpenTelemetry integration.

Specifications followed:
- W3C Trace Context Level 1: https://www.w3.org/TR/trace-context/
- Traceparent format: 00-{trace_id}-{parent_id}-{trace_flags}
"""

from __future__ import annotations
from contextvars import ContextVar
from dataclasses import dataclass, field
import logging
import re
import secrets
import time
from typing import Any

logger = logging.getLogger("agentguard.observability.tracing")

# W3C Trace Context regex
# 2-hex version (00) - 32-hex trace_id - 16-hex parent_id - 2-hex trace_flags
W3C_TRACEPARENT_REGEX = re.compile(
    r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)

# Context variables storing the current execution's trace context
current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="")
current_span_id: ContextVar[str] = ContextVar("current_span_id", default="")
current_traceparent: ContextVar[str] = ContextVar("current_traceparent", default="")


def generate_trace_id() -> str:
    """Generate a random 16-byte (32-character hex) W3C trace ID."""
    while True:
        tid = secrets.token_hex(16)
        if tid != "0" * 32:
            return tid


def generate_span_id() -> str:
    """Generate a random 8-byte (16-character hex) W3C span ID."""
    while True:
        sid = secrets.token_hex(8)
        if sid != "0" * 16:
            return sid


def parse_traceparent(header_value: str | None) -> tuple[str, str, str] | None:
    """Parse and validate incoming W3C traceparent header.

    Returns:
        (trace_id, parent_span_id, trace_flags) or None if invalid.
    """
    if not header_value:
        return None

    cleaned = header_value.strip().lower()
    match = W3C_TRACEPARENT_REGEX.match(cleaned)
    if not match:
        return None

    trace_id, parent_id, flags = match.groups()
    if trace_id == "0" * 32 or parent_id == "0" * 16:
        return None

    return trace_id, parent_id, flags


def format_traceparent(trace_id: str, span_id: str, sampled: bool = True) -> str:
    """Format a W3C traceparent header string."""
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


def get_current_trace_id() -> str:
    """Return active trace_id or generate a new one if unset."""
    tid = current_trace_id.get()
    if not tid:
        tid = generate_trace_id()
        current_trace_id.set(tid)
    return tid


def get_current_span_id() -> str:
    """Return active span_id or generate a new one if unset."""
    sid = current_span_id.get()
    if not sid:
        sid = generate_span_id()
        current_span_id.set(sid)
    return sid


def get_current_traceparent() -> str:
    """Return active W3C traceparent string."""
    tp = current_traceparent.get()
    if not tp:
        tp = format_traceparent(get_current_trace_id(), get_current_span_id(), sampled=True)
        current_traceparent.set(tp)
    return tp


@dataclass
class Span:
    """An execution unit representing a single operation within a trace."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    status: str = "UNSET"
    error_message: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def set_attribute(self, key: str, value: Any) -> Span:
        """Set a metadata attribute on this span."""
        self.attributes[key] = value
        return self

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> Span:
        """Record an in-flight milestone event during the span's lifetime."""
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })
        return self

    def record_exception(self, exc: BaseException) -> Span:
        """Record an exception and mark status as ERROR."""
        self.status = "ERROR"
        self.error_message = f"{type(exc).__name__}: {str(exc)}"
        self.attributes["error"] = True
        self.attributes["error.type"] = type(exc).__name__
        self.attributes["error.message"] = str(exc)
        return self

    def finish(self, status: str = "OK") -> None:
        """Mark span as completed."""
        if self.end_time is None:
            self.end_time = time.time()
            if self.status == "UNSET":
                self.status = status

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        end = self.end_time or time.time()
        return round((end - self.start_time) * 1000.0, 3)

    def to_dict(self) -> dict[str, Any]:
        """Serialize span to structured dictionary."""
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_message": self.error_message,
            "attributes": self.attributes,
            "events": self.events,
        }


class SpanContext:
    """Context manager and async context manager for starting and stopping a Span."""

    def __init__(self, name: str, attributes: dict[str, Any] | None = None):
        self.name = name
        self.attributes = attributes or {}
        self.span: Span | None = None
        self._prev_span_id_token = None
        self._prev_traceparent_token = None

    def __enter__(self) -> Span:
        trace_id = get_current_trace_id()
        parent_span_id = current_span_id.get() or None
        span_id = generate_span_id()

        self.span = Span(
            name=self.name,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            attributes=dict(self.attributes),
        )

        self._prev_span_id_token = current_span_id.set(span_id)
        self._prev_traceparent_token = current_traceparent.set(
            format_traceparent(trace_id, span_id, sampled=True)
        )
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            if exc_val is not None:
                self.span.record_exception(exc_val)
            self.span.finish("ERROR" if exc_val is not None else "OK")

        if self._prev_span_id_token:
            current_span_id.reset(self._prev_span_id_token)
        if self._prev_traceparent_token:
            current_traceparent.reset(self._prev_traceparent_token)

    async def __aenter__(self) -> Span:
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


def start_span(name: str, attributes: dict[str, Any] | None = None) -> SpanContext:
    """Start a new span within the current trace context.

    Can be used as a synchronous or asynchronous context manager:
        with start_span("db.query") as span:
            ...

        async with start_span("tool.execute") as span:
            ...
    """
    return SpanContext(name, attributes)
