"""E-Commerce Store Connectors: Shopify, WooCommerce, and High-Fidelity Simulator.

All external HTTP requests are routed through AgentGuard's SSRF network validation
to ensure zero access to link-local cloud metadata (169.254.169.254) or RFC-1918 subnets.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
import logging
from typing import Any
import httpx

from agentguard.ecommerce.models import (
    OrderDetails,
    OrderFulfillmentStatus,
    OrderItem,
    StoreConfig,
)
from agentguard.errors import NotFoundError, PolicyError, ToolError
from agentguard.governance.http_allowlist import safe_http_get, validate_url_ssrf

logger = logging.getLogger("agentguard.ecommerce.connectors")


class BaseStoreConnector(ABC):
    """Abstract interface defining required store platform capabilities."""

    def __init__(self, config: StoreConfig) -> None:
        self.config = config

    @abstractmethod
    async def fetch_order(self, order_number: str) -> OrderDetails | None:
        """Fetch order details by order number/identifier."""
        pass

    @abstractmethod
    async def issue_refund(
        self,
        order_id: str,
        amount_cents: int,
        reason: str,
    ) -> dict[str, Any]:
        """Disburse refund for an order via the platform's API."""
        pass


class ShopifyConnector(BaseStoreConnector):
    """Production Shopify connector using Admin REST API with SSRF defense."""

    def __init__(self, config: StoreConfig) -> None:
        super().__init__(config)
        # Normalize and validate Shopify domain
        base_url = config.api_url.rstrip("/")
        if not base_url.startswith("https://") and not base_url.startswith("http://"):
            base_url = f"https://{base_url}"
        self.base_url = base_url
        # Validate against SSRF
        validate_url_ssrf(self.base_url)

    async def fetch_order(self, order_number: str) -> OrderDetails | None:
        """Query Shopify orders endpoint filtered by name."""
        clean_num = order_number.strip().lstrip("#")
        query_url = f"{self.base_url}/admin/api/2024-01/orders.json?name={clean_num}&status=any"
        
        # Verify URL passes SSRF filter before calling
        validate_url_ssrf(query_url)

        headers = {
            "X-Shopify-Access-Token": self.config.api_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(query_url, headers=headers)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("Shopify API error fetching order %s: %s", order_number, exc)
            raise ToolError(
                code="SHOPIFY_API_ERROR",
                hint=f"Failed to communicate with Shopify store: {exc}",
            ) from exc

        orders = data.get("orders", [])
        if not orders:
            return None

        raw = orders[0]
        return self._normalize_shopify_order(raw)

    def _normalize_shopify_order(self, raw: dict[str, Any]) -> OrderDetails:
        fulfillments = raw.get("fulfillments", [])
        status = OrderFulfillmentStatus.UNFULFILLED
        tracking_company = None
        tracking_number = None
        tracking_url = None
        delivered_at = None

        if fulfillments:
            latest = fulfillments[-1]
            tracking_company = latest.get("tracking_company")
            tracking_number = latest.get("tracking_number")
            tracking_url = latest.get("tracking_url")
            f_status = latest.get("status", "").lower()
            if f_status == "success":
                status = OrderFulfillmentStatus.DELIVERED
                delivered_at = latest.get("updated_at")
            elif f_status in ("in_transit", "open"):
                status = OrderFulfillmentStatus.IN_TRANSIT
            elif f_status == "out_for_delivery":
                status = OrderFulfillmentStatus.OUT_FOR_DELIVERY

        if raw.get("cancelled_at"):
            status = OrderFulfillmentStatus.CANCELLED
        elif raw.get("financial_status") == "refunded":
            status = OrderFulfillmentStatus.REFUNDED

        items = [
            OrderItem(
                item_id=str(li.get("id")),
                title=li.get("title", "Item"),
                quantity=li.get("quantity", 1),
                price_cents=int(float(li.get("price", "0")) * 100),
                sku=li.get("sku", ""),
            )
            for li in raw.get("line_items", [])
        ]

        total_price = float(raw.get("total_price", "0"))
        return OrderDetails(
            order_id=str(raw["id"]),
            order_number=str(raw.get("name", raw["id"])).lstrip("#"),
            customer_email=(raw.get("email") or raw.get("contact_email") or "").lower(),
            customer_name=f"{raw.get('customer', {}).get('first_name', '')} {raw.get('customer', {}).get('last_name', '')}".strip() or "Valued Customer",
            created_at=raw.get("created_at", ""),
            total_cents=int(total_price * 100),
            currency=raw.get("currency", "USD"),
            fulfillment_status=status,
            items=items,
            delivered_at=delivered_at,
            tracking_company=tracking_company,
            tracking_number=tracking_number,
            tracking_url=tracking_url,
            financial_status=raw.get("financial_status", "paid"),
            store_id=self.config.store_id,
        )

    async def issue_refund(
        self,
        order_id: str,
        amount_cents: int,
        reason: str,
    ) -> dict[str, Any]:
        """Execute refund via Shopify Refunds API."""
        refund_url = f"{self.base_url}/admin/api/2024-01/orders/{order_id}/refunds.json"
        validate_url_ssrf(refund_url)

        headers = {
            "X-Shopify-Access-Token": self.config.api_token,
            "Content-Type": "application/json",
        }
        payload = {
            "refund": {
                "currency": "USD",
                "notify": True,
                "note": reason,
                "transactions": [
                    {
                        "parent_id": int(order_id) if order_id.isdigit() else 0,
                        "amount": f"{amount_cents / 100.0:.2f}",
                        "kind": "refund",
                        "gateway": "shopify_payments",
                    }
                ],
            }
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(refund_url, json=payload, headers=headers)
            if resp.status_code not in (200, 201):
                logger.error("Shopify refund error: %s - %s", resp.status_code, resp.text)
                raise ToolError(
                    code="SHOPIFY_REFUND_FAILED",
                    hint=f"Shopify returned HTTP {resp.status_code}: {resp.text[:200]}",
                )
            return resp.json()


class WooCommerceConnector(BaseStoreConnector):
    """Production WooCommerce connector using REST API v3 with Basic Auth & SSRF defense."""

    def __init__(self, config: StoreConfig) -> None:
        super().__init__(config)
        base_url = config.api_url.rstrip("/")
        if not base_url.startswith("https://") and not base_url.startswith("http://"):
            base_url = f"https://{base_url}"
        self.base_url = base_url
        validate_url_ssrf(self.base_url)

    async def fetch_order(self, order_number: str) -> OrderDetails | None:
        clean_num = order_number.strip().lstrip("#")
        query_url = f"{self.base_url}/wp-json/wc/v3/orders?search={clean_num}"
        validate_url_ssrf(query_url)

        auth = (self.config.api_token, self.config.api_secret)
        try:
            async with httpx.AsyncClient(timeout=8.0, auth=auth) as client:
                resp = await client.get(query_url)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                orders = resp.json()
        except httpx.HTTPError as exc:
            logger.error("WooCommerce API error fetching order %s: %s", order_number, exc)
            raise ToolError(
                code="WOOCOMMERCE_API_ERROR",
                hint=f"Failed to communicate with WooCommerce store: {exc}",
            ) from exc

        if not orders:
            return None

        raw = orders[0]
        return self._normalize_woo_order(raw)

    def _normalize_woo_order(self, raw: dict[str, Any]) -> OrderDetails:
        status_map = {
            "completed": OrderFulfillmentStatus.DELIVERED,
            "processing": OrderFulfillmentStatus.PROCESSING,
            "on-hold": OrderFulfillmentStatus.PROCESSING,
            "cancelled": OrderFulfillmentStatus.CANCELLED,
            "refunded": OrderFulfillmentStatus.REFUNDED,
        }
        raw_status = raw.get("status", "processing").lower()
        fulfillment_status = status_map.get(raw_status, OrderFulfillmentStatus.IN_TRANSIT)

        billing = raw.get("billing", {})
        customer_email = billing.get("email", "").lower()
        customer_name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip() or "Valued Customer"

        items = [
            OrderItem(
                item_id=str(it.get("id")),
                title=it.get("name", "Product"),
                quantity=it.get("quantity", 1),
                price_cents=int(float(it.get("total", "0")) * 100),
                sku=it.get("sku", ""),
            )
            for it in raw.get("line_items", [])
        ]

        total_price = float(raw.get("total", "0"))
        delivered_at = raw.get("date_completed")

        return OrderDetails(
            order_id=str(raw["id"]),
            order_number=str(raw.get("number", raw["id"])).lstrip("#"),
            customer_email=customer_email,
            customer_name=customer_name,
            created_at=raw.get("date_created", ""),
            total_cents=int(total_price * 100),
            currency=raw.get("currency", "USD"),
            fulfillment_status=fulfillment_status,
            items=items,
            delivered_at=delivered_at,
            financial_status="refunded" if raw_status == "refunded" else "paid",
            store_id=self.config.store_id,
        )

    async def issue_refund(
        self,
        order_id: str,
        amount_cents: int,
        reason: str,
    ) -> dict[str, Any]:
        """Issue refund via WooCommerce Orders Refunds API."""
        refund_url = f"{self.base_url}/wp-json/wc/v3/orders/{order_id}/refunds"
        validate_url_ssrf(refund_url)

        auth = (self.config.api_token, self.config.api_secret)
        payload = {
            "amount": f"{amount_cents / 100.0:.2f}",
            "reason": reason,
            "api_refund": True,
        }

        async with httpx.AsyncClient(timeout=10.0, auth=auth) as client:
            resp = await client.post(refund_url, json=payload)
            if resp.status_code not in (200, 201):
                logger.error("WooCommerce refund failed: %s - %s", resp.status_code, resp.text)
                raise ToolError(
                    code="WOOCOMMERCE_REFUND_FAILED",
                    hint=f"WooCommerce returned HTTP {resp.status_code}: {resp.text[:200]}",
                )
            return resp.json()


class SimulatorStoreConnector(BaseStoreConnector):
    """High-fidelity in-memory simulated store for instant offline testing and live recruiter demos."""

    def __init__(self, config: StoreConfig | None = None) -> None:
        cfg = config or StoreConfig(
            store_id="demo-store",
            store_name="Lumina Audio & Tech",
            platform=StorePlatform.SIMULATOR,
            api_url="https://demo.lumina-audio.com",
            return_window_days=30,
        )
        super().__init__(cfg)
        self.reset()

    def reset(self) -> None:
        """Reset in-memory orders to initial state."""
        now = datetime.now(timezone.utc)
        self._orders: dict[str, OrderDetails] = {
            "1001": OrderDetails(
                order_id="ord_1001",
                order_number="1001",
                customer_email="sarah.connor@example.com",
                customer_name="Sarah Connor",
                created_at=(now - timedelta(days=12)).isoformat(),
                total_cents=11400,
                currency="USD",
                fulfillment_status=OrderFulfillmentStatus.DELIVERED,
                items=[
                    OrderItem(item_id="item_1", title="Wireless Noise-Canceling Headphones", quantity=1, price_cents=9900, sku="LUM-NC9"),
                    OrderItem(item_id="item_2", title="Braided Audio Cable 3.5mm", quantity=1, price_cents=1500, sku="LUM-CBL"),
                ],
                delivered_at=(now - timedelta(days=6)).isoformat(),
                tracking_company="USPS",
                tracking_number="9400111899562537624128",
                tracking_url="https://tools.usps.com/go/TrackConfirmAction?tLabels=9400111899562537624128",
                financial_status="paid",
                store_id=self.config.store_id,
            ),
            "1002": OrderDetails(
                order_id="ord_1002",
                order_number="1002",
                customer_email="alex.chen@example.com",
                customer_name="Alex Chen",
                created_at=(now - timedelta(days=2)).isoformat(),
                total_cents=24900,
                currency="USD",
                fulfillment_status=OrderFulfillmentStatus.IN_TRANSIT,
                items=[
                    OrderItem(item_id="item_3", title="Smart Ergonomic Desk Chair", quantity=1, price_cents=24900, sku="LUM-CHR-01"),
                ],
                delivered_at=None,
                tracking_company="UPS",
                tracking_number="1Z9999999999999999",
                tracking_url="https://www.ups.com/track?tracknum=1Z9999999999999999",
                financial_status="paid",
                store_id=self.config.store_id,
            ),
            "1003": OrderDetails(
                order_id="ord_1003",
                order_number="1003",
                customer_email="elena.rostova@example.com",
                customer_name="Elena Rostova",
                created_at=(now - timedelta(days=55)).isoformat(),
                total_cents=13500,
                currency="USD",
                fulfillment_status=OrderFulfillmentStatus.DELIVERED,
                items=[
                    OrderItem(item_id="item_4", title="Mechanical Gaming Keyboard RGB", quantity=1, price_cents=13500, sku="LUM-KB-RGB"),
                ],
                delivered_at=(now - timedelta(days=48)).isoformat(),
                tracking_company="DHL Express",
                tracking_number="4209021093612898",
                tracking_url="https://www.dhl.com/en/express/tracking.html?AWB=4209021093612898",
                financial_status="paid",
                store_id=self.config.store_id,
            ),
            "1004": OrderDetails(
                order_id="ord_1004",
                order_number="1004",
                customer_email="marcus.vance@example.com",
                customer_name="Marcus Vance",
                created_at=(now - timedelta(days=3)).isoformat(),
                total_cents=8900,
                currency="USD",
                fulfillment_status=OrderFulfillmentStatus.OUT_FOR_DELIVERY,
                items=[
                    OrderItem(item_id="item_5", title="Compact Espresso Machine", quantity=1, price_cents=8900, sku="LUM-ESP-01"),
                ],
                delivered_at=None,
                tracking_company="FedEx",
                tracking_number="794829103948",
                tracking_url="https://www.fedex.com/apps/fedextrack/?tracknumbers=794829103948",
                financial_status="paid",
                store_id=self.config.store_id,
            ),
        }

    async def fetch_order(self, order_number: str) -> OrderDetails | None:
        clean = order_number.strip().lstrip("#")
        return self._orders.get(clean)

    async def issue_refund(
        self,
        order_id: str,
        amount_cents: int,
        reason: str,
    ) -> dict[str, Any]:
        # Find order by order_id
        for order in self._orders.values():
            if order.order_id == order_id:
                order.financial_status = "refunded"
                order.fulfillment_status = OrderFulfillmentStatus.REFUNDED
                return {
                    "status": "success",
                    "refund_id": f"ref_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                    "order_id": order_id,
                    "order_number": order.order_number,
                    "amount_cents": amount_cents,
                    "amount_usd": round(amount_cents / 100.0, 2),
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
        raise NotFoundError(
            code="ORDER_NOT_FOUND",
            hint=f"Simulated order '{order_id}' was not found for refund processing.",
        )

