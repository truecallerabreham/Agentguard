"""Automated tests for Gemini Multi-Agent E-Commerce Support Orchestration."""

import pytest
from unittest.mock import AsyncMock, patch

from agentguard.agents.base import AgentRole, CopilotFinalResult
from agentguard.agents.critic import CriticAgent
from agentguard.agents.orchestrator import MultiAgentOrchestrator
from agentguard.agents.planner import PlannerAgent
from agentguard.agents.synthesizer import SynthesizerAgent
from agentguard.agents.gemini_client import get_gemini_client, generate_with_gemini
from agentguard.ecommerce.service import get_ecommerce_service


@pytest.fixture(autouse=True)
def reset_store_state():
    get_ecommerce_service().reset()


@pytest.mark.asyncio
async def test_planner_decomposes_ecommerce_tracking_inquiry():
    """Verify that Planner recognizes order number and email and plans ecommerce_order_lookup."""
    planner = PlannerAgent()
    inquiry = "Where is my order #1001? My email is sarah.connor@example.com."
    plan = await planner.plan(inquiry=inquiry, tenant_id="demo-store")

    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "ecommerce_order_lookup"
    assert step.arguments["order_number"] == "1001"
    assert step.arguments["customer_email"] == "sarah.connor@example.com"


@pytest.mark.asyncio
async def test_planner_decomposes_ecommerce_return_inquiry():
    """Verify that Planner plans both order lookup and return evaluation for refund/return inquiries."""
    planner = PlannerAgent()
    inquiry = "I want a refund for order #1001. My email is sarah.connor@example.com. The product is defective."
    plan = await planner.plan(inquiry=inquiry, tenant_id="demo-store")

    assert len(plan.steps) == 2
    assert plan.steps[0].tool_name == "ecommerce_order_lookup"
    assert plan.steps[1].tool_name == "ecommerce_evaluate_return"
    assert plan.steps[1].arguments["order_number"] == "1001"
    assert plan.steps[1].arguments["customer_email"] == "sarah.connor@example.com"


@pytest.mark.asyncio
async def test_multi_agent_copilot_end_to_end_tracking():
    """Verify full 4-agent Copilot pipeline resolves order tracking with 100% accuracy and 0 hallucinations."""
    orchestrator = MultiAgentOrchestrator()
    inquiry = "Hi, where is my order #1001? My email is sarah.connor@example.com."

    events = []
    def record_event(evt):
        events.append(evt)

    result: CopilotFinalResult = await orchestrator.run(
        inquiry=inquiry,
        tenant_id="demo-store",
        event_handler=record_event,
    )

    assert result is not None
    assert len(result.plan.steps) == 1
    assert result.critique.passed is True
    assert result.critique.factual_accuracy_score == 1.0
    assert len(result.critique.hallucinations) == 0

    # Verify that the final response contains verified ground truth facts
    text = result.final_response
    assert "Sarah Connor" in text or "Sarah" in text
    assert "1001" in text
    assert "USPS" in text
    assert "9400111899562537624128" in text

    # Verify event emission stream
    event_types = [e.event_type for e in events]
    assert "PLANNING_STARTED" in event_types
    assert "PLAN_READY" in event_types
    assert "RETRIEVAL_STARTED" in event_types
    assert "RETRIEVAL_COMPLETED" in event_types
    assert "SYNTHESIS_READY" in event_types
    assert "CRITIQUE_COMPLETED" in event_types


@pytest.mark.asyncio
async def test_multi_agent_copilot_end_to_end_return_evaluation():
    """Verify that Copilot evaluates return policy and reports eligibility accurately."""
    orchestrator = MultiAgentOrchestrator()
    inquiry = "Can I return order #1001? My email is sarah.connor@example.com."

    result = await orchestrator.run(
        inquiry=inquiry,
        tenant_id="demo-store",
    )

    assert result.critique.passed is True
    assert result.critique.factual_accuracy_score == 1.0
    text = result.final_response.lower()
    assert "return" in text
    assert "eligible" in text or "within" in text


@pytest.mark.asyncio
async def test_gemini_integration_mock_generation():
    """Verify that Synthesizer uses Gemini output when generate_with_gemini returns text."""
    synthesizer = SynthesizerAgent()
    dossier = AsyncMock()
    dossier.items = [
        AsyncMock(
            tool_name="ecommerce_order_lookup",
            status="SUCCESS",
            result={
                "order_number": "1001",
                "customer_name": "Sarah Connor",
                "total_usd": 114.00,
                "fulfillment_status": "DELIVERED",
                "tracking_company": "USPS",
                "tracking_number": "9400111899562537624128",
            },
        )
    ]

    mock_gemini_text = (
        "Hello Sarah Connor! Your order #1001 for $114.00 was delivered via USPS (tracking: 9400111899562537624128). "
        "Let us know if you need anything else!"
    )

    with patch("agentguard.agents.synthesizer.generate_with_gemini", return_value=mock_gemini_text):
        draft = await synthesizer.draft(
            inquiry="Where is order #1001 for sarah.connor@example.com?",
            dossier=dossier,
        )

        assert draft.draft_text == mock_gemini_text
        assert draft.confidence_score == 0.98

        # Run Critic on the Gemini generated text
        critic = CriticAgent()
        critique = await critic.audit(draft, dossier)
        assert critique.passed is True
        assert critique.factual_accuracy_score == 1.0
        assert len(critique.hallucinations) == 0
