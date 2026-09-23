"""E-Commerce Support Service coordinating verified lookups, return policies, and HITL refund gates."""

from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import logging
import re
import secrets
from typing import Any

from agentguard.ecommerce.connectors import (
    BaseStoreConnector,
    ShopifyConnector,
    SimulatorStoreConnector,
    WooCommerceConnector,
)
from agentguard.ecommerce.models import (
    CustomKnowledgeArticle,
    MerchantAccount,
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
        self._merchants: dict[str, MerchantAccount] = {}
        self._merchants_by_token: dict[str, MerchantAccount] = {}
        self._merchants_by_store: dict[str, MerchantAccount] = {}
        self._kb_articles: dict[str, list[CustomKnowledgeArticle]] = {}
        self._init_default_data()

    def _init_default_data(self) -> None:
        """Seed default demo store, merchant account, and knowledge articles."""
        self._stores.clear()
        self._connectors.clear()
        self._merchants.clear()
        self._merchants_by_token.clear()
        self._merchants_by_store.clear()
        self._kb_articles.clear()

        # 1. Pre-register default demo store
        demo_cfg = StoreConfig(
            store_id="demo-store",
            store_name="Lumina Audio & Tech",
            platform=StorePlatform.SIMULATOR,
            api_url="https://demo.lumina-audio.com",
            return_window_days=30,
        )
        self.register_store(demo_cfg)

        # 2. Pre-register default demo merchant account
        demo_merchant = MerchantAccount(
            merchant_id="merch_demo",
            email="demo@lumina-audio.com",
            password_hash=self._hash_password("demo123"),
            store_name="Lumina Audio & Tech",
            store_id="demo-store",
            api_key="ag_live_demo_token",
            platform="simulator",
        )
        self._merchants[demo_merchant.merchant_id] = demo_merchant
        self._merchants_by_token[demo_merchant.api_key] = demo_merchant
        self._merchants_by_store[demo_merchant.store_id] = demo_merchant

        # 3. Pre-seed default demo store policies
        self.add_kb_article(
            store_id="demo-store",
            category="returns",
            title="Lumina Audio 30-Day Return & Replacement Policy",
            content="Customers may return any product within 30 days of delivery for a full refund or exchange. Items must be in original condition with all accessories.",
        )
        self.add_kb_article(
            store_id="demo-store",
            category="warranty",
            title="Lumina Audio 1-Year Comprehensive Hardware Warranty",
            content="All headphones and audio hardware come with a 1-year limited warranty covering manufacturing defects, audio driver failure, and loose wiring.",
        )
        self.add_kb_article(
            store_id="demo-store",
            category="shipping",
            title="Shipping Rates & Delivery Timeframes",
            content="Standard shipping takes 3-5 business days via USPS or UPS. Priority express shipping delivers in 1-2 business days with real-time tracking.",
        )

    def _hash_password(self, password: str, salt: str = "agentguard_salt_2026") -> str:
        return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()

    def register_merchant(
        self,
        email: str,
        password: str,
        store_name: str,
        platform: str = "simulator",
        api_url: str = "",
        api_token: str = "",
        api_secret: str = "",
        return_window_days: int = 30,
    ) -> MerchantAccount:
        """Register a new e-commerce merchant and provision an isolated tenant environment."""
        email_clean = email.strip().lower()
        if not email_clean or "@" not in email_clean:
            raise ValidationError(code="INVALID_EMAIL", hint="A valid email address is required.")
        if not password or len(password) < 6:
            raise ValidationError(code="WEAK_PASSWORD", hint="Password must be at least 6 characters.")
        if not store_name.strip():
            raise ValidationError(code="INVALID_STORE_NAME", hint="Store name is required.")

        # Check if email is already registered
        for m in self._merchants.values():
            if m.email == email_clean:
                raise ValidationError(code="EMAIL_EXISTS", hint="A merchant with this email address already exists.")

        # Generate unique store_id slug and credentials
        slug = re.sub(r"[^a-z0-9]+", "-", store_name.lower()).strip("-")[:16] or "store"
        rand_suffix = secrets.token_hex(3)
        store_id = f"store_{slug}_{rand_suffix}"
        merchant_id = f"merch_{secrets.token_hex(4)}"
        api_key = f"ag_live_{secrets.token_urlsafe(24)}"

        plat = (
            StorePlatform(platform.lower())
            if platform.lower() in ("shopify", "woocommerce", "simulator")
            else StorePlatform.SIMULATOR
        )

        # Provision store configuration and connector
        cfg = StoreConfig(
            store_id=store_id,
            store_name=store_name.strip(),
            platform=plat,
            api_url=api_url.strip() or "https://demo.lumina-audio.com",
            api_token=api_token.strip(),
            api_secret=api_secret.strip(),
            return_window_days=int(return_window_days),
        )
        self.register_store(cfg)

        merchant = MerchantAccount(
            merchant_id=merchant_id,
            email=email_clean,
            password_hash=self._hash_password(password),
            store_name=store_name.strip(),
            store_id=store_id,
            api_key=api_key,
            platform=plat.value,
        )
        self._merchants[merchant_id] = merchant
        self._merchants_by_token[api_key] = merchant
        self._merchants_by_store[store_id] = merchant

        # Pre-seed initial custom policies for this store
        self.add_kb_article(
            store_id=store_id,
            category="returns",
            title=f"{store_name} Return Policy",
            content=f"Customers may request returns within {return_window_days} days of delivery. Orders in original packaging qualify for return and refund after merchant authorization.",
        )
        self.add_kb_article(
            store_id=store_id,
            category="shipping",
            title=f"{store_name} Shipping Policy",
            content="Standard delivery takes 3-5 business days. Real-time carrier tracking links are provided upon dispatch.",
        )

        logger.info("Successfully provisioned new merchant account %s (%s) for store %s", merchant_id, email_clean, store_id)
        return merchant

    def authenticate_merchant(self, email: str, password: str) -> MerchantAccount | None:
        """Authenticate merchant by email and password."""
        email_clean = email.strip().lower()
        pwd_hash = self._hash_password(password)
        for m in self._merchants.values():
            if m.email == email_clean and m.password_hash == pwd_hash:
                return m
        return None

    def get_merchant_by_api_key(self, api_key: str) -> MerchantAccount | None:
        return self._merchants_by_token.get(api_key)

    def get_merchant_by_store_id(self, store_id: str) -> MerchantAccount | None:
        return self._merchants_by_store.get(store_id)

    def add_kb_article(
        self,
        store_id: str,
        category: str,
        title: str,
        content: str,
    ) -> CustomKnowledgeArticle:
        """Add a custom policy or FAQ article to a store's private knowledge base."""
        if not title.strip() or not content.strip():
            raise ValidationError(code="INVALID_KB_ARTICLE", hint="Article title and content are required.")

        article_id = f"art_{secrets.token_hex(4)}"
        article = CustomKnowledgeArticle(
            article_id=article_id,
            store_id=store_id,
            category=category.strip().lower() or "general",
            title=title.strip(),
            content=content.strip(),
        )
        if store_id not in self._kb_articles:
            self._kb_articles[store_id] = []
        self._kb_articles[store_id].append(article)
        logger.info("Added custom KB article '%s' for store '%s'", title, store_id)
        return article

    def list_kb_articles(self, store_id: str) -> list[CustomKnowledgeArticle]:
        """List all custom policies and FAQs for a store."""
        return list(self._kb_articles.get(store_id, []))

    def delete_kb_article(self, store_id: str, article_id: str) -> bool:
        """Delete an article from a store's knowledge base."""
        articles = self._kb_articles.get(store_id, [])
        for i, a in enumerate(articles):
            if a.article_id == article_id:
                articles.pop(i)
                logger.info("Deleted KB article '%s' from store '%s'", article_id, store_id)
                return True
        return False

    def search_store_kb(
        self,
        store_id: str,
        query: str,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search store's private knowledge base for keyword matches."""
        articles = self.list_kb_articles(store_id)
        keywords = set(re.findall(r"\w+", query.lower()))
        matches: list[tuple[float, dict[str, Any]]] = []

        for art in articles:
            if category and art.category.lower() != category.lower():
                continue
            title_lower = art.title.lower()
            content_lower = art.content.lower()
            score = 0.0
            for kw in keywords:
                if kw in title_lower:
                    score += 4.0
                if kw in content_lower:
                    score += 1.5
            if score > 0 or not keywords:
                d = art.to_dict()
                d["relevance_score"] = round(score, 2)
                matches.append((score, d))

        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches]

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
            return self._connectors.get("demo-store") or self._connectors[list(self._connectors.keys())[0]]
        return connector

    def get_store_config(self, store_id: str) -> StoreConfig:
        return self._stores.get(store_id, self._stores.get("demo-store", list(self._stores.values())[0]))

    def reset(self) -> None:
        """Reset all in-memory store and merchant states."""
        for conn in self._connectors.values():
            if hasattr(conn, "reset"):
                conn.reset()
        self._init_default_data()

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

