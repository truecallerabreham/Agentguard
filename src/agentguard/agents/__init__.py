"""AgentGuard Multi-Agent Support Copilot package."""

from __future__ import annotations

from agentguard.agents.base import (
    AgentEvent,
    AgentRole,
    CopilotFinalResult,
    CritiqueReport,
    DraftResponse,
    EvidenceDossier,
    EvidenceItem,
    ExecutionPlan,
    PlanStep,
)
from agentguard.agents.critic import CriticAgent
from agentguard.agents.orchestrator import MultiAgentOrchestrator
from agentguard.agents.planner import PlannerAgent
from agentguard.agents.retriever import RetrieverAgent
from agentguard.agents.synthesizer import SynthesizerAgent

__all__ = [
    "AgentRole",
    "PlanStep",
    "ExecutionPlan",
    "EvidenceItem",
    "EvidenceDossier",
    "DraftResponse",
    "CritiqueReport",
    "AgentEvent",
    "CopilotFinalResult",
    "PlannerAgent",
    "RetrieverAgent",
    "SynthesizerAgent",
    "CriticAgent",
    "MultiAgentOrchestrator",
]
