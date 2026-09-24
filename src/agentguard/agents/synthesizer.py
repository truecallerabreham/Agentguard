"""Synthesizer Agent: Synthesizes empirical evidence into empathetic, grounded customer solutions."""

from __future__ import annotations
import logging
from typing import Any

from agentguard.agents.base import AgentRole, DraftResponse, EvidenceDossier
from agentguard.agents.gemini_client import generate_with_gemini

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

        # Check for E-Commerce specific evidence
        ecom_order = None
        ecom_return = None
        ecom_error = None
        for item in dossier.items:
            if item.tool_name == "ecommerce_order_lookup":
                if item.status == "SUCCESS":
                    ecom_order = item.result
                elif item.status in ("FAILED", "ERROR"):
                    ecom_error = item.error
            elif item.tool_name == "ecommerce_evaluate_return" and item.status == "SUCCESS":
                ecom_return = item.result
        
        has_refund_request = any(item.tool_name == "ecommerce_request_refund" for item in dossier.items)

        if ecom_order:
            return await self._draft_ecommerce_response(
                inquiry, ecom_order, ecom_return, revision_guidance, has_refund_request=has_refund_request
            )

        if ecom_error:
            key_findings = [f"Order security verification: {ecom_error}"]
            cited_evidence = [f"Security Gate: {ecom_error}"]
            paragraphs = [
                "Dear Customer,",
                "Thank you for reaching out to customer support.",
                f"For your account security and privacy protection: {ecom_error}",
                "Please verify that you are contacting us with the email address used when placing the order, or provide your order confirmation details so we can assist you safely.",
                "Best regards,\nAgentGuard Support Copilot",
            ]
            return DraftResponse(
                draft_text="\n\n".join(paragraphs),
                key_findings=key_findings,
                cited_evidence=cited_evidence,
                confidence_score=0.98,
            )

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
            title = kb.get("title", "")
            content = kb.get("content", "")
            art_id = kb.get("id") or kb.get("article_id") or "KB"
            cited_evidence.append(f"{art_id}: {title}")
            if "return" in cat or "return" in title.lower():
                if return_policy is None:
                    return_policy = kb
            elif any(w in cat or w in title.lower() for w in ("warranty", "defect", "repair", "replace", "battery")):
                if warranty_policy is None:
                    warranty_policy = kb

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

        # Policy entitlements based on custom knowledge base or tier
        if warranty_policy and any(w in inquiry.lower() for w in ("warranty", "replacement", "defective", "broken", "damage", "battery", "repair")):
            policy_title = warranty_policy.get("title", "Warranty Policy")
            policy_content = warranty_policy.get("content")
            if policy_content and len(policy_content) > 10:
                paragraphs.append(
                    f"Regarding your inquiry: According to our **{policy_title}**, {policy_content}"
                )
            else:
                paragraphs.append(
                    f"Regarding your inquiry: According to our **{policy_title}**, items reported within warranty qualify for an "
                    "immediate direct replacement or a full refund."
                )
            key_findings.append(f"Referenced policy: {policy_title}.")

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

    async def _draft_ecommerce_response(
        self,
        inquiry: str,
        order: dict[str, Any],
        return_decision: dict[str, Any] | None,
        revision_guidance: str | None = None,
        has_refund_request: bool = False,
    ) -> DraftResponse:
        key_findings: list[str] = []
        cited_evidence: list[str] = []

        ord_num = order.get("order_number", "")
        cust_name = order.get("customer_name", "Valued Customer")
        total_usd = order.get("total_usd", 0.0)
        status = order.get("fulfillment_status", "unknown").upper()
        tracking_co = order.get("tracking_company")
        tracking_num = order.get("tracking_number")
        tracking_url = order.get("tracking_url")

        key_findings.append(f"Verified Order #{ord_num} for {cust_name}: Total ${total_usd:.2f}, Status: {status}")
        cited_evidence.append(f"Store Order #{ord_num}: Status={status}, Total=${total_usd:.2f}")

        if tracking_co and tracking_num:
            key_findings.append(f"Carrier Tracking: {tracking_co} ({tracking_num})")
            cited_evidence.append(f"Tracking: {tracking_co} #{tracking_num}")

        if return_decision:
            is_elig = return_decision.get("eligible", False)
            elig_status = return_decision.get("status", "")
            refund_usd = return_decision.get("total_refund_usd", 0.0)
            key_findings.append(f"Return Policy Check: {elig_status} (Eligible={is_elig}, Max Refund=${refund_usd:.2f})")
            cited_evidence.append(f"Return Eligibility: {elig_status} ({return_decision.get('reason')})")

        if has_refund_request:
            key_findings.append(f"Refund request submitted for Order #{ord_num} and queued for human merchant approval.")
            cited_evidence.append("HITL Gate: Refund request pending merchant approval")

        # Try Gemini LLM generation if available
        prompt = (
            f"You are a professional, empathetic customer support AI agent for an online store.\n"
            f"Customer Inquiry: \"{inquiry}\"\n\n"
            f"Verified Store Facts (Ground Truth):\n"
            f"- Customer Name: {cust_name}\n"
            f"- Order Number: #{ord_num}\n"
            f"- Order Total: ${total_usd:.2f}\n"
            f"- Fulfillment Status: {status}\n"
            f"- Carrier: {tracking_co or 'Not yet assigned'}\n"
            f"- Tracking Number: {tracking_num or 'N/A'}\n"
            f"- Tracking URL: {tracking_url or 'N/A'}\n"
        )
        if return_decision:
            prompt += (
                f"- Return Policy Decision: {return_decision.get('status')}\n"
                f"- Return Eligible: {return_decision.get('eligible')}\n"
                f"- Policy Reason: {return_decision.get('reason')}\n"
                f"- Max Refund Amount: ${return_decision.get('total_refund_usd', 0.0):.2f}\n"
            )
        if has_refund_request:
            prompt += "- Refund Status: Refund request submitted to store manager for human approval before payout.\n"
        if revision_guidance:
            prompt += f"\nImportant Revision Note from Critic: {revision_guidance}\n"

        prompt += (
            "\nGuidelines:\n"
            "1. Answer concisely and politely.\n"
            "2. Cite the exact order number, fulfillment status, and carrier tracking details if available.\n"
            "3. If a refund or return is requested, explain the policy eligibility clearly.\n"
            "4. Never invent tracking numbers, delivery dates, or refund confirmations not present in the facts.\n"
        )

        gemini_text = await generate_with_gemini(prompt)
        if gemini_text:
            return DraftResponse(
                draft_text=gemini_text,
                key_findings=key_findings,
                cited_evidence=cited_evidence,
                confidence_score=0.98,
            )

        # Deterministic Fallback if Gemini API key is not present
        paragraphs = [f"Hello {cust_name},", "Thank you for reaching out to store customer support!"]
        if status == "DELIVERED":
            delivered_str = f" via {tracking_co}" if tracking_co else ""
            paragraphs.append(
                f"I checked our records and located Order **#{ord_num}** (${total_usd:.2f}), "
                f"which was successfully delivered{delivered_str}."
            )
            if tracking_num:
                paragraphs.append(f"Tracking Number: **{tracking_num}** ({tracking_co})")
        elif status in ("IN_TRANSIT", "OUT_FOR_DELIVERY"):
            status_text = "is currently out for delivery today" if status == "OUT_FOR_DELIVERY" else "is currently in transit"
            paragraphs.append(f"Good news! Your Order **#{ord_num}** (${total_usd:.2f}) {status_text}.")
            if tracking_num and tracking_co:
                paragraphs.append(
                    f"Carrier: **{tracking_co}** | Tracking Number: **{tracking_num}**\n"
                    f"You can track live progress here: {tracking_url or tracking_num}"
                )
        else:
            paragraphs.append(f"Your Order **#{ord_num}** (${total_usd:.2f}) is currently **{status.lower()}**.")

        if has_refund_request:
            paragraphs.append(
                f"I have submitted a refund request of ${total_usd:.2f} for Order **#{ord_num}**. "
                "Because our security policy requires human authorization for financial disbursements, this request has been queued "
                "in the Merchant Approval Inbox for supervisor review. You will receive an email confirmation once reviewed."
            )
        elif return_decision:
            if return_decision.get("eligible"):
                paragraphs.append(
                    f"Regarding your return inquiry: your order is within our return policy window. "
                    f"I have initiated a return request for ${return_decision.get('total_refund_usd', 0.0):.2f}. "
                    "This has been forwarded to the store manager for human sign-off."
                )
            else:
                paragraphs.append(f"Regarding your return inquiry: {return_decision.get('reason')}")

        paragraphs.append("Please let us know if you need any further assistance!")
        return DraftResponse(
            draft_text="\n\n".join(paragraphs),
            key_findings=key_findings,
            cited_evidence=cited_evidence,
            confidence_score=0.95,
        )


