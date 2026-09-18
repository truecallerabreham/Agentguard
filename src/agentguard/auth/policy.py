"""Declarative Role-Based Access Control (RBAC) and tool policy engine."""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
import fnmatch
from functools import lru_cache, wraps
import logging
from pathlib import Path
from typing import Any, Callable
import yaml

from agentguard.auth.oauth import Principal, current_principal
from agentguard.config import ServerSettings, get_settings
from agentguard.errors import PolicyError

logger = logging.getLogger("agentguard.policy")


@dataclass
class ToolPolicy:
    name: str
    description: str = ""
    required_scopes: list[str] = field(default_factory=list)


@dataclass
class RolePolicy:
    name: str
    description: str = ""
    scopes: list[str] = field(default_factory=list)


class PolicyEngine:
    """Evaluates declarative authorization policies with deny-by-default semantics."""

    def __init__(
        self,
        policy_path: str | Path | None = None,
        policy_data: dict[str, Any] | None = None,
    ) -> None:
        self.policy_path = Path(policy_path) if policy_path else None
        self.default_action: str = "deny"
        self.tools: dict[str, ToolPolicy] = {}
        self.roles: dict[str, RolePolicy] = {}

        if policy_data is not None:
            self._parse_policy(policy_data)
        elif self.policy_path and self.policy_path.is_file():
            self._load_file(self.policy_path)
        else:
            self._load_fallback_defaults()

    def _load_file(self, path: Path) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._parse_policy(data)
            logger.info("Loaded authorization policy from %s", path)
        except Exception as exc:
            logger.warning("Failed to load policy from %s (%s). Using fallback policy.", path, exc)
            self._load_fallback_defaults()

    def _load_fallback_defaults(self) -> None:
        """In-memory default policy if configuration file is missing."""
        self.default_action = "deny"
        self.tools = {
            "greet": ToolPolicy("greet", "Public greeting", ["tool:greet", "tool:read", "tool:*"]),
            "add": ToolPolicy("add", "Math addition", ["tool:math", "tool:write", "tool:*"]),
            "echo": ToolPolicy("echo", "Echo message", ["tool:echo", "tool:read", "tool:*"]),
            "get_customer": ToolPolicy("get_customer", "Lookup customer", ["tool:customers:read", "tool:read", "tool:*"]),
            "postgres_query": ToolPolicy("postgres_query", "Query database", ["tool:db:query", "tool:*"]),
        }
        self.roles = {
            "guest": RolePolicy("guest", "Guest agent", ["tool:greet"]),
            "reader": RolePolicy("reader", "Read-only agent", ["tool:greet", "tool:echo", "tool:customers:read"]),
            "analyst": RolePolicy("analyst", "Data analyst", ["tool:greet", "tool:echo", "tool:customers:read", "tool:db:query"]),
            "admin": RolePolicy("admin", "Administrator", ["tool:*", "tenant:*:impersonate"]),
        }

    def _parse_policy(self, data: dict[str, Any]) -> None:
        self.default_action = str(data.get("default_action", "deny")).lower()
        self.tools = {}
        for name, tool_info in data.get("tools", {}).items():
            scopes = tool_info.get("required_scopes", [])
            desc = tool_info.get("description", "")
            self.tools[name] = ToolPolicy(name=name, description=desc, required_scopes=scopes)

        self.roles = {}
        for name, role_info in data.get("roles", {}).items():
            scopes = role_info.get("scopes", [])
            desc = role_info.get("description", "")
            self.roles[name] = RolePolicy(name=name, description=desc, scopes=scopes)

    def get_effective_scopes(self, principal: Principal) -> set[str]:
        """Compute the full set of effective scopes by combining token scopes and role expansions."""
        effective: set[str] = set(principal.scopes)

        for role_name in principal.roles:
            if role_name in self.roles:
                effective.update(self.roles[role_name].scopes)

        return effective

    def is_allowed(self, principal: Principal, tool_name: str) -> tuple[bool, str | None]:
        """Check whether a principal is authorized to invoke a tool."""
        # 1. Check if tool is registered
        if tool_name not in self.tools:
            if self.default_action == "deny":
                return False, f"Tool '{tool_name}' is not registered in the policy engine (deny-by-default)."
            return True, None

        tool_policy = self.tools[tool_name]
        if not tool_policy.required_scopes:
            return True, None

        effective_scopes = self.get_effective_scopes(principal)

        # 2. Check for global wildcard access
        if "*" in effective_scopes or "*:*" in effective_scopes or "admin" in effective_scopes:
            return True, None

        # 3. Evaluate required scopes against granted scopes (supporting wildcards)
        for req_scope in tool_policy.required_scopes:
            for granted in effective_scopes:
                if granted == req_scope or fnmatch.fnmatchcase(req_scope, granted):
                    return True, None

        return False, (
            f"Principal '{principal.sub}' lacks required scope for tool '{tool_name}'. "
            f"Required one of: {tool_policy.required_scopes}. "
            f"Effective scopes granted: {sorted(list(effective_scopes))}."
        )

    def enforce(self, principal: Principal, tool_name: str) -> None:
        """Enforce authorization; raises PolicyError if caller lacks required permissions."""
        allowed, reason = self.is_allowed(principal, tool_name)
        if not allowed:
            raise PolicyError(
                code="POLICY_DENIED",
                hint=reason,
                retryable=False,
                context={
                    "tool": tool_name,
                    "principal": principal.sub,
                    "tenant": principal.tenant,
                },
            )


_policy_engine: PolicyEngine | None = None


def get_policy_engine(settings: ServerSettings | None = None) -> PolicyEngine:
    """Return singleton PolicyEngine instance."""
    global _policy_engine
    if _policy_engine is None:
        settings = settings or get_settings()
        _policy_engine = PolicyEngine(policy_path=settings.policy_file)
    return _policy_engine


def enforce_tool_policy(tool_name: str, principal: Principal | None = None) -> None:
    """Validate that the calling principal has permission to invoke tool_name."""
    settings = get_settings()
    if not settings.enforce_policy:
        return

    p = principal or current_principal.get()
    if p is None:
        raise PolicyError(
            code="UNAUTHENTICATED",
            hint=f"Cannot execute tool '{tool_name}' without an authenticated principal.",
            retryable=False,
        )

    engine = get_policy_engine(settings)
    engine.enforce(p, tool_name)


def enforce_policy(tool_name: str | None = None) -> Callable:
    """Decorator to enforce RBAC policy on synchronous or asynchronous tool functions."""

    def decorator(func: Callable) -> Callable:
        name = tool_name or func.__name__

        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                enforce_tool_policy(name)
                return await func(*args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                enforce_tool_policy(name)
                return func(*args, **kwargs)
            return sync_wrapper

    return decorator

