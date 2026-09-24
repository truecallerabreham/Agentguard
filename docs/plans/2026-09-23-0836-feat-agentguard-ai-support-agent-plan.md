---
title: AgentGuard Autonomous E-Commerce Support Agent - Technical Implementation Plan
type: feat
date: 2026-09-24
topic: agentguard-ecommerce-support-agent
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-brainstorm
execution: code
---

# AgentGuard Autonomous E-Commerce Support Agent - Technical Implementation Plan

## Goal Capsule

**Objective**: Deliver a 100% production-ready, fully functional SaaS product for e-commerce merchants—eliminating all mock/simulator scaffolding—with persistent database storage, production session authentication, native order & customer management, and an embeddable customer chat widget that resolves real post-purchase inquiries (tracking, return evaluation, damaged claims) with human-in-the-loop financial safety.

**Means**: Replace ephemeral in-memory state with an ACID-compliant persistent SQLite database (WAL mode, disk-persisted, auto-detecting PostgreSQL when `DATABASE_URL` is set). Implement secure password hashing (PBKDF2/SHA-256) and HTTP-only session cookies. Provide full CRUD for store orders, products, and custom policies in the Merchant Dashboard, and wire the embeddable chat widget to query real database records and external Shopify/WooCommerce APIs with strict email verification.

**Product Authority**: Autonomous E-Commerce Support & Operational Governance SaaS. General non-commerce chat and enterprise multi-channel call centers remain out of active scope.

**Open Blockers**: None.

---

## Product Contract

### Summary

AgentGuard is a 100% real, operational **Autonomous E-Commerce Customer Support SaaS Platform & Merchant Control Panel**. Store owners sign up, manage their catalog and customer orders (or connect live Shopify/WooCommerce APIs), ingest store-specific return policies, and embed a lightweight chat widget on any website. When customers reach out, the multi-agent Copilot (Planner, Retriever, Synthesizer, Critic) verifies customer identity via Order # + Email, queries live order data, evaluates policy eligibility, and queues high-risk refunds for 1-click merchant sign-off in the dashboard. All data persists permanently on disk across server restarts.

### Problem Frame

Small e-commerce merchants need a real customer support agent that executes real operational tasks rather than returning static FAQ links. However, existing prototype or demo-oriented systems suffer from:
1. **Ephemeral In-Memory Storage**: Demo bots lose merchant accounts, store settings, customer orders, and approvals whenever the process or hosting container restarts.
2. **Mock Authentication**: Toy systems use hardcoded tokens or fake logins without secure password hashing, persistent merchant records, or HTTP-only session cookies.
3. **Lack of Order Management**: Merchants without paid Shopify API credentials cannot test or run support because there is no built-in order catalog to store customer purchases.
4. **Safety & Financial Risks**: Autonomous AI agents risk promising unauthorized cash refunds or leaking customer private delivery addresses without strict verification guardrails.

### Key Decisions

- **E-Commerce Sector Focus** (session-settled: user-directed — chosen over general FAQ or healthcare/real-estate: e-commerce has immediate transactional pain and directly leverages order lookup, return remediation, and refund tools). Governs R1, R2, R11.
- **Persistent ACID Database by Default** (session-settled: user-directed — chosen over in-memory dictionaries: accounts, orders, policies, and approvals persist permanently to disk via SQLite WAL with PostgreSQL auto-detection). Governs R1, R7, R11.
- **Production Session Authentication** (session-settled: user-directed — chosen over mock logins: secure password hashing, persistent merchant accounts, and HTTP-only cookies). Governs R1, R12.
- **Native Store Catalog & Order Management** (session-settled: user-directed — chosen over external-only connectors: merchants can manage real customer orders directly in the dashboard, alongside Shopify/WooCommerce sync). Governs R2, R13.
- **Privacy Defense via Order # + Email Verification** (session-settled: user-directed — customers must provide both Order Number and matching Billing Email to inspect order details, preventing snooping). Governs R3.
- **Human-in-the-Loop (HITL) Approval for Financial Transactions** (session-settled: user-directed — agent calculates refund eligibility based on store policy but cannot execute payouts without merchant 1-click sign-off). Governs R5, R6.
- **Gemini LLM Backbone with Critic Verification** (session-settled: user-directed — multi-agent team uses Gemini for natural conversation, while Critic verifies that tracking numbers, amounts, and dates exactly match store data before sending). Governs R4.

### Actors

- A1. **Store Merchant (Owner)** — Signs up with real credentials, configures store policies, manages native customer orders or connects Shopify/WooCommerce, embeds the widget on their store, and approves/rejects pending refunds.
- A2. **Store Customer (Shopper)** — Visits the merchant's store, opens the chat widget, authenticates with Order # + Email, and receives real-time tracking, return evaluations, or support.
- A3. **AgentGuard Multi-Agent Engine**:
  - **Planner Agent**: Interprets customer intent (WISMO, return, damaged item claim).
  - **Retriever Agent**: Queries persistent store database or external store APIs for live order status and policy rules.
  - **Synthesizer Agent (Gemini)**: Formulates an empathetic, brand-aligned resolution grounded in store facts.
  - **Critic Agent**: Cross-checks synthesized claims against live database facts to block hallucinations and unauthorized commitments.

---

### Requirements

**Merchant Onboarding, Authentication & Database Persistence**

- R1. A merchant signs up at the hosted URL with email and password. Credentials are securely hashed (PBKDF2/SHA-256), a persistent merchant record and unique store tenant are created in the database, and an authenticated HTTP-only session cookie is issued.
- R11. All application state—merchants, store configs, products, orders, knowledge base articles, approval tickets, and audit entries—persists to disk in an ACID-compliant database (SQLite with WAL mode or PostgreSQL via `DATABASE_URL`). Zero data loss on server restarts.
- R12. Protected merchant endpoints require a valid session cookie or Bearer API token; unauthenticated access redirects to login or returns HTTP 401.

**Platform Connectors & Native Order Management**

- R2. The merchant can connect external stores via Shopify (Domain + Admin API Token) or WooCommerce (URL + Consumer Key/Secret), with SSRF validation on all outbound calls.
- R13. The merchant dashboard provides a native **Orders & Fulfillment Management** interface where merchants can view, create, search, and update customer orders (order ID, customer email, items, price, carrier, tracking number, fulfillment status, and delivery date).

**Customer Chat Widget & Identity Verification**

- R3. The merchant receives a lightweight `<script src=".../widget.js" data-store-id="..."></script>` snippet. When a customer inquires about an order or return, the widget requires the customer to provide their **Order Number** and matching **Email Address** before revealing private order data.
- R4. The agent handles 3 primary transactional flows:
  - **Where Is My Order (WISMO)**: Returns live fulfillment status, carrier name, tracking code, and live tracking URL.
  - **Return & Exchange Remediation**: Evaluates delivery date against store return window. If eligible, calculates refund amount or replacement option.
  - **Damaged / Defective Item Claims**: Gathers issue details, creates an escalation record, and queues appropriate remediation.

**Financial Safety & Human-in-the-Loop (HITL) Governance**

- R5. When a customer is eligible for a refund exceeding the automated threshold ($50.00), the agent cannot disburse funds autonomously. It creates a persistent **Pending Approval** ticket in the database.
- R6. The merchant reviews pending requests in their dashboard and clicks **[Approve & Refund]** or **[Reject]**. On approval, AgentGuard marks the refund settled, records it in the cryptographic audit log, and notifies the customer.

**Security, Observability & Multi-Tenancy**

- R7. Every store is isolated by tenant ID. Cross-tenant data leakage is strictly blocked.
- R8. Outbound HTTP requests to merchant APIs and webhooks are validated by `validate_url_ssrf` to block cloud metadata (`169.254.169.254`) and loopback/private subnets.
- R9. Every conversation, tool execution, and refund decision is recorded in the append-only SHA-256 cryptographic audit chain.
- R10. Rate limiting via token buckets prevents malicious flooding or automated scraping.

---

### Key Flows

- F1. **Merchant Signup, Store Setup & Order Ingestion**
  - **Trigger:** Merchant signs up on public landing page.
  - **Actors:** A1
  - **Steps:** Merchant enters email, password, and store name → Backend hashes password, provisions persistent record in `agentguard.db`, issues HTTP-only session cookie → Merchant is redirected to dashboard → Merchant adds native test orders or connects Shopify/WooCommerce → Merchant defines return window and custom policies.
  - **Covered by:** R1, R2, R11, R12, R13

- F2. **Customer Order Tracking (WISMO)**
  - **Trigger:** Customer visits merchant's store, opens widget, and asks "Where is my order?"
  - **Actors:** A2, A3
  - **Steps:** Agent prompts for Order Number and Email → Customer inputs details → Retriever verifies email matches order billing email in database → Retriever pulls carrier tracking code and status → Synthesizer drafts reply → Critic verifies tracking number → Customer receives accurate tracking information.
  - **Covered by:** R3, R4, R7, R11

- F3. **Return & Refund Request with HITL Gate**
  - **Trigger:** Customer requests a refund for delivered Order #1001.
  - **Actors:** A1, A2, A3
  - **Steps:** Customer authenticates with Order #1001 + Email → Retriever pulls order from database ($249.00, delivered 5 days ago) → Planner validates order is within return window → Synthesizer notes eligibility but explains high-value refund requires manager approval → Agent creates persistent approval record with cryptographic token → Ticket appears in Merchant Approval Inbox → Merchant reviews order details and clicks `[Approve & Refund]` → Refund is marked settled in database and logged to SHA-256 audit chain.
  - **Covered by:** R4, R5, R6, R9, R11

---

### Acceptance Examples

- AE1. **Unauthenticated snooping blocked**
  - **Covers R3, R7.**
  - **Given:** Order #1001 belongs to `alex.chen@example.com`.
  - **When:** A visitor enters Order #1001 with email `intruder@snoop.org`.
  - **Then:** The agent responds: *"The email provided does not match our records for Order #1001. For your security and privacy, order details cannot be displayed."* Zero order details or delivery addresses are exposed.

- AE2. **Return policy boundary enforced**
  - **Covers R4, R11.**
  - **Given:** Store policy has a 30-day return window. Order #1003 was delivered 45 days ago.
  - **When:** Customer requests a return for Order #1003.
  - **Then:** Agent checks delivery timestamp, calculates 45 days, and states: *"Under store policy, returns must be initiated within 30 days of delivery. As this order was delivered 45 days ago, it is outside the standard return window."* Offers alternative or escalation.

- AE3. **High-value refund held for merchant approval across server restart**
  - **Covers R5, R6, R11.**
  - **Given:** Customer requests a $249.00 refund for Order #1001.
  - **When:** The agent evaluates the request, creates approval token `appr-xxxx`, and the server process is restarted.
  - **Then:** The approval ticket remains intact in the persistent database. When the merchant opens the Approval Inbox, the ticket is present, and clicking `[Approve & Refund]` settles the refund and appends to the SHA-256 audit ledger.

---

### Scope Boundaries

**In scope (v1)**
- Persistent SQLite database (WAL mode) with PostgreSQL auto-detection (`DATABASE_URL`).
- Secure merchant authentication: password hashing, session tokens, HTTP-only cookies, `/api/auth/me`, `/api/auth/logout`.
- Native order and customer management (CRUD) in Merchant Dashboard.
- External Shopify REST/GraphQL and WooCommerce REST API v3 connectors with SSRF defense.
- Embeddable customer chat widget (`widget.js`) with Order # + Email authentication.
- Multi-agent Copilot (Planner, Retriever, Synthesizer, Critic) running against persistent database.
- Human-in-the-Loop refund approval queue persisted across server restarts.
- Complete removal of all "demo", "simulator", and prototype labels across the application.

**Deferred for later**
- Automatic generation of printable carrier return shipping labels (USPS/UPS APIs).
- Multi-currency live exchange rate conversions.
- SMS / WhatsApp proactive tracking notifications.

**Outside this product's identity**
- Generic website FAQ chatbot without transactional capabilities.
- Marketing / outreach drip campaigns.

---

### Dependencies / Assumptions

- Python 3.10+ with standard library `sqlite3` and `asyncio`.
- Starlette ASGI server with Uvicorn.
- Optional `asyncpg` for PostgreSQL when deployed with a managed database (`DATABASE_URL`).
- Google Gemini API (`gemini-2.5-flash` / `gemini-1.5-flash`) via `google-genai` SDK or simulated copilot fallback when API key is not supplied.

---

## Planning Contract

### Key Technical Decisions

- **KTD1: SQLite with Write-Ahead Logging (WAL) and Connection Pooling as Default Storage Engine**
  - *(session-settled: user-directed — chosen over in-memory dictionaries: provides zero-configuration, robust ACID persistence on local and cloud container disks like Render/Railway with auto-fallback to PostgreSQL when `DATABASE_URL` is set)*.
  - *Governs R1, R7, R11, R13.*
  - Structure: A centralized database module `agentguard/storage/sqlite_db.py` managing schema migrations, WAL mode for concurrent read/write transactions, and dictionary row factories.

- **KTD2: Secure Session Cookies + Cryptographic Bearer Tokens**
  - *(session-settled: user-directed — chosen over client-side localStorage-only tokens: prevents XSS credential theft, enables seamless page reloads on the dashboard, and maintains secure multi-tenant isolation)*.
  - *Governs R1, R12.*
  - Structure: HTTP-only, `SameSite=Lax`, `Secure` (in production) cookie `agentguard_session` mapped to a persistent `sessions` table, combined with API keys (`ag_live_...`) for widget requests.

- **KTD3: Unified Store Order Repository Pattern**
  - *(session-settled: user-directed — chosen over external-connector-only architecture: guarantees every merchant can manage orders immediately out of the box without requiring external Shopify partner accounts)*.
  - *Governs R2, R4, R13.*
  - Structure: `OrderRepository` abstracts order lookups across native database orders and external Shopify/WooCommerce connectors, providing a single query surface for the AI Copilot.

- **KTD4: Production Realism & Removal of Prototype Scaffolding**
  - *(session-settled: user-directed — chosen over demo/simulator mode: transforms the entire user journey into an authentic e-commerce SaaS product)*.
  - *Governs R3, R4, R5.*
  - Structure: Clean rebranding of `/store` as a customizable merchant storefront preview, removal of all "mock" badges, and direct integration with live merchant catalog and orders.

---

### High-Level Technical Design

```
+----------------------------------------------------------------------------------------------------+
|                                    CLIENT SURFACES (BROWSER)                                       |
|                                                                                                    |
|   +-----------------------+     +-------------------------------+     +------------------------+   |
|   |   Public SaaS Site    |     |    Merchant Control Panel     |     |   Customer Storefront  |   |
|   |     (landing.html)    |     |       (dashboard.html)        |     |    (store_preview)     |   |
|   |                       |     |                               |     |  +------------------+  |   |
|   | - Value proposition   |     | - Orders & Fulfillment (CRUD) |     |  | Floating Widget  |  |   |
|   | - Free signup modal   |     | - Approval Inbox (HITL)       |     |  |   (widget.js)    |  |   |
|   | - Feature showcase    |     | - Knowledge Base & Policies   |     |  +------------------+  |   |
|   |                       |     | - Shopify/Woo Connection Hub  |     |                        |   |
|   +-----------+-----------+     +---------------+---------------+     +-----------+------------+   |
+---------------|---------------------------------|---------------------------------|----------------+
                | POST /api/auth/signup           | Cookie: agentguard_session      | POST /api/chat
                v                                 v                                 v
+----------------------------------------------------------------------------------------------------+
|                                   AGENTGUARD APPLICATION CORE                                      |
|                                                                                                    |
|  [Starlette Middleware Stack: CORS -> Observability -> Auth (Cookie/Bearer) -> Tenant -> Limiter]  |
|                                                                                                    |
|   +------------------------------------+             +-----------------------------------------+   |
|   |        Auth & Session Engine       |             |      Multi-Agent Reasoning Copilot      |   |
|   | - PBKDF2 Password Hashing          |             | - Planner Agent (Intent analysis)       |   |
|   | - Session Cookie Generation        |             | - Retriever (Order/KB query)            |   |
|   | - Principal Extraction             |             | - Synthesizer Agent (Gemini Flash)      |   |
|   +-----------------+------------------+             | - Critic Agent (Ground-truth audit)     |   |
|                     |                                +--------------------+--------------------+   |
|                     v                                                     v                        |
|   +------------------------------------+             +-----------------------------------------+   |
|   |     Unified Order Repository       |<------------+        HITL Approval & Audit Engine     |   |
|   | - Native Database Orders           |             | - Single-Use Cryptographic Tokens       |   |
|   | - Shopify REST/GraphQL Connector   |             | - SHA-256 Hash-Chained Audit Ledger     |   |
|   | - WooCommerce REST v3 Connector    |             +--------------------+--------------------+   |
|   +-----------------+------------------+                                  |                        |
+---------------------|-----------------------------------------------------|------------------------+
                      v                                                     v
+----------------------------------------------------------------------------------------------------+
|                               PERSISTENT DATABASE LAYER (ACID)                                     |
|                                                                                                    |
|    SQLite Database (`data/agentguard.db`) with WAL Mode  (or PostgreSQL via `DATABASE_URL`)       |
|                                                                                                    |
|    - `merchants`          : id, email, password_hash, salt, store_id, api_key                      |
|    - `stores`             : store_id, merchant_id, store_name, platform, api_url, return_window   |
|    - `orders`             : order_id, store_id, customer_email, total, carrier, tracking, items    |
|    - `knowledge_articles` : id, store_id, category, title, content, created_at                    |
|    - `approvals`          : id, store_id, tool_name, parameters, token, status                     |
|    - `sessions`           : session_id, merchant_id, expires_at                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## Implementation Units

### U1. Persistent Database Engine & Schema Migrations
- **Goal**: Implement an ACID-compliant persistent SQLite database (with WAL mode) and automated schema initialization, replacing all in-memory dictionary storage.
- **Requirements**: R1, R7, R11, R13.
- **Dependencies**: None.
- **Files**:
  - `src/agentguard/storage/sqlite_db.py` (create)
  - `src/agentguard/storage/schema.sql` (create)
  - `src/agentguard/config.py` (modify: add `db_path` setting, default `data/agentguard.db`)
  - `tests/test_sqlite_storage.py` (create)
- **Approach**:
  1. Create `schema.sql` with tables: `merchants`, `stores`, `orders`, `products`, `knowledge_articles`, `approvals`, and `sessions`.
  2. Implement `SqliteDatabaseManager` in `sqlite_db.py` with async support (`aiosqlite` or thread-pooled standard library `sqlite3`), enabling WAL mode (`PRAGMA journal_mode=WAL;`), foreign keys, and dictionary cursor factories.
  3. Ensure database directory `data/` is automatically created on startup.
  4. Seed default hardware store catalog and initial orders if database is freshly created.
- **Patterns to follow**: `agentguard/storage/db.py` interface.
- **Test scenarios**:
  - *Happy path*: Initialize database, verify tables created, insert merchant and order, retrieve successfully.
  - *Persistence test*: Write data, close connection, re-open database connection, verify all records persist intact.
  - *WAL concurrency*: Perform multiple concurrent read and write operations without database locked errors.

---

### U2. Production Merchant Authentication & Session Cookie Management
- **Goal**: Implement secure merchant registration, login, logout, and HTTP-only session cookies with password hashing, protecting all dashboard routes.
- **Requirements**: R1, R11, R12.
- **Dependencies**: U1.
- **Files**:
  - `src/agentguard/auth/security.py` (create: password hashing via PBKDF2/SHA-256 and session token generation)
  - `src/agentguard/auth/middleware.py` (modify: extract principal from session cookie or Authorization header)
  - `src/agentguard/ecommerce/service.py` (modify: wire merchant signup, login, session lookup to persistent DB)
  - `src/agentguard/ui/routes.py` (modify: set HTTP-only cookie on login/signup, handle logout, protect `/dashboard`)
  - `tests/test_auth_persistence.py` (create)
- **Approach**:
  1. Implement `hash_password(password, salt)` and `verify_password(password, salt, hash)` using `hashlib.pbkdf2_hmac` with 100,000 iterations.
  2. Implement `create_session(merchant_id)` generating 32-byte URL-safe tokens saved to `sessions` table with 30-day expiration.
  3. In `/api/auth/signup` and `/api/auth/login`, set cookie `agentguard_session=<token>; HttpOnly; SameSite=Lax; Path=/`.
  4. Implement `GET /api/auth/me` returning current merchant profile and store config.
  5. Implement `POST /api/auth/logout` clearing session in DB and clearing cookie.
  6. In `dashboard_endpoint`, redirect to `/?login=1` if no valid session exists.
- **Patterns to follow**: `agentguard/auth/principal.py`.
- **Test scenarios**:
  - *Happy path signup & login*: Register new merchant, verify password hash is salted PBKDF2, verify cookie is returned with HttpOnly flag.
  - *Protected dashboard access*: Request `/dashboard` with valid cookie -> 200 OK; request without cookie -> 302 Redirect to `/`.
  - *Logout*: Call `/api/auth/logout`, verify session is invalidated in DB and cookie is expired.
  - *Wrong password error*: Attempt login with wrong password -> returns 401 with clear error message.

---

### U3. Native Order Management & Unified Order Repository
- **Goal**: Provide full CRUD for customer orders in the persistent database and wire the AI Copilot to query this live repository.
- **Requirements**: R2, R4, R11, R13.
- **Dependencies**: U1, U2.
- **Files**:
  - `src/agentguard/ecommerce/repository.py` (create: `OrderRepository` for persistent order CRUD)
  - `src/agentguard/ecommerce/service.py` (modify: integrate `OrderRepository`)
  - `src/agentguard/ecommerce/models.py` (modify: add order create/update schemas)
  - `src/agentguard/ui/routes.py` (modify: add `/api/orders` GET and POST endpoints)
  - `src/agentguard/copilot/retriever.py` (modify: query unified order repository)
  - `tests/test_order_repository.py` (create)
- **Approach**:
  1. Implement `OrderRepository` with methods: `get_order(order_id, store_id)`, `list_orders(store_id, limit, offset)`, `create_order(order_data)`, `update_order_status(order_id, status, tracking)`.
  2. Add `GET /api/orders` returning paginated orders for the authenticated merchant's store.
  3. Add `POST /api/orders` allowing merchants to create new customer orders with custom order numbers, customer emails, item details, carriers, and tracking numbers.
  4. Ensure `lookup_order` verifies `customer_email.lower().strip() == record.customer_email.lower().strip()`.
- **Patterns to follow**: `agentguard/ecommerce/connectors.py`.
- **Test scenarios**:
  - *Happy path*: Create order `#2001` for `customer@domain.com`, query order via API, verify all fields match.
  - *AI Copilot lookup*: Inquire about order `#2001` via `/api/chat` with matching email -> AI returns live status and tracking.
  - *Email mismatch defense*: Inquire about order `#2001` with wrong email -> AI refuses and blocks order leakage (Covers AE1).

---

### U4. Merchant Dashboard: Real Orders Management & Connection Hub
- **Goal**: Enhance the Merchant Control Panel with a live Orders Management table, order creation modal, persistent approval inbox, and external store connection settings.
- **Requirements**: R1, R2, R5, R6, R12, R13.
- **Dependencies**: U2, U3.
- **Files**:
  - `src/agentguard/ui/dashboard.html` (modify: add Orders tab, order creation modal, real API calls, persistent approval inbox)
  - `src/agentguard/ui/routes.py` (modify: approval decisions update persistent database)
  - `tests/test_dashboard_orders.py` (create)
- **Approach**:
  1. Add an **"Orders & Fulfillment"** tab in `dashboard.html` displaying live customer orders with status badges (`Fulfilled`, `In Transit`, `Delivered`), order totals, tracking numbers, and customer emails.
  2. Add a **"Create Order"** modal allowing merchants to input real customer transactions immediately.
  3. Wire the **"Approval Inbox"** to query `GET /api/approvals` from the persistent database; clicking "Approve" or "Reject" dispatches `POST /api/approvals/decide` and updates the database record.
  4. Wire the **"Knowledge Base"** tab to save articles to the persistent database.
  5. Add user avatar, store switcher, and a real **"Sign Out"** button that calls `/api/auth/logout`.
- **Patterns to follow**: Existing `dashboard.html` styling and IBM Plex Mono typography.
- **Test scenarios**:
  - *Orders UI*: Load dashboard, switch to Orders tab, verify orders list renders from database.
  - *Approval workflow*: Trigger high-risk refund, view in dashboard, click Approve, verify status becomes `SETTLED` in database (Covers AE3).
  - *Sign out*: Click Sign Out, verify session cleared and user redirected to landing page.

---

### U5. Production Customer Storefront Preview & Universal Widget
- **Goal**: Eliminate all "simulator" and "demo-bench" artifacts, converting `/store` into a genuine merchant storefront preview and validating external widget embedding.
- **Requirements**: R3, R4, R11.
- **Dependencies**: U3, U4.
- **Files**:
  - `src/agentguard/ui/store_demo.html` (modify: rebrand as authentic Storefront Preview, display merchant's real store name and products)
  - `src/agentguard/ui/widget.js` (modify: ensure robust origin detection and connection to persistent backend)
  - `src/agentguard/ui/landing.html` (modify: update links, wire auth modal directly to session endpoints)
  - `tests/test_storefront_preview.py` (create)
- **Approach**:
  1. Remove all references to "SIMULATOR", "DEMO BENCH", and fake sample boxes in `store_demo.html`.
  2. Dynamically populate the store header with the merchant's actual `store_name` passed via query param or session.
  3. Ensure `widget.js` functions seamlessly when embedded in external HTML files via `<script src=".../widget.js" data-store-id="..."></script>`.
  4. Ensure `landing.html` signup modal sets the session cookie and redirects directly into the populated merchant dashboard.
- **Patterns to follow**: `src/agentguard/ui/widget.js`.
- **Test scenarios**:
  - *Storefront rendering*: Access `/store?store_id=<custom_store>`, verify store name and live products render cleanly without simulator labels.
  - *Widget chat*: Open chat on storefront, request tracking for native order, verify response is accurate and verified by Critic.
  - *CORS embedding*: Verify widget script loads and executes cross-origin requests with valid CORS headers.

---

### U6. Comprehensive Verification, Security Suite & Cloud Deployment Ready
- **Goal**: Update the entire test suite, security verification script, and documentation for persistent production deployment.
- **Requirements**: R1 through R13.
- **Dependencies**: U1, U2, U3, U4, U5.
- **Files**:
  - `tests/test_saas_onboarding.py` (modify)
  - `tests/test_ecommerce.py` (modify)
  - `tests/test_ui_routes.py` (modify)
  - `src/agentguard/verify_production.py` (modify: verify SQLite persistence and session security)
  - `walkthrough.md` (modify: document real product verification steps)
- **Approach**:
  1. Update all automated tests to test against the persistent database layer.
  2. Add simulated server restart tests to prove data survives process termination.
  3. Verify all 13 production security layers pass 100%.
  4. Update `walkthrough.md` with instructions on how to test persistent accounts, create orders, and deploy to Render.
- **Patterns to follow**: Existing pytest fixtures and `verify_production.py`.
- **Test scenarios**:
  - *Full pytest suite*: Run `python -m pytest tests/ -v`, verify 100% pass rate.
  - *Security verification*: Run `python -m agentguard.verify_production`, verify 13/13 layers pass.

---

## Verification Contract

The implementation is verified when all automated tests pass and the production security layers confirm persistent operations:

```bash
# 1. Run the entire automated test suite
python -m pytest tests/ -v

# 2. Run the 13-layer production security and architecture suite
python -m agentguard.verify_production

# 3. Verify database persistence across process restart
python -c "
from agentguard.storage.sqlite_db import get_sqlite_db
from agentguard.config import get_settings
db = get_sqlite_db(get_settings())
print('Tables in DB:', db.list_tables())
"
```

---

## Definition of Done

1. **Persistent Data**: Zero ephemeral in-memory dictionary loss; merchant accounts, stores, orders, knowledge base articles, and approvals survive complete server process restarts.
2. **Real Authentication**: Secure PBKDF2/SHA-256 password hashing, persistent session tokens, and HTTP-only cookies protecting dashboard routes.
3. **Native Order Management**: Merchants can view, create, search, and fulfill customer orders in the dashboard, and customers can look them up via the chat widget.
4. **Zero Demo Scaffolding**: No "simulator" or "demo-bench" badges on the landing page, storefront, or dashboard.
5. **Security & Privacy**: Email verification strictly blocks unauthorized order snooping, and high-risk refunds trigger single-use cryptographic tokens held in the merchant approval queue.
6. **All Tests Passing**: 100% of automated tests pass without warnings or regressions.
