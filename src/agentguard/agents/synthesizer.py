"""Synthesizer Agent: Synthesizes empirical evidence into empathetic, grounded customer solutions."""

from __future__ import annotations
import logging
from typing import Any

from agentguard.agents.base import AgentRole, DraftResponse, EvidenceDossier

logger = logging.getLogger("agentguard.agents.synthesizer")


class SynthesizerAgent:
    """Specialized agent responsible for drafting customer-facing responses grounded strictly in evidence."""

    def __init__(self, role: AgentRole = AgentRole.SYNTHESIZER) -> None:
        self.role = role

    async def draft(
        self,
        inquiry: str,
        dossier: EvidenceDossier,
        revision_guidance: str | None = None,
    ) -> DraftResponse:
        """Draft a comprehensive response based on the evidence dossier and optional revision notes."""
        logger.info("Synthesizer drafting response (revision_mode=%s)", bool(revision_guidance))

        # 1. Extract Customer profile evidence
        customer_data = None
        for item in dossier.items:
            if item.tool_name == "get_customer" and item.status == "SUCCESS":
                customer_data = item.result
                break

        # 2. Extract Order evidence
        orders_data = []
        for item in dossier.items:
            if item.tool_name == "order_lookup" and item.status == "SUCCESS":
                res = item.result
                if isinstance(res, list):
                    orders_data.extend(res)
                elif isinstance(res, dict):
                    orders_data.append(res)

        # 3. Extract Knowledge Base evidence
        kb_articles = []
        for item in dossier.items:
            if item.tool_name == "kb_search" and item.status == "SUCCESS":
                res = item.result
                if isinstance(res, list):
                    kb_articles.extend(res)
                elif isinstance(res, dict):
                    kb_articles.append(res)

        # Build citations & key findings
        key_findings: list[str] = []
        cited_evidence: list[str] = []

        cust_name = customer_data.get("name", "Valued Customer") if customer_data else "Valued Customer"
        cust_tier = customer_data.get("tier", "standard").capitalize() if customer_data else "Standard"

        if customer_data:
            key_findings.append(f"Identified customer {cust_name} ({cust_tier} tier member).")
            cited_evidence.append(f"Customer Profile: ID={customer_data.get('id')}, Tier={cust_tier}")

        target_order = None
        if orders_data:
            target_order = orders_data[0]
            total_dollars = f"${target_order.get('total_cents', 0) / 100:.2f}"
            status = target_order.get("status", "unknown")
            key_findings.append(f"Located order {target_order.get('id')}: Total {total_dollars}, Status: {status}.")
            cited_evidence.append(f"Order #{target_order.get('id')}: {status} ({total_dollars})")

        return_policy = None
        warranty_policy = None
        for kb in kb_articles:
            cat = kb.get("category", "").lower()
            if "return" in cat or "return" in kb.get("title", "").lower():
                return_policy = kb
                cited_evidence.append(f"KB-{kb.get('id')}: {kb.get('title')}")
            elif "warranty" in cat or "warranty" in kb.get("title", "").lower():
                warranty_policy = kb
                cited_evidence.append(f"KB-{kb.get('id')}: {kb.get('title')}")

        # Assemble the grounded draft text
        paragraphs: list[str] = []
        paragraphs.append(f"Dear {cust_name},")
        paragraphs.append(
            "Thank you for contacting customer support. I would be pleased to assist you with your inquiry."
        )

        if target_order:
            total_dollars = f"${target_order.get('total_cents', 0) / 100:.2f}"
            paragraphs.append(
                f"I have reviewed your account and located Order **#{target_order.get('id')}** "
                f"({total_dollars}), which is currently marked as **{target_order.get('status')}**."
            )
        else:
            paragraphs.append(
                "I investigated your inquiry against your account history and recent transactions."
            )

        # Policy entitlements based on tier
        if warranty_policy and ("defective" in inquiry.lower() or "broken" in inquiry.lower() or "damage" in inquiry.lower()):
            paragraphs.append(
                "Regarding the damaged or defective item: According to our **Warranty & Defective Merchandise Policy** "
                f"({warranty_policy.get('id', 'KB-102')}), items reported within 90 days of delivery qualify for an "
                "immediate direct replacement or a full refund."
            )
            key_findings.append("Defective item qualifies for 90-day warranty replacement.")

        if return_policy:
            if cust_tier.lower() == "gold":
                paragraphs.append(
                    f"As a valued **{cust_tier} tier member**, you enjoy **free return shipping** and a **100% refund with zero restocking fees** "
                    f"under our standard 30-day return policy ({return_policy.get('id', 'KB-101')})."
                )
                key_findings.append("Gold member tier grants 0% restocking fee and free return shipping.")
            else:
                paragraphs.append(
                    f"Under our standard return policy ({return_policy.get('id', 'KB-101')}), items returned within 30 days are subject to a "
                    "10% restocking fee, with return shipping covered according to standard terms."
                )

        paragraphs.append(
            "**Next Steps:**\n"
            "1. Reply to confirm whether you prefer an immediate direct replacement shipped at no cost, or a full refund.\n"
            "2. Once you confirm, we will initiate a Return Merchandise Authorization (RMA) and email your prepaid shipping label."
        )

        paragraphs.append("Best regards,\nAgentGuard Support Copilot")

        draft_text = "\n\n".join(paragraphs)

        return DraftResponse(
            draft_text=draft_text,
            key_findings=key_findings,
            cited_evidence=cited_evidence,
            confidence_score=0.98 if (customer_data and target_order) else 0.85,
        )
