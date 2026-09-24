"""Production authentication security utilities: salted PBKDF2 password hashing and session tokens."""

from __future__ import annotations
import hashlib
import hmac
import secrets


def generate_salt(length: int = 16) -> str:
    """Generate a cryptographically secure random salt."""
    return secrets.token_hex(length)


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 rounds.
    
    Returns:
        (password_hash, salt)
    """
    if salt is None:
        salt = generate_salt()
    
    # Use PBKDF2-HMAC-SHA256 for robust production password hashing
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,
    )
    return derived.hex(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Verify password against salt and expected hash in constant time."""
    # Check PBKDF2 hash first
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,
    ).hex()
    if hmac.compare_digest(derived, expected_hash):
        return True

    # Fallback check for legacy simple SHA256 hashes (e.g. seeded demo accounts)
    legacy = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, expected_hash)


def generate_session_token() -> str:
    """Generate a cryptographically secure session ID."""
    return f"sess_{secrets.token_urlsafe(32)}"


def generate_api_key(prefix: str = "ag_live_") -> str:
    """Generate a production API key for merchant stores."""
    return f"{prefix}{secrets.token_hex(16)}"
