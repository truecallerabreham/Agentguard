"""Data models and schemas for E-Commerce store integration and customer support."""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class StorePlatform(str, Enum):
    """Supported e-commerce platforms."""
    SHOPIFY = "shopify"
    WOOCOMMERCE = "woocommerce"
    SIMULATOR = "simulator"


class OrderFulfillmentStatus(str, Enum):
    """Normalized order fulfillment and delivery states."""
    UNFULFILLED = "unfulfilled"
    PROCESSING = "processing"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


@dataclass
class OrderItem:
    """Individual line item in an order."""
    item_id: str
    title: str
    quantity: int
    price_cents: int
    sku: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrderDetails:
    """Canonical representation of an e-commerce order normalized across platforms."""
    order_id: str
    order_number: str
    customer_email: str
    customer_name: str
    created_at: str
    total_cents: int
    currency: str
    fulfillment_status: OrderFulfillmentStatus
    items: list[OrderItem] = field(default_factory=list)
    delivered_at: str | None = None
    tracking_company: str | None = None
    tracking_number: str | None = None
    tracking_url: str | None = None
    financial_status: str = "paid"
    store_id: str = "default"

    @property
    def total_usd(self) -> float:
        return round(self.total_cents / 100.0, 2)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["fulfillment_status"] = self.fulfillment_status.value
        data["total_usd"] = self.total_usd
        data["items"] = [it.to_dict() for it in self.items]
        return data


@dataclass
class ReturnRemediationDecision:
    """Policy evaluation outcome for a return or refund request."""
    eligible: bool
    status: str  # "ELIGIBLE", "OUTSIDE_RETURN_WINDOW", "ALREADY_REFUNDED", "NOT_DELIVERED"
    reason: str
    days_since_delivery: int | None
    return_window_days: int
    order_number: str
    total_refund_cents: int
    items_to_return: list[dict[str, Any]] = field(default_factory=list)
    requires_human_approval: bool = True

    @property
    def total_refund_usd(self) -> float:
        return round(self.total_refund_cents / 100.0, 2)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_refund_usd"] = self.total_refund_usd
        return data


@dataclass
class StoreConfig:
    """Configuration and credentials for an e-commerce store connection."""
    store_id: str
    store_name: str
    platform: StorePlatform
    api_url: str
    api_token: str = ""
    api_secret: str = ""
    return_window_days: int = 30
    auto_approve_refund_cents: int = 0  # 0 means all refunds require human approval

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["platform"] = self.platform.value
        # Mask credentials in representations
        data["api_token"] = "***" if self.api_token else ""
        data["api_secret"] = "***" if self.api_secret else ""
        return data
