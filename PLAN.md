# AgentGuard: Production-Grade MCP Architecture Plan

**AgentGuard** is an enterprise-grade Model Context Protocol (MCP) server and multi-agent system built from the ground up to solve the 12 critical production failure modes of autonomous agents.

---

## The 15 Core Milestones

| Milestone | Architecture Layer | Core Objective & What We Build | Real Production Problem Solved |
|---|---|---|---|
| **Milestone 0** | **Baseline MCP Server** | Package structure, `mcp` SDK setup, stdio JSON-RPC transport, and core greeting/math tools. | Establishes the MCP protocol baseline and reveals why stdio fails for distributed network agents. |
| **Milestone 1** | **Remote Streamable HTTP** | Starlette ASGI application, Uvicorn server, `/healthz`, `/sse` streaming, and `/messages` JSON-RPC endpoint. | Enables remote web & network clients, while exposing the dangerous lack of authentication. |
| **Milestone 2** | **OAuth 2.1 Authentication** | Resource Server architecture, Pydantic settings, JWT claims (`sub`, `act.sub`, `tenant`, `scopes`), JWKS key validation, and ASGI Auth Middleware. | Rejects unauthenticated callers; stops anonymous attackers from scraping private data. |
| **Milestone 3** | **Multi-Tenancy & Database RLS** | PostgreSQL connection pooling, tenant context propagation via `request.state`, and database-level Row-Level Security (`SET LOCAL app.tenant_id`). | Eliminates cross-tenant data leakage where Agent A can see Tenant B's data. |
| **Milestone 4** | **Policy Engine & RBAC** | Declarative YAML authorization policies, deny-by-default engine, role-to-tool mappings, and permission enforcement. | Prevents authenticated agents with read-only roles from invoking destructive tools (`DROP TABLE`, delete). |
| **Milestone 5** | **Strict Input Validation & Dispatch Pipeline** | Pydantic v2 runtime schemas, SQL Abstract Syntax Tree (AST) validation (`SELECT`-only parser), and a centralized tool execution pipeline. | Neutralizes SQL injection and malformed parameters before queries ever hit the database. |
| **Milestone 6** | **Distributed Rate Limiting** | Redis-backed token bucket algorithm executing atomic Lua scripts to enforce per-tenant and per-agent request quotas. | Stops runaway agent loops that fire hundreds of recursive requests in seconds, protecting backend capacity. |
| **Milestone 7** | **Two-Tier Caching & Stampede Prevention** | L1 in-process LRU cache + L2 distributed Redis cache with single-flight mutex locks. | Prevents repetitive identical queries from degrading database CPU and eliminates cache stampedes (thundering herd). |
| **Milestone 8** | **Circuit Breakers & Adaptive Timeouts (ATBA)** | State machine (Closed, Open, Half-Open), exponential backoff with full jitter, and Adaptive Timeout Budget Allocation. | Prevents cascading failures when downstream services lag or crash; prevents thread pool starvation. |
| **Milestone 9** | **Structured Error Recovery (SERF)** | Standardized error taxonomy (`ToolError`, `ValidationError`, `PolicyDeniedError`) with machine-readable error codes and recovery hints for LLMs. | Replaces raw Python tracebacks with actionable JSON-RPC error hints so LLMs can recover without hallucinating. |
| **Milestone 10** | **Observability & Audit Logging** | OpenTelemetry distributed tracing (W3C traceparent), Prometheus metrics (`/metrics`), and immutable JSON-structured audit trails. | Provides end-to-end auditability: tracking every agent tool invocation back to the human who authorized it. |
| **Milestone 11** | **Three-Level Tool Hierarchy** | Classification into Atomic tools (database, search), Composed tools (multi-step aggregation), and Workflow tools (stateful long-running jobs). | Prevents agents from building fragile 10-step plans by providing higher-level, robust tool abstractions. |
| **Milestone 12** | **Human-in-the-Loop & SSRF Defense** | Pending approval tokens for high-risk tools (e.g. S3 writes, wire transfers) and outbound HTTP IP/domain allowlists. | Prevents catastrophic unreviewed destructive actions and stops Server-Side Request Forgery (SSRF) data exfiltration. |
| **Milestone 13** | **Multi-Agent Orchestrator Copilot** | Specialized 4-agent system: Planner → Retriever → Synthesizer → Critic, coordinating complex support workflows. | Replaces monolithic prompts with an autonomous team that cross-verifies results before responding. |
| **Milestone 14** | **Containerization & Production Verification** | Production multi-stage Dockerfile, docker-compose orchestration (Postgres, Redis, OTel, MinIO), and complete integration test suite. | Guarantees reproducible, isolated, and scalable deployment across staging and cloud environments. |

---

## New Working Rules (Milestone-Driven)

1. **Build Complete Milestones**: Instead of 103 micro-steps, we execute milestone by milestone. Each milestone delivers a complete, cohesive, working layer of the system.
2. **Terminal-First Manual Testing**: No temporary test scripts cluttering the repository. Every milestone includes exact, copy-pasteable PowerShell/Bash commands so you can run the server and test it with real requests in your own terminal.
3. **Deep Educational Python Explanations**: For every milestone, we explain the architecture and teach the core Python concepts needed (dataclasses, async/await, decorators, middleware, Pydantic, closures, exception hierarchies) in a way tailored to an intermediate Python learner / AI engineer.
4. **Clean Commits**: Every milestone is cleanly committed to Git.

