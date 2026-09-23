"""Critic Agent: Audits synthesized responses against empirical evidence for factual accuracy and policy compliance."""

from __future__ import annotations
import logging
import re
from typing import Any

from agentguard.agents.base import AgentRole, CritiqueReport, DraftResponse, EvidenceDossier

logger = logging.getLogger("agentguard.agents.critic")


class CriticAgent:
    """Specialized agent responsible for hallucination detection, grounding cross-checks, and policy auditing."""

    def __init__(self, role: AgentRole = AgentRole.CRITIC) -> None:
        self.role = role

    async def audit(
        self,
        draft: DraftResponse,
        dossier: EvidenceDossier,
    ) -> CritiqueReport:
        """Perform a rigorous verification audit of the draft against ground-truth evidence in the dossier."""
        logger.info("Critic performing verification audit on draft response (%d chars)", len(draft.draft_text))

        hallucinations: list[str] = []
        unsupported_claims: list[str] = []
        compliance_notes: list[str] = []
        score = 1.0

        # 1. Extract known ground-truth entities from the dossier
        ground_customers = set()
        ground_tiers = set()
        ground_orders = set()
        ground_amounts = set()

        for item in dossier.items:
            if item.status != "SUCCESS":
                continue

            if item.tool_name == "get_customer" and isinstance(item.result, dict):
                if "name" in item.result:
                    ground_customers.add(item.result["name"].lower())
                if "tier" in item.result:
                    ground_tiers.add(item.result["tier"].lower())

            elif item.tool_name == "order_lookup":
                rows = item.result if isinstance(item.result, list) else [item.result] if item.result else []
                for row in rows:
                    if isinstance(row, dict):
                        if "id" in row:
                            ground_orders.add(row["id"].lower())
                        if "total_cents" in row:
                            cents = row["total_cents"]
                            dollars = cents / 100
                            ground_amounts.add(f"${dollars:.2f}")
                            ground_amounts.add(f"{dollars:.2f}")

        # 2. Check Order ID mentions in draft
        order_mentions = re.findall(r"\b(o[_-]\d+|ord[_-]\d+)\b", draft.draft_text, re.IGNORECASE)
        for om in order_mentions:
            if om.lower() not in ground_orders:
                hallucinations.append(f"Referenced order '{om}' which does not exist in the retrieved evidence dossier.")
                score -= 0.35

        # 3. Check Dollar amount mentions
        amount_mentions = re.findall(r"\$\d+(?:\.\d{2})?", draft.draft_text)
        for am in amount_mentions:
            if ground_amounts and am not in ground_amounts:
                # If amount is not in order totals, check if it's a known policy fee
                if am not in ("$0.00", "$0"):
                    unsupported_claims.append(f"Financial figure '{am}' was cited without matching order receipt data.")
                    score -= 0.15

        # 4. Check for unverified high-risk commitments (HITL violation check)
        high_risk_phrases = [
            "refund has been processed",
            "refund has been issued",
            "money has been deposited",
            "funds have been sent",
        ]
        for hrp in high_risk_phrases:
            if hrp in draft.draft_text.lower():
                # Verify if an actual refund transaction exists in dossier
                has_refund = any(it.tool_name == "issue_high_risk_refund" and it.status == "SUCCESS" for it in dossier.items)
                if not has_refund:
                    hallucinations.append(
                        f"Prematurely claimed '{hrp}' before obtaining an authorized Human-in-the-Loop refund transaction."
                    )
                    score -= 0.50

        # 5. Policy compliance check
        if "gold" in draft.draft_text.lower():
            if "gold" in ground_tiers:
                compliance_notes.append("Correctly recognized customer's Gold tier entitlements.")
            else:
                unsupported_claims.append("Claimed Gold tier benefits but customer record indicates different tier.")
                score -= 0.20

        # Final score calculation
        score = max(0.0, min(1.0, round(score, 2)))
        passed = (score >= 0.85) and (len(hallucinations) == 0)

        revision_guidance = None
        if not passed:
            guidance_parts = []
            if hallucinations:
                guidance_parts.append("Remove hallucinated entities: " + "; ".join(hallucinations))
            if unsupported_claims:
                guidance_parts.append("Correct unsupported claims: " + "; ".join(unsupported_claims))
            guidance_parts.append("Ensure all order IDs and figures strictly reflect the evidence dossier.")
            revision_guidance = " | ".join(guidance_parts)
            logger.warning("Draft failed Critic audit (score=%.2f): %s", score, revision_guidance)
        else:
            logger.info("Draft PASSED Critic audit with score %.2f", score)

        return CritiqueReport(
            passed=passed,
            factual_accuracy_score=score,
            hallucinations=hallucinations,
            unsupported_claims=unsupported_claims,
            policy_compliance_notes=compliance_notes,
            revision_guidance=revision_guidance,
        )
