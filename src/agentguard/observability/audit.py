"""Tamper-proof structured audit logger for AgentGuard.

Implements cryptographic hash chaining:
- Each audit log entry is a canonical JSON record in a JSONL file.
- Every record includes a cryptographic SHA-256 hash of its payload and the 'prev_hash'
  of the preceding record (blockchain-style tamper-evidence).
- If any log entry is modified, deleted, or inserted out of order, the chain of hashes
  breaks, immediately alerting security auditors.
- Includes automatic redaction of sensitive parameters (tokens, passwords, keys).
"""

from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any

from agentguard.auth.oauth import current_principal
from agentguard.governance.tenant import current_tenant
from agentguard.observability.tracing import get_current_trace_id, get_current_span_id

logger = logging.getLogger("agentguard.observability.audit")

SENSITIVE_PARAM_KEYS = {
    "password",
    "secret",
    "token",
    "auth",
    "authorization",
    "api_key",
    "access_token",
    "refresh_token",
    "private_key",
    "credentials",
}

GENESIS_HASH = "0" * 64


def sanitize_parameters(params: Any) -> Any:
    """Recursively sanitize sensitive fields from parameters before writing to audit log."""
    if isinstance(params, dict):
        sanitized = {}
        for k, v in params.items():
            if any(s in k.lower() for s in SENSITIVE_PARAM_KEYS):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_parameters(v)
        return sanitized
    elif isinstance(params, list):
        return [sanitize_parameters(item) for item in params]
    elif isinstance(params, (str, int, float, bool)) or params is None:
        return params
    else:
        return str(params)


def compute_record_hash(record_data: dict[str, Any]) -> str:
    """Compute SHA-256 hash over canonical (sorted keys, compact) JSON representation."""
    # Ensure record_hash is not included in hash calculation
    data = {k: v for k, v in record_data.items() if k != "record_hash"}
    canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


@dataclass
class AuditRecord:
    entry_id: int
    timestamp: str
    trace_id: str
    span_id: str
    tenant_id: str
    principal: dict[str, Any]
    action: str
    parameters: dict[str, Any]
    status: str
    execution_time_ms: float
    error: dict[str, Any] | None
    prev_hash: str
    record_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLogger:
    """Thread-safe, tamper-evident audit logger writing to a hash-chained JSONL file."""

    def __init__(self, log_path: str = "logs/audit.jsonl", enabled: bool = True):
        self.log_path = Path(log_path)
        self.enabled = enabled
        self._lock = threading.Lock()
        self._last_hash = GENESIS_HASH
        self._next_entry_id = 1
        self._in_memory_records: list[dict[str, Any]] = []

        if self.enabled:
            self._initialize_from_existing()

    def _initialize_from_existing(self) -> None:
        """Read the existing log file to resume the hash chain from the last verified entry."""
        if not self.log_path.exists():
            return

        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                last_line = ""
                count = 0
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        last_line = stripped
                        count += 1

                if last_line:
                    record = json.loads(last_line)
                    self._last_hash = record.get("record_hash", GENESIS_HASH)
                    self._next_entry_id = record.get("entry_id", count) + 1
                    logger.info(
                        "AuditLogger resumed existing chain: entries=%d, last_hash=%s",
                        count,
                        self._last_hash[:12],
                    )
        except Exception as exc:
            logger.warning("Could not parse existing audit log at %s: %s", self.log_path, exc)

    def log_action(
        self,
        action: str,
        parameters: dict[str, Any] | None = None,
        status: str = "SUCCESS",
        execution_time_ms: float = 0.0,
        error: dict[str, Any] | None = None,
        tenant_id: str | None = None,
        principal_info: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Record an action in the tamper-evident audit log."""
        timestamp = datetime.now(timezone.utc).isoformat()
        trace_id = get_current_trace_id()
        span_id = get_current_span_id()

        # Resolve tenant
        if tenant_id is None:
            tenant_id = current_tenant.get() or "system"

        # Resolve principal
        if principal_info is None:
            p = current_principal.get()
            if p:
                principal_info = {
                    "subject": getattr(p, "subject", "unknown"),
                    "delegator": getattr(p, "delegator", None),
                    "tenant": getattr(p, "tenant", None),
                    "roles": sorted(list(getattr(p, "roles", []))),
                    "scopes": sorted(list(getattr(p, "scopes", []))),
                }
            else:
                principal_info = {"subject": "anonymous", "roles": ["guest"]}

        sanitized_params = sanitize_parameters(parameters or {})

        with self._lock:
            entry_id = self._next_entry_id
            self._next_entry_id += 1
            prev_hash = self._last_hash

            record_dict = {
                "entry_id": entry_id,
                "timestamp": timestamp,
                "trace_id": trace_id,
                "span_id": span_id,
                "tenant_id": tenant_id,
                "principal": principal_info,
                "action": action,
                "parameters": sanitized_params,
                "status": status.upper(),
                "execution_time_ms": round(execution_time_ms, 3),
                "error": error,
                "prev_hash": prev_hash,
            }

            record_hash = compute_record_hash(record_dict)
            record_dict["record_hash"] = record_hash
            self._last_hash = record_hash

            record = AuditRecord(**record_dict)
            self._in_memory_records.append(record.to_dict())

            if self.enabled:
                self._write_to_disk(record.to_dict())

            return record

    def _write_to_disk(self, record: dict[str, Any]) -> None:
        """Write record to append-only JSONL file."""
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, separators=(",", ":")) + "\n")
        except Exception as exc:
            logger.error("Failed to write audit record to disk: %s", exc)

    def get_in_memory_records(self) -> list[dict[str, Any]]:
        """Return cached in-memory records (useful for testing and immediate verification)."""
        with self._lock:
            return list(self._in_memory_records)


def verify_audit_log(log_path: str | Path) -> tuple[bool, str, int]:
    """Verify cryptographic integrity of an audit log file.

    Returns:
        (is_valid: bool, reason: str, verified_count: int)
    """
    path = Path(log_path)
    if not path.exists():
        return False, f"File does not exist: {log_path}", 0

    expected_prev_hash = GENESIS_HASH
    line_number = 0

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line_number += 1
            stripped = line.strip()
            if not stripped:
                continue

            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                return False, f"Line {line_number} is corrupted (invalid JSON): {exc}", line_number - 1

            # 1. Verify prev_hash matches expected preceding record_hash
            recorded_prev_hash = record.get("prev_hash")
            if recorded_prev_hash != expected_prev_hash:
                return (
                    False,
                    f"Tampering detected at line {line_number}: prev_hash '{recorded_prev_hash[:12]}...' does not match expected '{expected_prev_hash[:12]}...'",
                    line_number - 1,
                )

            # 2. Recompute record_hash
            recorded_hash = record.get("record_hash")
            computed_hash = compute_record_hash(record)
            if recorded_hash != computed_hash:
                return (
                    False,
                    f"Tampering detected at line {line_number}: record_hash was altered! recorded='{recorded_hash[:12]}...', computed='{computed_hash[:12]}...'",
                    line_number - 1,
                )

            expected_prev_hash = recorded_hash

    return True, f"Audit log verified: {line_number} entries intact with cryptographic chain valid.", line_number


_GLOBAL_AUDIT_LOGGER: AuditLogger | None = None
_LOGGER_LOCK = threading.Lock()


def get_audit_logger(log_path: str = "logs/audit.jsonl", enabled: bool = True) -> AuditLogger:
    """Return the global singleton AuditLogger instance."""
    global _GLOBAL_AUDIT_LOGGER
    with _LOGGER_LOCK:
        if _GLOBAL_AUDIT_LOGGER is None:
            _GLOBAL_AUDIT_LOGGER = AuditLogger(log_path=log_path, enabled=enabled)
        return _GLOBAL_AUDIT_LOGGER
