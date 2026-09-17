"""Step 1.4 Diagnosis: Why Static API Keys Fail vs Why OAuth 2.1 Resource Server is Required.

This script demonstrates the architectural difference between:
1. Static API keys (fragile, no scopes, no expiry, no tenant isolation)
2. OAuth 2.1 Claims-based Bearer Tokens (tamper-proof, scoped, expiring, multi-tenant)
"""

import time
from typing import Any, Dict


# ==============================================================================
# 1. FLAGGED APPROACH: Naive Static API Key
# ==============================================================================
class NaiveApiKeyAuth:
    """A static shared secret key."""
    def __init__(self, secret_key: str):
        self._secret_key = secret_key

    def verify(self, key_provided: str) -> bool:
        # Fails to answer: Who is calling? What can they do? Has it expired?
        return key_provided == self._secret_key


# ==============================================================================
# 2. PRODUCTION ARCHITECTURE: OAuth 2.1 Principal & Claims Verification
# ==============================================================================
class OAuth2Principal:
    """The verified identity and authorization context extracted from a valid JWT."""
    def __init__(
        self,
        subject: str,
        delegator: str | None,
        tenant: str,
        scopes: set[str],
        expires_at: float,
        token_id: str,
    ):
        self.subject = subject          # e.g., "agent-finance-bot-01"
        self.delegator = delegator      # e.g., "alice@enterprise.com" (human user)
        self.tenant = tenant            # e.g., "tenant-acme-corp"
        self.scopes = frozenset(scopes) # e.g., {"tool:customer:read"}
        self.expires_at = expires_at    # Unix timestamp
        self.token_id = token_id        # Unique JWT ID for audit and instant revocation

    def has_scope(self, required_scope: str) -> bool:
        return required_scope in self.scopes or "tool:*:admin" in self.scopes

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


def run_auth_diagnosis():
    print("==========================================================================")
    print(" STEP 1.4 DIAGNOSIS: STATIC API KEYS VS. OAUTH 2.1 RESOURCE SERVER")
    print("==========================================================================")

    print("\n[SCENARIO 1: Static API Key]")
    static_auth = NaiveApiKeyAuth("super-secret-prod-key-12345")
    key_valid = static_auth.verify("super-secret-prod-key-12345")
    print(f"-> Key validated? {key_valid}")
    print("-> Questions Static Key CANNOT Answer:")
    print("   ? Who is the caller? (Unknown)")
    print("   ? Is the caller an AI agent or human? (Unknown)")
    print("   ? Does the key have permission to delete databases? (Unknown - all or nothing)")
    print("   ? Which tenant's data is the caller allowed to see? (Unknown)")
    print("   ? When does this key expire? (Never - if leaked, it is compromised indefinitely)")
    print("   ? Can we revoke this single compromised caller? (No - rotating breaks ALL callers)")

    print("\n[SCENARIO 2: OAuth 2.1 Principal Context]")
    # Simulated claims payload verified against an Identity Provider (IdP)
    now = time.time()
    principal = OAuth2Principal(
        subject="agent-sales-assistant-99",
        delegator="bob@enterprise.com",
        tenant="tenant-enterprise-dept",
        scopes={"tool:customer:read"},
        expires_at=now + 3600,  # Valid for 1 hour
        token_id="jwt-token-uuid-abc-123"
    )

    print(f"-> Caller Subject:   {principal.subject} (Autonomous Agent)")
    print(f"-> Delegator:        {principal.delegator} (Human who authorized agent)")
    print(f"-> Tenant Scope:     {principal.tenant} (Multi-tenancy isolation)")
    print(f"-> Granted Scopes:   {set(principal.scopes)}")
    print(f"-> Token Expired?    {principal.is_expired()} (Expires in {int(principal.expires_at - now)}s)")
    print(f"-> Can read customers?  {principal.has_scope('tool:customer:read')} [ALLOWED]")
    print(f"-> Can wipe database?   {principal.has_scope('tool:database:drop')} [DENIED]")

    print("\n[ARCHITECTURAL DECISION]:")
    print("AgentGuard will act as an OAuth 2.1 RESOURCE SERVER:")
    print("1. We will NOT store passwords or issue tokens (leave that to Auth0/Keycloak).")
    print("2. We will intercept every HTTP request via ASGI Middleware.")
    print("3. We will validate bearer tokens cryptographically against JWKS.")
    print("4. We will attach the verified Principal to request.state for tools to inspect.")
    print("==========================================================================")


if __name__ == "__main__":
    run_auth_diagnosis()
