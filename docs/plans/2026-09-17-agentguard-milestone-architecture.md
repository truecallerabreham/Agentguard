---
artifact_contract: ce-unified-plan/v1
product_contract_source: user-specification
execution: code
title: "AgentGuard: Milestone-by-Milestone Implementation & Learning Plan"
date: "2026-09-17"
---

# AgentGuard: Milestone-by-Milestone Implementation & Learning Plan

## Goal Capsule

- **Objective:** Rebuild the production-grade MCP server (`agentguard`) across 15 complete, coherent architectural milestones, transforming each layer into a deep learning vehicle for an intermediate Python learner / AI engineer.
- **Means:** Move away from fragmented micro-step progression (which produced clutter and broken context). Instead, implement and verify one complete milestone at a time. Each milestone delivers an end-to-end working component with zero test script file clutter, accompanied by progressive explanations (One-Sentence Technical -> Real-World Analogy -> Software Mechanics -> Python Concepts -> Terminal Test Commands).
- **Authority Hierarchy:**
  1. User's explicit learning requirements & no-clutter rule (no extra test scripts; user tests manually in terminal).
  2. The 15 Core Milestones from the source tutorial (*From Hello World to Production: Building a Production-Grade MCP Server One Error at a Time*).
  3. Strict production naming: `agentguard` (never `atlas_mcp`).
- **Stop Conditions:** Every milestone halts after implementation, git commit, and explanation, allowing the user to run terminal commands, inspect the output, and confirm readiness before the next milestone begins.

---

## Product Contract

### Target Architecture & Deliverables
AgentGuard is an enterprise Model Context Protocol (MCP) server designed to safely expose internal tools and database systems to autonomous AI agents (Claude Desktop, Cursor, LangChain, custom agents). It addresses the 12 core failure modes of autonomous agents.

### User Persona & Educational Contract
The primary user is an AI Engineer and intermediate Python learner. To optimize for deep conceptual mastery and practical command:
1. **Zero Buzzwords:** Goals are explained plainly in terms of concrete problems and outcomes.
2. **Three-Tier Technical Translation:**
   - *Layer 1: Technical One-Liner* — Concise, precise engineering definition.
   - *Layer 2: Real-World Analogy* — Intuitive real-life model.
   - *Layer 3: Software Mechanics* — Exact data flow, packet exchange, or memory state.
3. **Progressive Concept Unfolding:** Rather than dumping entire specifications at once, concepts are unfolded iteratively (cause -> mechanism -> implementation).
4. **Intermediate Python Deep-Dives:** Explaining Python constructs from first principles (`slots=True`, `frozen=True`, decorators, closures, `@lru_cache`, ASGI middleware call chains, Pydantic type coercion).
5. **Clean Workspace & Manual Terminal Testing:** No test files (`test_step_X.py`) in the repository. All verification is done by the user in their own terminal via direct commands (`python -m agentguard.server`, `curl`, `Invoke-RestMethod`, or inline one-liners).

---

## Planning Contract

### The 15 Milestones Overview

```
Milestone 0: Baseline Stdio MCP Server (FastMCP, tools, local execution)
     │
     ▼
Milestone 1: Remote Streamable HTTP (Starlette, Uvicorn, SSE, unauthenticated network leak)
     │
     ▼
Milestone 2: OAuth 2.1 Authentication (JWT, JWKS, claims, Bearer middleware)
     │
     ▼
Milestone 3: Multi-Tenancy & Database RLS (PostgreSQL pooling, tenant context, RLS)
     │
     ▼
Milestone 4: Policy Engine & RBAC (Declarative YAML, deny-by-default, scope checks)
     │
     ▼
Milestone 5: Input Validation & Dispatch Pipeline (Pydantic schemas, SQL AST SELECT-only)
     │
     ▼
Milestone 6: Distributed Rate Limiting (Redis token bucket, atomic Lua script)
     │
     ▼
Milestone 7: Two-Tier Caching (L1 LRU + L2 Redis, single-flight stampede protection)
     │
     ▼
Milestone 8: Circuit Breaker & Adaptive Timeouts (State machine, backoff, ATBA)
     │
     ▼
Milestone 9: Structured Error Recovery Framework (SERF taxonomy, LLM hints)
     │
     ▼
Milestone 10: Observability Stack (OpenTelemetry tracing, Prometheus /metrics, audit log)
     │
     ▼
Milestone 11: Three-Level Tool Hierarchy (Atomic, Composed, Workflow tools)
     │
     ▼
Milestone 12: Human-in-the-Loop & Exfiltration Defense (Approval gates, SSRF allowlist)
     │
     ▼
Milestone 13: 4-Agent Support Copilot (Planner, Retriever, Synthesizer, Critic)
     │
     ▼
Milestone 14: Docker Packaging & Production Verification (Multi-stage container, full stack)
```

---

## Implementation Units (Work Breakdown)

### Milestone 0: Baseline Stdio MCP Server
- **Goal:** Set up `pyproject.toml` with `mcp` SDK, create package `agentguard`, and run baseline tools (`greet`, `add`, `echo`) over standard input/output (`stdio`).
- **Files:** `pyproject.toml`, `src/agentguard/__init__.py`, `src/agentguard/server.py`.
- **Teaching Focus:**
  - *Analogy:* Walkie-talkie between two people in the same room (stdio between parent and child process).
  - *Python Concepts:* Decorator mechanics (`@mcp.tool()`), type introspection via `typing`, Python package structure with `hatchling`.
- **Manual Terminal Verification:** Interactive tool list and direct execution using Python one-liners.

### Milestone 1: Remote Streamable HTTP & SSE Transport
- **Goal:** Transform the local stdio server into a remote HTTP/SSE web service using Starlette and Uvicorn, and uncover the network vulnerability where anyone on the network can query tools without credentials.
- **Files:** `pyproject.toml` (add `starlette`, `uvicorn`), `src/agentguard/server.py` (add `build_http_app`, `/healthz`, `/sse`, `/messages`).
- **Teaching Focus:**
  - *Analogy:* Upgrading from a private walkie-talkie to a public megaphone in a crowded stadium.
  - *Python Concepts:* Asynchronous programming (`async`/`await`), ASGI application specification, Server-Sent Events (SSE) streaming generators.
- **Manual Terminal Verification:** Launch server in Terminal 1 (`$env:AGENTGUARD_TRANSPORT="http"; python -m agentguard.server`); query `/healthz` and `/sse` in Terminal 2 using `curl`.

### Milestone 2: OAuth 2.1 Authentication & Resource Server
- **Goal:** Secure the HTTP server so all anonymous requests are rejected (401 Unauthorized), accepting only cryptographically signed JWT bearer tokens validated against an identity provider's JWKS.
- **Files:** `src/agentguard/config.py`, `src/agentguard/auth/oauth.py`, `src/agentguard/errors.py`, `src/agentguard/auth/middleware.py`, updated `server.py`.
- **Teaching Focus:**
  - *Analogy:* Airport security checkpoint: the airline ticket (JWT) is stamped with tamper-proof watermarks and identity details, verified against the official airline registry (JWKS).
  - *Python Concepts:* Immutable `@dataclass(frozen=True, slots=True)`, Pydantic settings with `frozen=True` and `@lru_cache`, ASGI middleware request-response interception.
- **Manual Terminal Verification:** Sending unauthenticated `curl` (receives 401), sending forged token (receives 401), sending valid token (receives 200).

### Milestone 3: Multi-Tenancy & Database Row-Level Security (RLS)
- **Goal:** Connect to PostgreSQL and enforce row-level security so Tenant Acme cannot see Tenant Globex's data, enforced at the database transaction layer (`SET LOCAL app.tenant_id = $1`).
- **Files:** `src/agentguard/db/pool.py`, `src/agentguard/governance/tenant.py`, `src/agentguard/tools/atomic/postgres.py`, SQL init script.
- **Teaching Focus:**
  - *Analogy:* An apartment building where every tenant's key only unlocks their own floor's lock, enforced by physical lock tumblers (Postgres RLS engine), not by a sign on the door.
  - *Python Concepts:* Context managers (`async with`), database connection pooling (`asyncpg`), thread-safe context variables (`contextvars.ContextVar`).
- **Manual Terminal Verification:** Run database queries with Tenant A and Tenant B tokens; verify isolation directly via terminal.

### Milestone 4: Policy Engine & Role-Based Access Control (RBAC)
- **Goal:** Implement a declarative YAML policy engine enforcing "deny-by-default" access rules so read-only agents cannot trigger destructive tools.
- **Files:** `src/agentguard/auth/policy.py`, `config/policy.yaml`.
- **Teaching Focus:**
  - *Analogy:* Security access badge: an intern badge opens the library doors but triggers an alarm if tapped on the server vault door.
  - *Python Concepts:* YAML parsing, dictionary lookup sets, boolean evaluation hierarchies, custom policy evaluation methods.
- **Manual Terminal Verification:** Attempting authorized vs unauthorized tool calls; checking 403 Forbidden responses.

### Milestone 5: Strict Input Validation & Tool Dispatch Pipeline
- **Goal:** Intercept every tool invocation in a unified dispatch pipeline, parsing inputs with Pydantic v2 and validating SQL queries with Abstract Syntax Tree (AST) inspection to allow only `SELECT` statements.
- **Files:** `src/agentguard/validation/schemas.py`, `src/agentguard/tools/base.py`, `src/agentguard/server.py`.
- **Teaching Focus:**
  - *Analogy:* Airport baggage X-ray scanner that disassembles items to ensure no hidden contraband before letting baggage pass through.
  - *Python Concepts:* Pydantic field validators, Python AST parsing (`sqlparse` / `ast`), abstract base classes (`abc.ABC`, `@abstractmethod`).
- **Manual Terminal Verification:** Executing clean queries vs injecting `DROP TABLE` or `INSERT`; verifying rejection at the validation layer.

### Milestone 6: Distributed Rate Limiting (Token Bucket)
- **Goal:** Protect downstream infrastructure from runaway recursive agent loops by enforcing per-tenant and per-agent token-bucket quotas backed by Redis Lua scripts.
- **Files:** `src/agentguard/ratelimit/limiter.py`, `src/agentguard/ratelimit/token_bucket.lua`.
- **Teaching Focus:**
  - *Analogy:* An arcade dispenser that only dispenses 5 tokens per minute; once empty, you must wait for refills no matter how fast you push the button.
  - *Python Concepts:* Redis connections, executing atomic server-side Lua scripts, handling fractional time deltas.
- **Manual Terminal Verification:** Firing a burst of 25 rapid requests in terminal; observing allowed requests followed by 429 Too Many Requests.

### Milestone 7: Two-Tier Caching with Stampede Prevention
- **Goal:** Cache frequent identical tool queries using an in-process L1 LRU cache and an L2 Redis distributed cache with single-flight mutex locking (thundering herd defense).
- **Files:** `src/agentguard/cache/lru.py`, `src/agentguard/cache/manager.py`.
- **Teaching Focus:**
  - *Analogy:* Keeping popular books on your desk (L1) and less common ones in the office bookcase (L2), while sending only one person to the library if a book is missing (single-flight mutex).
  - *Python Concepts:* Thread synchronization (`asyncio.Lock`), deterministic SHA256 hashing of arguments, TTL management.
- **Manual Terminal Verification:** Running expensive search query twice; observing second response returning in <1ms from cache.

### Milestone 8: Circuit Breaker, Exponential Backoff & Adaptive Timeouts
- **Goal:** Prevent server cascading failures when external APIs or search engines lag by implementing a 3-state Circuit Breaker (Closed, Open, Half-Open) and Adaptive Timeout Budget Allocation (ATBA).
- **Files:** `src/agentguard/reliability/circuit_breaker.py`, `src/agentguard/reliability/retry.py`, `src/agentguard/reliability/atba.py`.
- **Teaching Focus:**
  - *Analogy:* Household electrical circuit breaker that trips automatically to prevent the house wiring from catching fire during a power surge.
  - *Python Concepts:* State machines, closures and function wrappers, exponential math with randomized jitter.
- **Manual Terminal Verification:** Simulating downstream failure; watching circuit trip to Open state and immediately fast-fail incoming calls.

### Milestone 9: Structured Error Recovery Framework (SERF)
- **Goal:** Replace raw Python stack traces with structured JSON-RPC error envelopes containing machine-readable error codes and recovery hints specifically designed for LLMs.
- **Files:** `src/agentguard/errors/framework.py`, `src/agentguard/errors/handlers.py`.
- **Teaching Focus:**
  - *Analogy:* Instead of an engine exploding and leaving black smoke (raw traceback), the dashboard displays "Check Tire Pressure: Add 5 PSI to front-left tire" (structured hint).
  - *Python Concepts:* Custom exception hierarchies inheriting from `Exception`, `try...except...else...finally` blocks, serialization to JSON-RPC standard error codes.
- **Manual Terminal Verification:** Triggering intentional invalid inputs; observing structured JSON error responses with `retryable` and `hint` fields.

### Milestone 10: Observability Stack (Tracing, Metrics, Audit Logs)
- **Goal:** Integrate OpenTelemetry distributed tracing (W3C trace context), Prometheus `/metrics` endpoint, and tamper-proof JSON audit logging.
- **Files:** `src/agentguard/observability/tracing.py`, `src/agentguard/observability/metrics.py`, `src/agentguard/observability/audit.py`.
- **Teaching Focus:**
  - *Analogy:* An airplane's flight data recorder (black box) recording every cockpit conversation, altitude change, and instrument reading.
  - *Python Concepts:* Context managers, structured logging with `structlog` / `json`, exporting Prometheus gauge/counter metrics.
- **Manual Terminal Verification:** Querying `/metrics` with `curl` and viewing trace IDs printed to console.

### Milestone 11: Three-Level Tool Hierarchy
- **Goal:** Structure tools into Atomic (single database/search operations), Composed (multi-step operations), and Workflow (stateful long-running workflows).
- **Files:** `src/agentguard/tools/atomic/`, `src/agentguard/tools/composed/`, `src/agentguard/tools/workflow/`, `src/agentguard/tools/registry.py`.
- **Teaching Focus:**
  - *Analogy:* Building blocks: individual Lego bricks (Atomic), pre-assembled walls (Composed), and the complete house model (Workflow).
  - *Python Concepts:* Polymorphism, registry design patterns, async generator streams.
- **Manual Terminal Verification:** Listing tools from registry; calling composed workflows in terminal.

### Milestone 12: Human-in-the-Loop (HITL) & SSRF Defense
- **Goal:** Create pending approval gates for high-risk operations (e.g. database drops, external data writes) requiring human confirmation tokens, and enforce outbound HTTP allowlists.
- **Files:** `src/agentguard/governance/approval.py`, `src/agentguard/governance/http_allowlist.py`.
- **Teaching Focus:**
  - *Analogy:* Two-key nuclear missile launch system: the computer proposes the launch, but it cannot fire until an authorized human turns the physical key.
  - *Python Concepts:* Token generation (`secrets.token_urlsafe`), URL parsing and IP address validation with `ipaddress` module.
- **Manual Terminal Verification:** Triggering sensitive action; verifying execution pauses until approval token is submitted.

### Milestone 13: Multi-Agent Support Copilot
- **Goal:** Build an autonomous 4-agent team: Planner (decomposes queries) -> Retriever (fetches evidence via MCP tools) -> Synthesizer (drafts responses) -> Critic (audits for hallucinations).
- **Files:** `src/agentguard/agents/base.py`, `src/agentguard/agents/planner.py`, `src/agentguard/agents/retriever.py`, `src/agentguard/agents/synthesizer.py`, `src/agentguard/agents/critic.py`, `src/agentguard/agents/orchestrator.py`.
- **Teaching Focus:**
  - *Analogy:* A news editorial team: Editor-in-Chief (Planner) assigns the story, Field Reporter (Retriever) gathers facts, Writer (Synthesizer) writes the article, and Fact Checker (Critic) verifies every claim before publication.
  - *Python Concepts:* Agent message state loops, prompt engineering templates, multi-step asynchronous orchestration.
- **Manual Terminal Verification:** Running the multi-agent CLI in terminal and watching the 4 agents collaborate on a complex support inquiry.

### Milestone 14: Containerization & Production Verification
- **Goal:** Package the entire system into a production-grade multi-stage Docker image and compose environment (AgentGuard, Postgres, Redis, Prometheus), and verify all 12 production layers end-to-end.
- **Files:** `Dockerfile`, `docker-compose.yml`, `deploy/`.
- **Teaching Focus:**
  - *Analogy:* Shipping container standard: packing an entire factory cleanly so it can be loaded onto any ship in any port in the world and work identically.
  - *Python Concepts:* Multi-stage builds, non-root user security permissions, health-check probe scripts.
- **Manual Terminal Verification:** Running `docker compose up -d` and curling the healthy containerized stack.

---

## Verification Contract & Quality Gates

1. **No Test Script Clutter:** No temporary test script files will be created in the repository.
2. **Terminal-First Validation:** Every milestone provides exact copy-pasteable PowerShell/Bash commands for the user to execute and inspect.
3. **Commit Integrity:** Every milestone is cleanly committed to Git with a semantic title (`feat(milestone-N): ...`).
4. **Interactive Checkpoint:** We stop at the completion of each milestone to let the user review, test in terminal, and give authorization to move to the next milestone.

---

## Definition of Done

A milestone is marked complete ONLY when:
1. All files belonging to the milestone are written and syntactically clean.
2. The user has copy-pasteable terminal commands to run and test the milestone directly.
3. The explanation follows the 3-tier translation (Technical 1-Liner -> Analogy -> Software Mechanics) + Python concepts from scratch.
4. Git commit is created on `main`.
5. The user reviews, tests in terminal, and authorizes the next milestone.

