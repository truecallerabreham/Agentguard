"""Stateful Workflow Engine tracking multi-phase, long-running agent workflows."""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import threading
import time
from typing import Any, AsyncGenerator
import uuid


class WorkflowStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    CHECKPOINT = "CHECKPOINT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class WorkflowStep:
    step_number: int
    name: str
    status: str = "PENDING"
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    output: dict[str, Any] | None = None
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        end = self.completed_at or time.time()
        return round((end - self.started_at) * 1000.0, 2)


@dataclass
class WorkflowExecution:
    workflow_id: str
    name: str
    tenant_id: str
    caller_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    steps: list[WorkflowStep] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class WorkflowEngine:
    """Thread-safe in-memory engine managing stateful agent workflows."""

    def __init__(self) -> None:
        self._workflows: dict[str, WorkflowExecution] = {}
        self._lock = threading.Lock()

    def create_workflow(
        self,
        name: str,
        tenant_id: str,
        caller_id: str,
        initial_context: dict[str, Any] | None = None,
    ) -> WorkflowExecution:
        workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        wf = WorkflowExecution(
            workflow_id=workflow_id,
            name=name,
            tenant_id=tenant_id,
            caller_id=caller_id,
            status=WorkflowStatus.RUNNING,
            context=dict(initial_context or {}),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._workflows[workflow_id] = wf
        return wf

    def get_workflow(self, workflow_id: str) -> WorkflowExecution | None:
        with self._lock:
            return self._workflows.get(workflow_id)

    def list_workflows(self, tenant_id: str) -> list[WorkflowExecution]:
        with self._lock:
            return [wf for wf in self._workflows.values() if wf.tenant_id == tenant_id]

    def record_step(
        self,
        workflow_id: str,
        step_number: int,
        step_name: str,
        status: str = "COMPLETED",
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> WorkflowStep | None:
        with self._lock:
            wf = self._workflows.get(workflow_id)
            if not wf:
                return None
            
            step = WorkflowStep(
                step_number=step_number,
                name=step_name,
                status=status,
                completed_at=time.time(),
                output=output,
                error=error,
            )
            wf.steps.append(step)
            wf.status = WorkflowStatus.CHECKPOINT
            wf.updated_at = datetime.now(timezone.utc).isoformat()
            return step

    def complete_workflow(
        self,
        workflow_id: str,
        result: dict[str, Any],
    ) -> WorkflowExecution | None:
        with self._lock:
            wf = self._workflows.get(workflow_id)
            if not wf:
                return None
            wf.status = WorkflowStatus.COMPLETED
            wf.result = result
            wf.updated_at = datetime.now(timezone.utc).isoformat()
            return wf

    def fail_workflow(
        self,
        workflow_id: str,
        error: str,
    ) -> WorkflowExecution | None:
        with self._lock:
            wf = self._workflows.get(workflow_id)
            if not wf:
                return None
            wf.status = WorkflowStatus.FAILED
            wf.error = error
            wf.updated_at = datetime.now(timezone.utc).isoformat()
            return wf


_GLOBAL_ENGINE: WorkflowEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_workflow_engine() -> WorkflowEngine:
    """Singleton getter for WorkflowEngine."""
    global _GLOBAL_ENGINE
    with _ENGINE_LOCK:
        if _GLOBAL_ENGINE is None:
            _GLOBAL_ENGINE = WorkflowEngine()
        return _GLOBAL_ENGINE

