"""OAuth 2.1 resource server — validates bearer tokens against JWKS."""

from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import jwt
from jwt import PyJWKClient

from agentguard.config import ServerSettings
from agentguard.errors import AuthError


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is calling — the verified result of successful token validation.

    An MCP principal is not a simple user. It is an *agent* acting with
    delegated authority from a user. The `delegator` attribute
    identifies the human who authorized the agent (RFC 8693 actor claim).
    """

    subject: str                    # Agent identity (sub claim)
    delegator: str | None           # Human who authorized the agent (act.sub claim)
    tenant: str                     # Multi-tenancy scope (tenant claim)
    scopes: frozenset[str]          # Tool-level permissions (scope claim)
    token_id: str                   # jti claim — for revocation and audit
    issued_at: int
    expires_at: int

    def has_scope(self, required: str) -> bool:
        return required in self.scopes or "tool:*:admin" in self.scopes


class TokenValidator:
    """Validates MCP access tokens against the auth server's JWKS or local secret."""

    def __init__(self, settings: ServerSettings):
        self.settings = settings
        if not settings.auth_secret and settings.auth_jwks_url:
            self._jwks: PyJWKClient | None = PyJWKClient(
                settings.auth_jwks_url, cache_keys=True, max_cached_keys=16
            )
        else:
            self._jwks = None

    def validate(self, bearer: str) -> Principal:
        try:
            # 1. Local secret mode (HS256) for development and quick testing
            if self.settings.auth_secret:
                signing_key = self.settings.auth_secret
                algorithms = ["HS256"]
            # 2. Production JWKS mode (RS256 / ES256)
            elif self._jwks is not None:
                key_obj = self._jwks.get_signing_key_from_jwt(bearer)
                signing_key = key_obj.key
                algorithms = ["RS256", "ES256"]
            else:
                raise AuthError(
                    code="misconfigured_auth",
                    retryable=False,
                    hint="Neither auth_jwks_url nor auth_secret is configured on the server.",
                )

            claims = jwt.decode(
                bearer,
                signing_key,
                algorithms=algorithms,
                audience=self.settings.auth_audience,
                issuer=self.settings.auth_issuer,
                options={"require": ["exp", "iat", "sub", "jti", "aud", "iss"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError(
                code="token_expired",
                retryable=True,
                hint="Your access token has expired. Obtain a refreshed token from your identity provider.",
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError(
                code="invalid_token",
                retryable=False,
                hint=f"Token verification failed: {exc}",
            ) from exc
        except Exception as exc:
            raise AuthError(
                code="token_verification_failed",
                retryable=False,
                hint=f"Unable to verify token: {exc}",
            ) from exc

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
