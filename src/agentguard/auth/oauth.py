"""OAuth 2.1 resource server — validates bearer tokens against JWKS."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import jwt
from jwt import PyJWKClient

from agentguard.config import ServerSettings


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is calling — the result of successful token validation.

    An MCP principal is not a user. It is an *agent* acting with
    delegated authority from a user. The `delegator` attribute
    identifies the human who authorized the agent.
    """

    subject: str                    # Agent identity
    delegator: str | None           # Human who authorized the agent
    tenant: str                     # Multi-tenancy scope
    scopes: frozenset[str]          # Tool-level permissions
    token_id: str                   # jti — for revocation and audit
    issued_at: int
    expires_at: int

    def has_scope(self, required: str) -> bool:
        return required in self.scopes or "tool:*:admin" in self.scopes


class TokenValidator:
    """Validates MCP access tokens against the auth server's JWKS."""

    def __init__(self, settings: ServerSettings):
        self.settings = settings
        self._jwks = PyJWKClient(
            settings.auth_jwks_url, cache_keys=True, max_cached_keys=16
        )

    def validate(self, bearer: str) -> Principal:
        signing_key = self._jwks.get_signing_key_from_jwt(bearer)

        claims = jwt.decode(
            bearer,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=self.settings.auth_audience,
            issuer=self.settings.auth_issuer,
            options={"require": ["exp", "iat", "sub", "jti", "aud", "iss"]},
        )
        scopes = claims.get("scope", "")
        return Principal(
            subject=claims["sub"],
            delegator=claims.get("act", {}).get("sub"),
            tenant=claims.get("tenant", "default"),
            scopes=frozenset(
                scopes.split() if isinstance(scopes, str) else scopes
            ),
            token_id=claims["jti"],
            issued_at=claims["iat"],
            expires_at=claims["exp"],
        )


@lru_cache(maxsize=1)
def get_validator(settings: ServerSettings | None = None) -> TokenValidator:
    if settings is None:
        from agentguard.config import get_settings

        settings = get_settings()
    return TokenValidator(settings)
