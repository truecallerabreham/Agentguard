"""Base tool abstraction and centralized dispatch pipeline."""

from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
from functools import wraps
from typing import Any, Callable, Type
from pydantic import BaseModel, ValidationError as PydanticValidationError

from agentguard.auth.policy import enforce_tool_policy
from agentguard.errors import ValidationError


class BaseTool(ABC):
    """Abstract base class for all AgentGuard tools."""

    name: str
    description: str
    input_schema: Type[BaseModel]

    @abstractmethod
    async def run(self, **kwargs: Any) -> Any:
        """Execute the tool's core logic with validated parameters."""
        pass

    async def execute(self, arguments: dict[str, Any] | BaseModel) -> Any:
        """Centralized execution pipeline: Policy enforcement -> Schema validation -> Execution."""
        # 1. RBAC Policy Check
        enforce_tool_policy(self.name)

        # 2. Strict Input Validation via Pydantic
        if isinstance(arguments, BaseModel):
            validated_model = arguments
        else:
            try:
                validated_model = self.input_schema.model_validate(arguments or {})
            except PydanticValidationError as exc:
                error_hints = []
                for err in exc.errors():
                    field_path = ".".join(str(loc) for loc in err.get("loc", [])) or "input"
                    msg = err.get("msg", "invalid value")
                    error_hints.append(f"{field_path}: {msg}")

                raise ValidationError(
                    code="INVALID_ARGUMENTS",
                    hint="; ".join(error_hints),
                    retryable=False,
                    context={"validation_errors": exc.errors()},
                ) from exc

        # 3. Execution
        kwargs = validated_model.model_dump()
        return await self.run(**kwargs)


class ToolDispatcher:
    """Registry and dispatcher for BaseTool instances."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Get a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        """Return descriptions and JSON schemas for all registered tools."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema.model_json_schema(),
            }
            for tool in self._tools.values()
        ]

    async def dispatch(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Dispatch an invocation request through the unified security pipeline."""
        tool = self.get(tool_name)
        if not tool:
            raise ValidationError(
                code="TOOL_NOT_FOUND",
                hint=f"Tool '{tool_name}' is not registered in the system.",
                retryable=False,
            )
        return await tool.execute(arguments or {})


_global_dispatcher: ToolDispatcher | None = None


def get_dispatcher() -> ToolDispatcher:
    """Singleton getter for the global ToolDispatcher."""
    global _global_dispatcher
    if _global_dispatcher is None:
        _global_dispatcher = ToolDispatcher()
    return _global_dispatcher


def validate_input(schema_cls: Type[BaseModel]) -> Callable:
    """Decorator to apply Pydantic validation to a standalone tool function."""

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                # If arguments were passed as kwargs or first arg
                params = kwargs
                if args and not kwargs:
                    # If single dict arg passed
                    if len(args) == 1 and isinstance(args[0], dict):
                        params = args[0]
                try:
                    validated = schema_cls.model_validate(params)
                except PydanticValidationError as exc:
                    hints = [
                        f"{'.'.join(str(loc) for loc in err.get('loc', [])) or 'input'}: {err.get('msg')}"
                        for err in exc.errors()
                    ]
                    raise ValidationError(
                        code="INVALID_ARGUMENTS",
                        hint="; ".join(hints),
                        retryable=False,
                        context={"errors": exc.errors()},
                    ) from exc
                return await func(**validated.model_dump())
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                params = kwargs
                if args and not kwargs:
                    if len(args) == 1 and isinstance(args[0], dict):
                        params = args[0]
                try:
                    validated = schema_cls.model_validate(params)
                except PydanticValidationError as exc:
                    hints = [
                        f"{'.'.join(str(loc) for loc in err.get('loc', [])) or 'input'}: {err.get('msg')}"
                        for err in exc.errors()
                    ]
                    raise ValidationError(
                        code="INVALID_ARGUMENTS",
                        hint="; ".join(hints),
                        retryable=False,
                        context={"errors": exc.errors()},
                    ) from exc
                return func(**validated.model_dump())
            return sync_wrapper

    return decorator

