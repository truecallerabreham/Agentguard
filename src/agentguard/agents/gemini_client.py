"""Google Gemini client integration for AgentGuard autonomous reasoning.

Uses the official google-genai SDK with automatic fallbacks for offline testing
and environments where GEMINI_API_KEY is not yet provisioned.
"""

from __future__ import annotations
import logging
import os
from typing import Any

logger = logging.getLogger("agentguard.agents.gemini")

_CLIENT: Any | None = None
_CLIENT_INITIALIZED = False


def get_gemini_client() -> Any | None:
    """Return an initialized google.genai.Client instance, or None if key is absent."""
    global _CLIENT, _CLIENT_INITIALIZED
    if _CLIENT_INITIALIZED:
        return _CLIENT

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.info("No GEMINI_API_KEY or GOOGLE_API_KEY detected. Running in deterministic fallback mode.")
        _CLIENT = None
        _CLIENT_INITIALIZED = True
        return None

    try:
        from google import genai
        _CLIENT = genai.Client(api_key=api_key)
        _CLIENT_INITIALIZED = True
        logger.info("Initialized Google Gemini client successfully.")
        return _CLIENT
    except Exception as exc:
        logger.warning("Could not initialize google-genai client: %s. Using deterministic fallback.", exc)
        _CLIENT = None
        _CLIENT_INITIALIZED = True
        return None


async def generate_with_gemini(
    prompt: str,
    system_instruction: str = "You are a helpful, precise, and empathetic customer support AI agent.",
    model: str = "gemini-2.5-flash",
    temperature: float = 0.2,
) -> str | None:
    """Generate response text with Google Gemini, returning None if client is unavailable."""
    client = get_gemini_client()
    if not client:
        return None

    try:
        # The new google-genai SDK generate_content call
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "system_instruction": system_instruction,
                "temperature": temperature,
            },
        )
        if response and response.text:
            return response.text.strip()
    except Exception as exc:
        logger.warning("Gemini generation call failed: %s. Reverting to deterministic response.", exc)

    return None

