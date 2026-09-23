"""Central configuration for AgentGuard."""

from __future__ import annotations
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTGUARD_",
        env_file=".env",
        extra="ignore",
        frozen=True,
    )

    # Transport
    transport: str = "http"
    http_host: str = "0.0.0.0"
    http_port: int = 8080

    # Auth
    auth_issuer: str = "https://auth.agentguard.local"
    auth_audience: str = "agentguard"
    auth_jwks_url: str = "https://auth.agentguard.local/.well-known/jwks.json"
    auth_secret: str | None = None  # Optional secret for local testing with HS256

    # Database & Multi-Tenancy
    postgres_url: str = "postgresql://agentguard:agentguard@localhost:5432/agentguard"
    require_tenant: bool = True
    tenant_header: str = "X-Tenant-Id"

    # Policy & Authorization (RBAC)
    policy_file: str = "config/policy.yaml"
    enforce_policy: bool = True

    # Rate Limiting (Token Bucket)
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_enabled: bool = True
    rate_limit_capacity: int = 10        # Maximum burst capacity of bucket
    rate_limit_refill_rate: float = 2.0  # Tokens refilled per second (e.g. 2 tokens/sec)

    # Two-Tier Caching (L1 LRU + L2 Redis)
    cache_enabled: bool = True
    cache_l1_capacity: int = 1000
    cache_l1_ttl_seconds: int = 30
    cache_l2_ttl_seconds: int = 300

    # Reliability & Circuit Breaker
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 10.0
    timeout_budget_default_seconds: float = 30.0

    # Observability Stack (Tracing, Metrics, Audit Logging)
    metrics_enabled: bool = True
    tracing_enabled: bool = True
    audit_logging_enabled: bool = True
    audit_log_path: str = "logs/audit.jsonl"

    # Governance: Human-in-the-Loop (HITL) & SSRF Defense
    approval_timeout_seconds: int = 900
    block_private_ips: bool = True
    outbound_domain_allowlist: list[str] = ["*"]


@lru_cache(maxsize=1)
def get_settings() -> ServerSettings:
    """Module-level singleton — read once, cached for application lifetime."""
    return ServerSettings()

