"""E-Commerce Support Service coordinating verified lookups, return policies, and HITL refund gates."""

from __future__ import annotations
from datetime import datetime, timezone
import logging
from typing import Any

from agentguard.ecommerce.connectors import (
    BaseStoreConnector,
    ShopifyConnector,
    SimulatorStoreConnector,
    WooCommerceConnector,
)
from agentguard.ecommerce.models import (
    OrderDetails,
    OrderFulfillmentStatus,
    ReturnRemediationDecision,
    StoreConfig,
    StorePlatform,
)
from agentguard.errors import NotFoundError, PolicyError, ValidationError
from agentguard.governance.approval import get_approval_manager
from agentguard.observability.audit import get_audit_logger

logger = logging.getLogger("agentguard.ecommerce.service")


class EcommerceService:
    """Enterprise coordination layer governing store connectors, identity verification, and refund gates."""

    def __init__(self) -> None:
        self._stores: dict[str, StoreConfig] = {}
        self._connectors: dict[str, BaseStoreConnector] = {}
        # Pre-register default demo store
        self.register_store(
            StoreConfig(
                store_id="demo-store",
                store_name="Lumina Audio & Tech",
                platform=StorePlatform.SIMULATOR,
                api_url="https://demo.lumina-audio.com",
                return_window_days=30,
            )
        )

    def register_store(self, config: StoreConfig) -> None:
        """Register a store configuration and instantiate its connector."""
        self._stores[config.store_id] = config
        if config.platform == StorePlatform.SHOPIFY:
            self._connectors[config.store_id] = ShopifyConnector(config)
        elif config.platform == StorePlatform.WOOCOMMERCE:
            self._connectors[config.store_id] = WooCommerceConnector(config)
        else:
            self._connectors[config.store_id] = SimulatorStoreConnector(config)
        logger.info("Registered %s store '%s' (ID: %s)", config.platform.value, config.store_name, config.store_id)

    def get_connector(self, store_id: str) -> BaseStoreConnector:
        """Retrieve connector for a store ID, falling back to simulator if unknown."""
        connector = self._connectors.get(store_id)
        if not connector:
            logger.warning("Store ID '%s' not registered. Falling back to Simulator connector.", store_id)
            return self._connectors["demo-store"]
        return connector

    def get_store_config(self, store_id: str) -> StoreConfig:
        return self._stores.get(store_id, self._stores["demo-store"])

    def reset(self) -> None:
        """Reset all in-memory store states."""
        for conn in self._connectors.values():
            if hasattr(conn, "reset"):
                conn.reset()

    async def lookup_verified_order(
        self,
        store_id: str,
        order_number: str,
        customer_email: str,
    ) -> OrderDetails:
        """Fetch order details with strict customer email authentication to prevent snooping."""
        clean_num = order_number.strip().lstrip("#")
        clean_email = customer_email.strip().lower()

        if not clean_email:
            raise ValidationError(
                code="EMAIL_REQUIRED",
                hint="Customer billing email is required to verify order ownership.",
            )

        connector = self.get_connector(store_id)
        order = await connector.fetch_order(clean_num)

        if not order:
            raise NotFoundError(
                code="ORDER_NOT_FOUND",
                hint=f"Order #{clean_num} was not found in store records. Please check the order number.",
                context={"order_number": clean_num},
            )

        # Enforce email privacy boundary: matching email required to inspect order
        if order.customer_email.strip().lower() != clean_email:
            logger.warning(
                "Order snooping attempt detected: order_number=%s, provided_email=%s, actual_email=%s",
                clean_num,
                clean_email,
                order.customer_email,
            )
            # Log security event in audit trail
            audit = get_audit_logger()
            audit.log_action(
                action="ecommerce:order_lookup_denied",
                parameters={"order_number": clean_num, "provided_email": clean_email},
                status="DENIED",
                error={"reason": "EMAIL_MISMATCH"},
            )
            raise ValidationError(
                code="EMAIL_VERIFICATION_FAILED",
                hint="The email address provided does not match our records for this order. Please use the email provided at checkout.",
                context={"order_number": clean_num},
            )

        # Audit successful lookup
        audit = get_audit_logger()
        audit.log_action(
            action="ecommerce:order_lookup_success",
            parameters={"order_number": clean_num, "customer_email": clean_email},
            status="SUCCESS",
        )
        return order

    async def evaluate_return(
        self,
        store_id: str,
        order_number: str,
        customer_email: str,
        reason: str = "",
    ) -> ReturnRemediationDecision:
        """Evaluate order return eligibility against the store's policy window."""
        order = await self.lookup_verified_order(store_id, order_number, customer_email)
        cfg = self.get_store_config(store_id)
        now = datetime.now(timezone.utc)

        # 1. Check if order is delivered
        if order.fulfillment_status != OrderFulfillmentStatus.DELIVERED:
            return ReturnRemediationDecision(
                eligible=False,
                status="NOT_DELIVERED",
                reason=(
                    f"Order #{order_number} is currently {order.fulfillment_status.value.upper()}. "
                    "Items can only be returned after they have been successfully delivered."
                ),
                days_since_delivery=None,
                return_window_days=cfg.return_window_days,
                order_number=order_number,
                total_refund_cents=0,
                requires_human_approval=False,
            )

        # 2. Check if already refunded
        if order.financial_status == "refunded":
            return ReturnRemediationDecision(
                eligible=False,
                status="ALREADY_REFUNDED",
                reason=f"Order #{order_number} has already been fully refunded.",
                days_since_delivery=None,
                return_window_days=cfg.return_window_days,
                order_number=order_number,
                total_refund_cents=0,
                requires_human_approval=False,
            )

        # 3. Check delivery date against return window
        days_since_delivery = 0
        if order.delivered_at:
            try:
                # Handle ISO timestamps with or without timezone
                delivery_dt = datetime.fromisoformat(order.delivered_at)
                if delivery_dt.tzinfo is None:
                    delivery_dt = delivery_dt.replace(tzinfo=timezone.utc)
                delta = now - delivery_dt
                days_since_delivery = max(0, delta.days)
            except Exception as exc:
                logger.warning("Could not parse delivered_at timestamp '%s': %s", order.delivered_at, exc)
                days_since_delivery = 5  # default safe fallback

        if days_since_delivery > cfg.return_window_days:
            return ReturnRemediationDecision(
                eligible=False,
                status="OUTSIDE_RETURN_WINDOW",
                reason=(
                    f"Order #{order_number} was delivered {days_since_delivery} days ago, "
                    f"which exceeds our {cfg.return_window_days}-day return policy window."
                ),
                days_since_delivery=days_since_delivery,
                return_window_days=cfg.return_window_days,
                order_number=order_number,
                total_refund_cents=0,
                requires_human_approval=False,
            )

        return ReturnRemediationDecision(
            eligible=True,
            status="ELIGIBLE",
            reason=(
                f"Order #{order_number} was delivered {days_since_delivery} day(s) ago and is fully eligible "
                f"for a return under our {cfg.return_window_days}-day policy."
            ),
            days_since_delivery=days_since_delivery,
            return_window_days=cfg.return_window_days,
            order_number=order_number,
            total_refund_cents=order.total_cents,
            items_to_return=[it.to_dict() for it in order.items],
            requires_human_approval=True,
        )

    async def execute_approved_refund(
        self,
        store_id: str,
        order_number: str,
        approval_id: str,
        approval_token: str,
        amount_cents: int,
        reason: str,
    ) -> dict[str, Any]:
        """Execute store refund after verifying cryptographic single-use token from HITL gate."""
        manager = get_approval_manager()

        # Enforce single-use token consumption (prevents replay attacks)
        if not manager.verify_and_consume(approval_id, approval_token):
            raise PolicyError(
                code="APPROVAL_TOKEN_INVALID",
                hint=f"Approval request '{approval_id}' has already been consumed, expired, or is invalid.",
            )

        connector = self.get_connector(store_id)
        # Find order_id
        order = await connector.fetch_order(order_number)
        if not order:
            raise NotFoundError(code="ORDER_NOT_FOUND", hint=f"Order #{order_number} not found.")

        result = await connector.issue_refund(
            order_id=order.order_id,
            amount_cents=amount_cents,
            reason=reason,
        )

        # Cryptographically log refund execution
        audit = get_audit_logger()
        audit.log_action(
            action="ecommerce:refund_settled",
            parameters={
                "order_number": order_number,
                "amount_cents": amount_cents,
                "approval_id": approval_id,
                "reason": reason,
            },
            status="SETTLED",
        )
        return result


_GLOBAL_ECOMMERCE_SERVICE: EcommerceService | None = None


def get_ecommerce_service() -> EcommerceService:
    """Singleton getter for the global EcommerceService."""
    global _GLOBAL_ECOMMERCE_SERVICE
    if _GLOBAL_ECOMMERCE_SERVICE is None:
        _GLOBAL_ECOMMERCE_SERVICE = EcommerceService()
    return _GLOBAL_ECOMMERCE_SERVICE

