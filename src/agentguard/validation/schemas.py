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

    @ field_validator("name")
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


class OrderLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str | None = Field(
        default=None,
        max_length=64,
        description="Lookup orders for customer ID",
    )
    order_id: str | None = Field(
        default=None,
        max_length=64,
        description="Lookup specific order by order ID",
    )

    @field_validator("customer_id", "order_id")
    @classmethod
    def validate_id(cls, v: str | None) -> str | None:
        if v is not None:
            clean = v.strip()
            if not re.match(r"^[A-Za-z0-9_-]+$", clean):
                raise ValueError("Identifier must contain only alphanumeric characters, hyphens, and underscores.")
            return clean
        return None

    def model_post_init(self, __context) -> None:
        if not self.customer_id and not self.order_id:
            raise ValueError("At least one of 'customer_id' or 'order_id' must be specified.")


class KBSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Search term or inquiry keywords",
    )
    category: str | None = Field(
        default=None,
        max_length=50,
        description="Optional category filter (e.g. returns, warranty, billing)",
    )
    store_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional store ID for store-specific custom policy search",
    )


class TicketCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(
        ...,
        max_length=64,
        description="Customer ID for whom the ticket is being created",
    )
    title: str = Field(
        ...,
        min_length=3,
        max_length=150,
        description="Brief subject/title of the support ticket",
    )
    description: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Detailed description of the customer problem or request",
    )
    priority: str = Field(
        default="normal",
        pattern=r"^(low|normal|high|urgent)$",
        description="Priority level: low, normal, high, or urgent",
    )


class Customer360Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(
        ...,
        max_length=64,
        description="Customer ID for the comprehensive 360 overview",
    )


class TroubleshootInquiryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(
        ...,
        max_length=64,
        description="Customer ID experiencing the issue",
    )
    issue_description: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Description of the customer issue to troubleshoot",
    )


class ReturnRemediationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(
        ...,
        max_length=64,
        description="Order ID to remediate or return",
    )
    customer_id: str = Field(
        ...,
        max_length=64,
        description="Customer ID requesting remediation",
    )
    reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Reason for return or replacement request",
    )


class WorkflowStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(
        ...,
        min_length=8,
        max_length=64,
        description="Workflow instance ID to query status for",
    )


class ApproveActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(
        ...,
        min_length=4,
        max_length=64,
        description="Pending approval ID to approve",
    )
    approval_token: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Secret confirmation token provided by human supervisor",
    )


class RejectActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(
        ...,
        min_length=4,
        max_length=64,
        description="Pending approval ID to reject and cancel",
    )
    reason: str = Field(
        default="Rejected by supervisor",
        max_length=500,
        description="Reason for rejecting the action",
    )


class ListApprovalsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional tenant filter",
    )


class FetchUrlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(
        ...,
        min_length=8,
        max_length=2000,
        description="Outbound HTTP or HTTPS URL to fetch safely",
    )


class HighRiskRefundInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(..., max_length=64, description="Target order ID")
    customer_id: str = Field(..., max_length=64, description="Customer ID")
    amount_usd: float = Field(..., gt=0, le=100_000, description="Refund amount in USD")
    reason: str = Field(..., min_length=3, max_length=500, description="Justification for refund")
    approval_id: str | None = Field(default=None, max_length=64, description="Approval ID if previously requested")
    approval_token: str | None = Field(default=None, max_length=128, description="Approval token if previously authorized")



