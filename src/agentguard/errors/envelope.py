"""Standardized JSON recovery envelopes for LLMs and MCP clients."""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
import json
import time
from typing import Any


@dataclass
class SERFEnvelope:
    """Standardized machine-readable error recovery envelope for autonomous agents."""

    code: str
    category: str
    message: str
    retryable: bool
    hint: str
    suggested_actions: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "ERROR",
            "error": {
                "code": self.code,
                "category": self.category,
                "message": self.message,
                "retryable": self.retryable,
                "hint": self.hint,
                "suggested_actions": self.suggested_actions,
                "context": self.context,
                "timestamp": self.timestamp,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_mcp_response(self) -> str:
        """Formatted string returned directly as tool execution output to the LLM."""
        return self.to_json()
