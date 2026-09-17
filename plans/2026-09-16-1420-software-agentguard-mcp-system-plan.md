# AgentGuard: Pure Step-by-Step Implementation Plan (Micro-Version Progression)

**Artifact Contract**: `ce-unified-plan/v1`  
**Execution**: `code`  
**Source Document**: `D:\mcp-server-from-scratch-milestone-tutorial_2026-07-19.pdf` (*From Hello World to Production: Building a Production-Grade MCP Server One Error at a Time*)  
**Reference Repository**: `FareedKhan-dev/production-grade-mcp-agentic-system`  
**Target GitHub Repository**: `https://github.com/truecallerabreham/Agentguard.git`  
**Product Name**: `agentguard` (renamed from `atlas_mcp` / `atlas`)  

---

## 1. Goal Capsule & Mandatory Operational Rules

Rebuild the complete production-grade MCP server + multi-agent system from scratch as **AgentGuard**.

> [!IMPORTANT]
> ### 🚨 The Strict Step-by-Step Discipline (Micro-Version Progression)
> - The execution is strictly **step-based** (Step 0.1, Step 0.2, Step 0.3...). Each step is an isolated micro-version.
> - We will **never** skip steps or bundle steps together.
> - At **every single step**, I will:
>   1. Provide an **exhaustive, in-depth technical explanation** of the concept, the protocol mechanics, failure modes, and why the code is designed this way.
>   2. Write/modify the **exact production-grade code** (with `agentguard` naming).
>   3. **Run the command / program** to demonstrate the exact outcome, error, or fix.
>   4. **Commit to Git and push to GitHub** (`https://github.com/truecallerabreham/Agentguard.git`).
>   5. **STOP completely** and hand over to you to inspect the code, run it yourself, and authorize moving to the next step.

---

## 2. Complete Micro-Step Inventory (All 103 Steps)

### Phase 0: The Hello-World MCP Server (Steps 0.1 – 0.8)
- **Step 0.1**: Create empty folder structure and verify environment (`python`, `git`).
- **Step 0.2**: Define project metadata in `pyproject.toml` (package `agentguard`, dependencies `mcp`, `uvicorn`, hatchling build).
- **Step 0.3**: Create package skeleton (`src/agentguard/__init__.py`).
- **Step 0.4**: Write hello-world stdio server in `src/agentguard/server.py` with `@mcp.tool() def greet(name: str)`.
- **Step 0.5**: Install editable package and run the server over stdio.
- **Step 0.6**: Connect from an MCP host/client script to test JSON-RPC communication.
- **Step 0.7**: Trigger and observe the first error: Stdio is bound to a single local process; cannot be shared across networks or horizontally scaled.
- **Step 0.8**: Deep technical diagnosis: JSON-RPC over stdio vs. network transports (Streamable HTTP / SSE).

### Phase 1: Go Remote, Get Hacked (Steps 1.1 – 1.4)
- **Step 1.1**: Add Streamable HTTP transport using Starlette ASGI application and Uvicorn.
- **Step 1.2**: Run the server over HTTP on `0.0.0.0:8080`.
- **Step 1.3**: Observe the error: anyone on the network can call internal tools without credentials.
- **Step 1.4**: Deep technical diagnosis: why production systems require OAuth 2.1 + PKCE authentication.

### Phase 2: Add OAuth 2.1 Authentication (Steps 2.1 – 2.9)
- **Step 2.1**: Add auth dependencies to `pyproject.toml` (`authlib`, `pyjwt[crypto]`, `pydantic-settings`).
- **Step 2.2**: Centralize configuration in `src/agentguard/config.py` using Pydantic Settings with `AGENTGUARD_` env prefix.
- **Step 2.3**: Create OAuth 2.1 authorization module in `src/agentguard/auth/oauth.py` with asymmetric key pairs and JWKS endpoint.
- **Step 2.4**: Create structured `AuthError` in `src/agentguard/errors/framework.py`.
- **Step 2.5**: Write `AuthMiddleware` in `src/agentguard/auth/middleware.py` (Bearer token extraction, signature verification, claims validation).
- **Step 2.6**: Wire `AuthMiddleware` into the Starlette ASGI pipeline.
- **Step 2.7**: Test authenticated HTTP endpoint with valid, expired, and forged JWTs.
- **Step 2.8**: Observe the next error: caller identity is validated, but tenant context is missing.
- **Step 2.9**: Deep technical diagnosis: tenant context propagation and database-level Row-Level Security (RLS).

### Phase 3: Multi-Tenancy & Database Row-Level Security (Steps 3.1 – 3.9)
- **Step 3.1**: Add naive Postgres query tool in `src/agentguard/tools/atomic/postgres.py`.
- **Step 3.2**: Seed two tenants (`acme` and `globex`) in database.
- **Step 3.3**: The error: Tenant `acme`'s query sees records belonging to Tenant `globex` (cross-tenant leak).
- **Step 3.4**: Deep technical diagnosis: why application-level `WHERE tenant_id = ...` clauses fail under autonomous agents.
- **Step 3.5**: Add Row-Level Security (RLS) policies to PostgreSQL schema in `deploy/sql/init.sql`.
- **Step 3.6**: Implement `TenantMiddleware` in `src/agentguard/governance/tenant.py`.
- **Step 3.7**: Fix Postgres tool to execute `SET LOCAL app.tenant_id = $1` on every transaction.
- **Step 3.8**: Test RLS: verify `acme` cannot access `globex` data even if explicitly queried.
- **Step 3.9**: The next error: authenticated callers can still invoke destructive tools (`DROP TABLE`, delete).

### Phase 4: The Policy Engine (Deny by Default) (Steps 4.1 – 4.5)
- **Step 4.1**: Deep technical explanation: YAML declarative policy, RBAC vs. ABAC, and deny-by-default architecture.
- **Step 4.2**: Implement `PolicyEngine` in `src/agentguard/auth/policy.py`.
- **Step 4.3**: Author `config/policy.yaml` with explicit role, tenant, and tool mappings.
- **Step 4.4**: Test policy engine: verify authorized vs. unauthorized tool invocations.
- **Step 4.5**: The next error: agent passes adversarial SQL (`DROP TABLE customers`) into an authorized SQL query tool.

### Phase 5: Input Validation & Dispatch Pipeline (Steps 5.1 – 5.5)
- **Step 5.1**: Build strict Pydantic schemas in `src/agentguard/validation/schemas.py` with SQL AST `SELECT`-only validator.
- **Step 5.2**: Create the three-level `Tool` base class in `src/agentguard/tools/base.py`.
- **Step 5.3**: Build the centralized dispatch pipeline in `src/agentguard/server.py`.
- **Step 5.4**: Test input validation: verify `DROP TABLE` is rejected with a validation error before hitting the database.
- **Step 5.5**: The next error: confused agent enters an infinite loop, firing 100 tool calls in 3 minutes.

### Phase 6: Rate Limiting: Stop the Runaway Agent (Steps 6.1 – 6.7)
- **Step 6.1**: Deep technical explanation: Token bucket algorithm and why atomic Lua scripts in Redis are mandatory.
- **Step 6.2**: Add Redis dependency and connection settings in `config.py`.
- **Step 6.3**: Write the atomic token-bucket Lua script.
- **Step 6.4**: Implement `RateLimiter` in `src/agentguard/ratelimit/limiter.py`.
- **Step 6.5**: Wire rate limiter into the dispatch pipeline.
- **Step 6.6**: Test rate limiting: verify the 21st burst call is rejected with `RateLimitError`.
- **Step 6.7**: The next error: identical search queries execute 100 times, causing database CPU spikes.

### Phase 7: Two-Tier Caching with Stampede Prevention (Steps 7.1 – 7.7)
- **Step 7.1**: Deep technical explanation: Two-tier cache (L1 in-process LRU + L2 distributed Redis) and thundering herd.
- **Step 7.2**: Implement in-process L1 LRU cache.
- **Step 7.3**: Implement `CacheManager` with distributed single-flight mutex lock in `src/agentguard/cache/manager.py`.
- **Step 7.4**: Build deterministic cache key construction from tool metadata and sanitized inputs.
- **Step 7.5**: Wire caching into the dispatch pipeline.
- **Step 7.6**: Test caching: verify the second query returns in sub-millisecond time.
- **Step 7.7**: The next error: downstream service (Elasticsearch) lags and hangs for 30s, exhausting server threads.

### Phase 8: Circuit Breaker, Retry & ATBA (Steps 8.1 – 8.8)
- **Step 8.1**: Deep technical explanation: Circuit breaker state machine (Closed, Open, Half-Open).
- **Step 8.2**: Add reliability errors (`CircuitOpenError`, `TimeoutBudgetExceededError`).
- **Step 8.3**: Implement `CircuitBreaker` and `CircuitBreakerRegistry` in `src/agentguard/reliability/circuit_breaker.py`.
- **Step 8.4**: Implement exponential backoff with full jitter in `src/agentguard/reliability/retry.py`.
- **Step 8.5**: Implement Adaptive Timeout Budget Allocation (ATBA) in `src/agentguard/reliability/atba.py`.
- **Step 8.6**: Wire circuit breaker and ATBA into the dispatch pipeline.
- **Step 8.7**: Test circuit breaker: verify rapid fail-fast when backend is down.
- **Step 8.8**: The next error: agent receives raw Python traceback and hallucinates broken fixes.

### Phase 9: Structured Errors (SERF) (Steps 9.1 – 9.6)
- **Step 9.1**: Deep technical explanation: Structured Error Recovery Framework (SERF) and why LLMs need structured hints.
- **Step 9.2**: Implement full error taxonomy (`ToolError`, `ValidationError`, `PolicyDeniedError`, etc.) in `src/agentguard/errors/framework.py`.
- **Step 9.3**: Convert backend exceptions at the tool boundary.
- **Step 9.4**: Implement wire-format conversion `to_mcp_error()`.
- **Step 9.5**: Test structured errors: verify agent receives actionable error dict (`code`, `retryable`, `hint`).
- **Step 9.6**: The next error: multi-step operations fail with zero traceability into intermediate actions.

### Phase 10: Observability Stack (Steps 10.1 – 10.8)
- **Step 10.1**: Deep technical explanation: The three pillars (Distributed Tracing, Prometheus Metrics, Audit Logs).
- **Step 10.2**: Add OpenTelemetry and Prometheus dependencies.
- **Step 10.3**: Implement OpenTelemetry tracing in `src/agentguard/observability/tracing.py`.
- **Step 10.4**: Implement Prometheus metrics registry in `src/agentguard/observability/metrics.py`.
- **Step 10.5**: Implement immutable structured audit logging in `src/agentguard/observability/audit.py`.
- **Step 10.6**: Wire observability into the dispatch pipeline and expose `/metrics`.
- **Step 10.7**: Bring up observability stack and verify trace context propagation.
- **Step 10.8**: The next error: agent builds brittle 5-step plans out of low-level atomic primitives.

### Phase 11: The Three-Level Tool Hierarchy (Steps 11.1 – 11.6)
- **Step 11.1**: Deep technical explanation: Atomic vs. Composed vs. Workflow tools.
- **Step 11.2**: Implement `ToolRegistry` with discovery filtering in `src/agentguard/tools/registry.py`.
- **Step 11.3**: Build composed tool `semantic_search` in `src/agentguard/tools/composed/semantic_search.py`.
- **Step 11.4**: Build workflow tool `customer.build_context` in `src/agentguard/tools/workflow/customer_context.py`.
- **Step 11.5**: Expose `/.well-known/mcp-server` discovery endpoint.
- **Step 11.6**: The next error: agent attempts to write to S3 with no human review and exfiltrate data via HTTP.

### Phase 12: Governance, Approval Gates & Exfiltration Defense (Steps 12.1 – 12.6)
- **Step 12.1**: Deep technical explanation: Human-in-the-loop (HITL) approval mechanics and SSRF exfiltration risks.
- **Step 12.2**: Implement `PendingApproval` gate in `src/agentguard/governance/approval.py`.
- **Step 12.3**: Test approval gate: verify destructive S3 write pauses for approval token.
- **Step 12.4**: Implement outbound HTTP allowlist in `config/http_allowlist.yaml` and `src/agentguard/tools/atomic/http_client.py`.
- **Step 12.5**: Test HTTP allowlist: verify unauthorized outbound requests are blocked.
- **Step 12.6**: The next error: the server is hardened, but no agentic system orchestrates it.

### Phase 13: The Four-Agent Support Copilot (Steps 13.1 – 13.9)
- **Step 13.1**: Deep technical explanation: Planner → Retriever → Synthesizer → Critic architecture.
- **Step 13.2**: Implement `Agent` base class, token tracking, and LLM interface in `src/agentguard/agents/base.py`.
- **Step 13.3**: Implement `PlannerAgent` in `src/agentguard/agents/planner.py`.
- **Step 13.4**: Implement `RetrieverAgent` with bounded tool-calling loop in `src/agentguard/agents/retriever.py`.
- **Step 13.5**: Implement `SynthesizerAgent` and adversarial `CriticAgent` in `synthesizer.py` & `critic.py`.
- **Step 13.6**: Implement multi-agent `Orchestrator` in `src/agentguard/agents/orchestrator.py`.
- **Step 13.7**: Build interactive CLI in `src/agentguard/agents/cli.py`.
- **Step 13.8**: Run end-to-end support copilot scenario against the AgentGuard MCP server.
- **Step 13.9**: The next error: environment discrepancies between local machine and multi-service deployment.

### Phase 14: Ship It: Docker & Production Verification (Steps 14.1 – 14.6)
- **Step 14.1**: Build production two-stage, non-root `Dockerfile`.
- **Step 14.2**: Author complete `docker-compose.yml` (Postgres, Redis, Elasticsearch, Qdrant, MinIO, OTel, Prometheus, Grafana).
- **Step 14.3**: Spin up complete container stack and verify inter-service health checks.
- **Step 14.4**: Execute automated unit and integration test suite (`tests/`).
- **Step 14.5**: Connect Claude Desktop to AgentGuard over HTTP/stdio.
- **Step 14.6**: Final architectural retrospective and verification of all 12 production components.

---

## 3. Protocol for Each Individual Step

For **each single step**:
1. **Deep Technical Breakdown**: Detailed explanation of the concepts, mechanics, and failure modes.
2. **Code Implementation**: Write exact code for that micro-step with `agentguard` naming.
3. **Execution & Demonstration**: Run the script/command showing the attempt, error, or fix.
4. **Git Commit & Push**: Commit with `feat(step-X.Y): ...` and push to `origin main`.
5. **STOP**: Hand off to you for review and approval before starting the next micro-step.
