---
title: AgentGuard Autonomous E-Commerce Support Agent - Plan
type: feat
date: 2026-09-23
topic: agentguard-ecommerce-support-agent
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-brainstorm
execution: code
---

# AgentGuard Autonomous E-Commerce Support Agent - Plan

## Goal Capsule

**Objective**: Small e-commerce store owners (Shopify & WooCommerce) connect their store in 2 minutes, embed a modern chat widget, and let an autonomous, grounded AI agent resolve real customer inquiries (order tracking, return remediation, damaged item claims) while enforcing human approval before issuing financial refunds.

**Means**: Connect AgentGuard's multi-agent governance engine to real e-commerce APIs (Shopify REST/GraphQL & WooCommerce REST API), authenticate customer inquiries via Order Number + Email, execute live order/return workflows, and provide a merchant control dashboard for 1-click refund approvals and audit verification.

**Product Authority**: Autonomous E-Commerce Support & Operational Governance. General B2B enterprise IT ticketing, non-commerce sectors, and complex warehouse logistics ERP integrations are out of active scope.

**Open Blockers**: None.

---

## Product Contract

### Summary

AgentGuard becomes a free, production-ready **Autonomous E-Commerce Customer Support Agent** engineered specifically for small online stores. Unlike generic FAQ chatbots, this agent takes real action: it connects directly to Shopify and WooCommerce stores, verifies customer identity via Order # + Email, queries real-time order/fulfillment statuses, diagnoses return eligibility, and drafts return/exchange resolutions. High-risk financial actions (issuing refunds or canceling fulfilled orders) are intercepted by AgentGuard's Human-in-the-Loop (HITL) approval gates, giving the merchant 1-click review in their dashboard.

### Problem Frame

Small e-commerce merchants are overwhelmed by repetitive post-purchase tickets: "Where is my order?", "Can I return this?", "My item arrived damaged, give me a refund." 

Existing solutions fail small merchants:
1. **Rule-based/FAQ Chatbots (Tidio, Crisp, Gorgias basic)**: Cannot execute real transactional actions or look up dynamic order tracking without expensive enterprise tiers ($60–$300/mo). They just spit back static FAQ links, frustrating customers.
2. **Unconstrained Autonomous AI Agents**: Dangerous to deploy because hallucinations can cause an AI agent to promise free products, grant unauthorized $500 refunds, or leak customer order details to strangers.
3. **Privacy & Security Risks**: Without identity verification, anyone typing a random order ID could view someone else's shipping address and purchased items.

### Key Decisions

- **E-Commerce Sector Focus** (session-settled: user-directed — chosen over general FAQ or healthcare/real-estate: e-commerce has immediate transactional pain and directly leverages order lookup, return remediation, and refund tools). Governs R1, R2.
- **Real Platform Integrations: Shopify & WooCommerce** (session-settled: user-directed — store owners connect real store APIs to query live orders and products). Governs R2.
- **Real Operational Actions, Not FAQ Retrieval** (session-settled: user-directed — agent looks up orders, processes return workflows, checks inventory, and initiates refund approvals). Governs R3, R4.
- **Privacy Defense via Order # + Email Verification** (session-settled: user-directed — customers must provide both Order Number and matching Billing Email to inspect order details, preventing snooping). Governs R3.
- **Human-in-the-Loop (HITL) Approval for Financial Transactions** (session-settled: user-directed — agent calculates refund eligibility based on store policy but cannot execute payouts without merchant 1-click sign-off). Governs R5.
- **Gemini LLM Backbone with Critic Verification** (session-settled: user-directed — multi-agent team uses Gemini for natural conversation, while Critic verifies that tracking numbers, amounts, and dates exactly match store data before sending). Governs R4.

### Actors

- A1. **Store Merchant (Owner)** — Signs up, connects Shopify/WooCommerce store API credentials, defines return/refund policy rules (e.g. 30-day window), embeds the widget, and reviews pending refund approvals.
- A2. **Store Customer (Shopper)** — Visits the merchant's online store, opens the chat widget, inputs Order # + Email, and receives instant resolution for order tracking, returns, or product inquiries.
- A3. **AgentGuard Multi-Agent Engine**:
  - **Planner Agent**: Interprets the customer's request (e.g. tracking check vs return vs damaged item claim).
  - **Retriever Agent**: Calls Shopify/WooCommerce tools to pull live order line items, fulfillment tracking, and store policies.
  - **Synthesizer Agent (Gemini)**: Formulates an empathetic, accurate, brand-aligned resolution.
  - **Critic Agent**: Cross-checks synthesized claims against live order facts (prevents hallucinated dates or unauthorized refund promises).

---

### Requirements

**Merchant Onboarding & Platform Connector**

- R1. A merchant signs up at the hosted URL and is provisioned an isolated tenant with PostgreSQL Row-Level Security (RLS).
- R2. The merchant connects their store via Shopify (Store Domain + Admin API Token) or WooCommerce (Store URL + Consumer Key/Secret). Credentials are stored encrypted and all outbound API calls pass through AgentGuard's SSRF network filter.

**Customer Chat Widget & Identity Verification**

- R3. The merchant receives a lightweight `<script>` tag to embed on their store. When a customer requests order status, returns, or support, the widget requires the customer to provide their **Order Number** and matching **Email Address** before revealing private order data.
- R4. The agent handles the 3 primary post-purchase customer flows:
  - **Where Is My Order (WISMO)**: Returns live fulfillment status, tracking carrier, tracking URL, and estimated delivery dates.
  - **Return & Exchange Remediation**: Checks purchase date against store return policy (e.g., 30-day window). If eligible, calculates refund amount or replacement option.
  - **Damaged / Defective Item Claims**: Collects issue details, logs an escalation ticket, and prepares a refund or replacement request.

**Financial Safety & Human-in-the-Loop (HITL) Governance**

- R5. When a customer is eligible for a refund, the agent cannot directly disburse funds. It creates a **Pending Approval** in the merchant's dashboard detailing: Order ID, customer email, items returned, refund amount, and policy justification.
- R6. The merchant reviews pending requests in their dashboard and clicks **[Approve & Refund]** or **[Reject]**. On approval, AgentGuard calls the store API to execute the refund and notifies the customer in the chat.

**Security, Observability & Multi-Tenancy**

- R7. Every store is isolated via PostgreSQL RLS. Cross-tenant queries are blocked.
- R8. Outbound HTTP requests to merchant APIs and webhooks are strictly validated by `validate_url_ssrf` to block cloud metadata (`169.254.169.254`) and loopback/private subnets.
- R9. Every conversation, tool execution, and refund decision is recorded in the append-only SHA-256 cryptographic audit chain.
- R10. Rate limiting via Redis token buckets prevents malicious flooding or automated scraping of a store's order database.

---

### Key Flows

- F1. Merchant Store Connection
  - **Trigger:** Merchant signs up on the hosted control panel.
  - **Actors:** A1
  - **Steps:** Merchant enters store name and selects platform (Shopify or WooCommerce) → inputs API credentials → AgentGuard verifies connection via safe read probe → merchant sets return policy window (e.g., 30 days) → system outputs embeddable widget snippet.
  - **Covered by:** R1, R2, R3

- F2. Customer Order Tracking (WISMO)
  - **Trigger:** Customer clicks chat widget on the store and asks "Where is my order?"
  - **Actors:** A2, A3
  - **Steps:** Agent prompts for Order Number and Email → Customer submits details → Retriever verifies email matches order billing email → Retriever pulls carrier tracking status → Synthesizer drafts status message → Critic verifies tracking number and delivery date → Customer receives live tracking update.
  - **Covered by:** R3, R4

- F3. Return & Refund Request with HITL Gate
  - **Trigger:** Customer asks to return a delivered item from Order #1042.
  - **Actors:** A1, A2, A3
  - **Steps:** Customer authenticates with Order #1042 + Email → Retriever pulls order date ($85 order, delivered 12 days ago) → Planner validates order is within the 30-day window → Synthesizer informs customer of eligibility and asks reason for return → Agent triggers `issue_high_risk_refund` tool → HITL Gate holds the request and generates a cryptographic single-use token → Card appears in Merchant Approval Inbox → Merchant clicks `[Approve & Refund]` → Refund is dispatched to store API and recorded in the audit log → Customer is notified in chat.
  - **Covered by:** R4, R5, R6, R9

---

### Acceptance Examples

- AE1. Unauthenticated snooping blocked
  - **Covers R3.**
  - **Given:** Order #1055 belongs to `sara@example.com`.
  - **When:** A customer enters Order #1055 with email `hacker@evil.com`.
  - **Then:** The agent responds: *"The email provided does not match our records for Order #1055. Please check the email address used at checkout."* Zero customer or order details are revealed.

- AE2. Return policy boundary enforced
  - **Covers R4.**
  - **Given:** Store policy has a 30-day return window. Order #1010 was delivered 45 days ago.
  - **When:** Customer requests a return for Order #1010.
  - **Then:** Agent checks delivery timestamp, calculates 45 days, and states: *"Under store policy, returns must be initiated within 30 days of delivery. As this order was delivered 45 days ago, it is outside the standard return window."* Offers alternative (e.g., store credit or human review).

- AE3. High-value refund held for merchant approval
  - **Covers R5, R6.**
  - **Given:** Customer requests an $85 refund for a damaged item.
  - **When:** The agent evaluates the request.
  - **Then:** The agent creates a `PENDING` approval item in the merchant dashboard with token and order context. It tells the customer: *"I've submitted your refund request of $85.00 to the store manager for approval. You'll receive a confirmation once reviewed."* The refund is NOT issued until the merchant clicks Approve.

---

### Scope Boundaries

**In scope (v1)**

- Merchant onboarding and store connection (Shopify REST API & WooCommerce REST API connector)
- Embeddable customer chat widget with Order # + Email authentication
- Order status & tracking lookup (WISMO)
- Return remediation & return policy evaluator
- HITL Approval Inbox in merchant dashboard for refund authorization
- Multi-tenant PostgreSQL RLS isolation & SSRF defense
- Gemini-backed multi-agent reasoning (Planner, Retriever, Synthesizer, Critic)
- Tamper-proof SHA-256 audit log of all refund operations

**Deferred for later**

- Automatic generation of printable USPS/UPS return shipping labels
- Proactive SMS / WhatsApp tracking updates
- Complex multi-currency exchange rate conversions

**Outside this product's identity**

- General website FAQ chatbot (this is strictly a transactional support agent)
- Marketing / sales outreach bot (focus is 100% on post-purchase customer resolution)

---

### Dependencies / Assumptions

- Shopify Admin REST / GraphQL API availability with standard order read/write permissions
- WooCommerce REST API v3 availability
- Google Gemini API (gemini-1.5-flash / gemini-2.5-flash) for reasoning and synthesis
- Starlette ASGI server with PostgreSQL RLS and Redis running hosted on Render/Railway

