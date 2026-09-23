"""Multi-Agent Orchestrator: Coordinates Planner, Retriever, Synthesizer, and Critic in an auditable workflow."""

from __future__ import annotations
import inspect
import logging
import secrets
import time
from typing import Any

from agentguard.agents.base import (
    AgentEvent,
    AgentRole,
    CopilotFinalResult,
    DraftResponse,
    EventHandler,
)
from agentguard.agents.critic import CriticAgent
from agentguard.agents.planner import PlannerAgent
from agentguard.agents.retriever import RetrieverAgent
from agentguard.agents.synthesizer import SynthesizerAgent
from agentguard.config import get_settings
from agentguard.governance.tenant import current_tenant
from agentguard.observability.audit import get_audit_logger

logger = logging.getLogger("agentguard.agents.orchestrator")


class MultiAgentOrchestrator:
    """Coordinates the 4-agent team with event streaming, verification loops, and cryptographic audit logging."""

    def __init__(
        self,
        planner: PlannerAgent | None = None,
        retriever: RetrieverAgent | None = None,
        synthesizer: SynthesizerAgent | None = None,
        critic: CriticAgent | None = None,
        max_revisions: int | None = None,
    ) -> None:
        settings = get_settings()
        self.planner = planner or PlannerAgent()
        self.retriever = retriever or RetrieverAgent()
        self.synthesizer = synthesizer or SynthesizerAgent()
        self.critic = critic or CriticAgent()
        self.max_revisions = max_revisions or settings.copilot_max_revisions

    async def _emit(self, event_handler: EventHandler | None, event: AgentEvent) -> None:
        """Helper to invoke event handler whether synchronous or coroutine."""
        if not event_handler:
            return
        try:
            res = event_handler(event)
            if inspect.isawaitable(res):
                await res
        except Exception as exc:
            logger.warning("Event handler raised error during emission: %s", exc)

    async def run(
        self,
        inquiry: str,
        tenant_id: str = "acme",
        customer_id: str | None = None,
        event_handler: EventHandler | None = None,
    ) -> CopilotFinalResult:
        """Run the full end-to-end multi-agent support resolution pipeline."""
        start_time = time.perf_counter()
        trace_id = f"trace-{secrets.token_hex(8)}"
        current_tenant.set(tenant_id)

        logger.info(
            "Starting Multi-Agent Copilot [trace_id=%s, tenant=%s, customer=%s]",
            trace_id,
            tenant_id,
            customer_id,
        )

        # ---------------------------------------------------------------------
        # 1. PLANNER STAGE
        # ---------------------------------------------------------------------
        await self._emit(
            event_handler,
            AgentEvent(
                event_type="PLANNING_STARTED",
                agent_role=AgentRole.PLANNER,
                message="Planner decomposing customer inquiry into structured investigation steps...",
                payload={"inquiry": inquiry, "customer_id": customer_id, "trace_id": trace_id},
            ),
        )

        plan = await self.planner.plan(inquiry=inquiry, customer_id=customer_id, tenant_id=tenant_id)

        await self._emit(
            event_handler,
            AgentEvent(
                event_type="PLAN_READY",
                agent_role=AgentRole.PLANNER,
                message=f"Planner created {len(plan.steps)}-step plan: {plan.rationale}",
                payload=plan.to_dict(),
            ),
        )

        # ---------------------------------------------------------------------
        # 2. RETRIEVER STAGE
        # ---------------------------------------------------------------------
        await self._emit(
            event_handler,
            AgentEvent(
                event_type="RETRIEVAL_STARTED",
                agent_role=AgentRole.RETRIEVER,
                message=f"Retriever executing {len(plan.steps)} tool steps within tenant '{tenant_id}'...",
                payload={"step_count": len(plan.steps)},
            ),
        )

        dossier = await self.retriever.execute_plan(plan=plan, tenant_id=tenant_id)

        await self._emit(
            event_handler,
            AgentEvent(
                event_type="RETRIEVAL_COMPLETED",
                agent_role=AgentRole.RETRIEVER,
                message=dossier.summary,
                payload=dossier.to_dict(),
            ),
        )

        # ---------------------------------------------------------------------
        # 3 & 4. SYNTHESIS & CRITIQUE AUDIT LOOP
        # ---------------------------------------------------------------------
        revision_guidance: str | None = None
        revisions_count = 0
        final_draft: DraftResponse | None = None
        final_critique = None

        for revision_idx in range(self.max_revisions):
            # Synthesizer Turn
            await self._emit(
                event_handler,
                AgentEvent(
                    event_type="SYNTHESIS_STARTED",
                    agent_role=AgentRole.SYNTHESIZER,
                    message=f"Synthesizer drafting response (iteration {revision_idx + 1}/{self.max_revisions})...",
                    payload={"revision_index": revision_idx, "guidance": revision_guidance},
                ),
            )

            draft = await self.synthesizer.draft(
                inquiry=inquiry,
                dossier=dossier,
                revision_guidance=revision_guidance,
            )
            final_draft = draft

            await self._emit(
                event_handler,
                AgentEvent(
                    event_type="SYNTHESIS_READY",
                    agent_role=AgentRole.SYNTHESIZER,
                    message=f"Synthesizer drafted response with {len(draft.key_findings)} key findings.",
                    payload=draft.to_dict(),
                ),
            )

            # Critic Turn
            await self._emit(
                event_handler,
                AgentEvent(
                    event_type="CRITIQUE_STARTED",
                    agent_role=AgentRole.CRITIC,
                    message="Critic auditing draft against retrieved ground-truth evidence...",
                    payload={"draft_length": len(draft.draft_text)},
                ),
            )

            critique = await self.critic.audit(draft=draft, dossier=dossier)
            final_critique = critique

            await self._emit(
                event_handler,
                AgentEvent(
                    event_type="CRITIQUE_COMPLETED",
                    agent_role=AgentRole.CRITIC,
                    message=f"Critic audit completed: passed={critique.passed}, score={critique.factual_accuracy_score:.2f}",
                    payload=critique.to_dict(),
                ),
            )

            if critique.passed:
                logger.info("Critic approved response on iteration %d", revision_idx + 1)
                break
            else:
                revisions_count += 1
                if revision_idx < self.max_revisions - 1:
                    revision_guidance = critique.revision_guidance
                    await self._emit(
                        event_handler,
                        AgentEvent(
                            event_type="REVISION_REQUESTED",
                            agent_role=AgentRole.ORCHESTRATOR,
                            message=f"Critic requested revision: {revision_guidance}",
                            payload={"guidance": revision_guidance},
                        ),
                    )

        total_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # ---------------------------------------------------------------------
        # 5. AUDIT LOGGING & FINALIZATION
        # ---------------------------------------------------------------------
        audit = get_audit_logger()
        audit.log_action(
            action="multi_agent_copilot:resolve",
            parameters={
                "customer_id": customer_id,
                "inquiry": inquiry[:200],
                "steps_executed": len(plan.steps),
                "revisions_count": revisions_count,
                "accuracy_score": final_critique.factual_accuracy_score if final_critique else 0.0,
            },
            status="SUCCESS",
            tenant_id=tenant_id,
            execution_time_ms=total_duration_ms,
        )

        result = CopilotFinalResult(
            inquiry=inquiry,
            tenant_id=tenant_id,
            customer_id=customer_id,
            plan=plan,
            dossier=dossier,
            final_response=final_draft.draft_text if final_draft else "",
            critique=final_critique,
            revisions_count=revisions_count,
            total_duration_ms=total_duration_ms,
            trace_id=trace_id,
        )

        await self._emit(
            event_handler,
            AgentEvent(
                event_type="COPILOT_COMPLETED",
                agent_role=AgentRole.ORCHESTRATOR,
                message=f"Multi-Agent Copilot completed inquiry resolution in {total_duration_ms:.1f}ms.",
                payload={"trace_id": trace_id, "duration_ms": total_duration_ms},
            ),
        )

        return result
