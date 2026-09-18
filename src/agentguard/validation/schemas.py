"""Pydantic v2 input validation schemas with strict security constraints."""

from __future__ import annotations
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentguard.validation.sql import validate_sql_ast


class GreetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        default="World",
        max_length=100,
        min_length=1,
        description="Name of the person or agent to greet",
    )

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Name cannot be empty or solely whitespace.")
        if "\x00" in clean or any(ord(c) < 32 and c not in "\t\n\r" for c in clean):
            raise ValueError("Name contains forbidden control characters.")
        return clean


class AddInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: int = Field(..., ge=-1_000_000, le=1_000_000, description="First integer operand")
    b: int = Field(..., ge=-1_000_000, le=1_000_000, description="Second integer operand")


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        ...,
        max_length=10_000,
        min_length=1,
        description="Input message to echo back",
    )


class CustomerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(
        ...,
        max_length=64,
        min_length=1,
        description="Unique customer identifier (e.g. CUST-1001)",
    )

    @field_validator("customer_id")
    @classmethod
    def validate_customer_id(cls, v: str) -> str:
        clean = v.strip()
        if not re.match(r"^[A-Za-z0-9_-]+$", clean):
            raise ValueError(
                f"Invalid customer_id format '{clean}'. "
                "Identifiers must contain only alphanumeric characters, underscores, and hyphens."
            )
        return clean


class PostgresQueryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str = Field(
        ...,
        max_length=5000,
        min_length=5,
        description="SQL SELECT query to execute in tenant-isolated session",
    )

    @field_validator("sql")
    @classmethod
    def validate_sql(cls, v: str) -> str:
        return validate_sql_ast(v)

