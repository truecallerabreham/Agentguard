"""Interactive CLI runner for the AgentGuard Multi-Agent Support Copilot."""

from __future__ import annotations
import argparse
import asyncio
import sys

from agentguard.agents.base import AgentEvent
from agentguard.agents.orchestrator import MultiAgentOrchestrator


def format_event(event: AgentEvent) -> str:
    """Format an agent event with color and structure for terminal display."""
    role = event.agent_role.value.upper()
    etype = event.event_type
    msg = event.message

    role_colors = {
        "PLANNER": "\033[94m",     # Blue
        "RETRIEVER": "\033[96m",   # Cyan
        "SYNTHESIZER": "\033[92m", # Green
        "CRITIC": "\033[93m",      # Yellow
        "ORCHESTRATOR": "\033[95m",# Magenta
    }
    reset = "\033[0m"
    bold = "\033[1m"
    color = role_colors.get(role, "")

    return f"{color}{bold}[{role}]{reset} {etype:<20} | {msg}"


async def async_main():
    parser = argparse.ArgumentParser(
        description="AgentGuard Multi-Agent Support Copilot (Planner -> Retriever -> Synthesizer -> Critic)"
    )
    parser.add_argument(
        "--customer",
        "-c",
        default="CUST-1001",
        help="Customer ID (default: CUST-1001)",
    )
    parser.add_argument(
        "--tenant",
        "-t",
        default="acme",
        help="Tenant ID for RLS database isolation (default: acme)",
    )
    parser.add_argument(
        "--inquiry",
        "-i",
        default="Hi, Alicia here. My order o_9001 arrived with a broken cooling fan. Can I get a replacement or refund under warranty?",
        help="Customer inquiry text",
    )
    parser.add_argument(
        "--stream",
        "-s",
        action="store_true",
        default=True,
        help="Stream agent reasoning steps to terminal in real time",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("  AGENTGUARD MULTI-AGENT SUPPORT COPILOT")
    print(f"  Tenant: {args.tenant} | Customer: {args.customer}")
    print(f"  Inquiry: {args.inquiry}")
    print("=" * 80 + "\n")

    def event_streamer(event: AgentEvent):
        if args.stream:
            print(format_event(event))

    orchestrator = MultiAgentOrchestrator()
    result = await orchestrator.run(
        inquiry=args.inquiry,
        tenant_id=args.tenant,
        customer_id=args.customer,
        event_handler=event_streamer,
    )

    print("\n" + "=" * 80)
    print("  FINAL GROUNDED CUSTOMER RESPONSE")
    print("=" * 80)
    print(result.final_response)
    print("\n" + "-" * 80)
    print("  FACTUAL AUDIT SUMMARY")
    print(f"  - Trace ID: {result.trace_id}")
    print(f"  - Critic Score: {result.critique.factual_accuracy_score * 100:.1f}%")
    print(f"  - Passed: {result.critique.passed}")
    print(f"  - Hallucinations Detected: {len(result.critique.hallucinations)}")
    print(f"  - Revisions Made: {result.revisions_count}")
    print(f"  - Total Pipeline Latency: {result.total_duration_ms:.2f}ms")
    print("=" * 80)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
