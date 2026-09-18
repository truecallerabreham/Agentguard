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


@lru_cache(maxsize=1)
def get_settings() -> ServerSettings:
    """Module-level singleton — read once, cached for application lifetime."""
    return ServerSettings()
