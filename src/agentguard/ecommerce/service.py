"""E-Commerce Support Service coordinating persistent store records, verified lookups, return policies, and HITL refund gates."""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
import json
import logging
import re
import secrets
from typing import Any

from agentguard.auth.security import (
    generate_api_key,
    generate_session_token,
    hash_password,
    verify_password,
)
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
    OrderItem,
    ReturnRemediationDecision,
    StoreConfig,
    StorePlatform,
)
from agentguard.errors import NotFoundError, PolicyError, ValidationError
from agentguard.governance.approval import get_approval_manager
from agentguard.observability.audit import get_audit_logger
from agentguard.storage.sqlite_db import SqliteDatabaseManager, get_sqlite_db

logger = logging.getLogger("agentguard.ecommerce.service")


class EcommerceService:
    """Enterprise coordination layer governing persistent database records, store connectors, identity verification, and refund gates."""

    def __init__(self, db: SqliteDatabaseManager | None = None) -> None:
        self.db = db or get_sqlite_db()
        self._connectors: dict[str, BaseStoreConnector] = {}
        self._init_default_data()

    def _init_default_data(self) -> None:
        """Initialize in-memory connectors for registered stores."""
        self._connectors.clear()
        demo_cfg = self.get_store_config("demo-store")
        self._init_connector(demo_cfg)

    def _init_connector(self, config: StoreConfig) -> None:
        if config.platform == StorePlatform.SHOPIFY:
            self._connectors[config.store_id] = ShopifyConnector(config)
        elif config.platform == StorePlatform.WOOCOMMERCE:
            self._connectors[config.store_id] = WooCommerceConnector(config)
        else:
            self._connectors[config.store_id] = SimulatorStoreConnector(config)

    def register_merchant(
        self,
        email: str,
        password: str,
        store_name: str,
        platform: str = "native",
        api_url: str = "",
        api_token: str = "",
        api_secret: str = "",
        return_window_days: int = 30,
    ) -> MerchantAccount:
        """Register a new e-commerce merchant and provision an isolated persistent store environment."""
        email_clean = email.strip().lower()
        if not email_clean or "@" not in email_clean:
            raise ValidationError(code="INVALID_EMAIL", hint="A valid email address is required.")
        if not password or len(password) < 6:
            raise ValidationError(code="WEAK_PASSWORD", hint="Password must be at least 6 characters.")
        if not store_name.strip():
            raise ValidationError(code="INVALID_STORE_NAME", hint="Store name is required.")

        # Check if email is already registered in persistent database
        existing = self.db.get_merchant_by_email(email_clean)
        if existing:
            raise ValidationError(code="EMAIL_EXISTS", hint="A merchant with this email address already exists.")

        # Generate unique store_id slug and credentials
        slug = re.sub(r"[^a-z0-9]+", "-", store_name.lower()).strip("-")[:16] or "store"
        rand_suffix = secrets.token_hex(3)
        store_id = f"store_{slug}_{rand_suffix}"
        merchant_id = f"merch_{secrets.token_hex(4)}"
        api_key = generate_api_key()

        plat_str = platform.lower()
        if plat_str in ("shopify", "woocommerce", "simulator", "native"):
            plat = StorePlatform(plat_str)
        else:
            plat = StorePlatform.NATIVE

        # Secure password hashing (PBKDF2-HMAC-SHA256)
        pwd_hash, salt = hash_password(password)

        # 1. Persist merchant to SQLite
        self.db.create_merchant(
            merchant_id=merchant_id,
            email=email_clean,
            password_hash=pwd_hash,
            salt=salt,
            store_name=store_name.strip(),
            store_id=store_id,
            api_key=api_key,
            platform=plat.value,
        )

        # 2. Persist store to SQLite
        self.db.create_store(
            store_id=store_id,
            merchant_id=merchant_id,
            store_name=store_name.strip(),
            platform=plat.value,
            api_url=api_url.strip() or f"https://{slug}.agentguard.store",
            return_window_days=int(return_window_days),
        )

        cfg = StoreConfig(
            store_id=store_id,
            store_name=store_name.strip(),
            platform=plat,
            api_url=api_url.strip() or f"https://{slug}.agentguard.store",
            api_token=api_token.strip(),
            api_secret=api_secret.strip(),
            return_window_days=int(return_window_days),
        )
        self._init_connector(cfg)

        # 3. Pre-seed initial custom policies in persistent DB
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

        merchant = MerchantAccount(
            merchant_id=merchant_id,
            email=email_clean,
            password_hash=pwd_hash,
            store_name=store_name.strip(),
            store_id=store_id,
            api_key=api_key,
            platform=plat.value,
        )

        logger.info("Successfully provisioned persistent merchant account %s (%s) for store %s", merchant_id, email_clean, store_id)
        return merchant

    def authenticate_merchant(self, email: str, password: str) -> MerchantAccount | None:
        """Authenticate merchant by email and password against persistent database."""
        email_clean = email.strip().lower()
        row = self.db.get_merchant_by_email(email_clean)
        if not row:
            return None

        if verify_password(password, row["salt"], row["password_hash"]):
            return MerchantAccount(
                merchant_id=row["merchant_id"],
                email=row["email"],
                password_hash=row["password_hash"],
                store_name=row["store_name"],
                store_id=row["store_id"],
                api_key=row["api_key"],
                platform=row["platform"],
            )
        return None

    def create_session(self, merchant_id: str, days: int = 30) -> dict[str, Any]:
        """Create a persistent session token."""
        token = generate_session_token()
        return self.db.create_session(session_id=token, merchant_id=merchant_id, days=days)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Validate and return session from persistent database."""
        return self.db.get_session(session_id)

    def delete_session(self, session_id: str) -> None:
        """Delete session token on logout."""
        self.db.delete_session(session_id)

    def get_merchant_by_api_key(self, api_key: str) -> MerchantAccount | None:
        row = self.db.get_merchant_by_api_key(api_key)
        if not row:
            return None
        return MerchantAccount(
            merchant_id=row["merchant_id"],
            email=row["email"],
            password_hash=row["password_hash"],
            store_name=row["store_name"],
            store_id=row["store_id"],
            api_key=row["api_key"],
            platform=row["platform"],
        )

    def get_merchant_by_store_id(self, store_id: str) -> MerchantAccount | None:
        row = self.db.get_merchant_by_store_id(store_id)
        if not row:
            return None
        return MerchantAccount(
            merchant_id=row["merchant_id"],
            email=row["email"],
            password_hash=row["password_hash"],
            store_name=row["store_name"],
            store_id=row["store_id"],
            api_key=row["api_key"],
            platform=row["platform"],
        )

    def add_kb_article(
        self,
        store_id: str,
        category: str,
        title: str,
        content: str,
    ) -> CustomKnowledgeArticle:
        """Add a custom policy or FAQ article to a store's persistent knowledge base."""
        if not title.strip() or not content.strip():
            raise ValidationError(code="INVALID_KB_ARTICLE", hint="Article title and content are required.")

        article_id = f"art_{secrets.token_hex(4)}"
        row = self.db.add_kb_article(
            article_id=article_id,
            store_id=store_id,
            category=category.strip().lower() or "general",
            title=title.strip(),
            content=content.strip(),
        )
        logger.info("Added persistent custom KB article '%s' for store '%s'", title, store_id)
        return CustomKnowledgeArticle(
            article_id=row["article_id"],
            store_id=row["store_id"],
            category=row["category"],
            title=row["title"],
            content=row["content"],
            created_at=row["created_at"],
        )

    def list_kb_articles(self, store_id: str) -> list[CustomKnowledgeArticle]:
        """List all custom policies and FAQs for a store from persistent database."""
        rows = self.db.list_kb_articles(store_id)
        return [
            CustomKnowledgeArticle(
                article_id=r["article_id"],
                store_id=r["store_id"],
                category=r["category"],
                title=r["title"],
                content=r["content"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def delete_kb_article(self, store_id: str, article_id: str) -> bool:
        """Delete an article from a store's persistent knowledge base."""
        return self.db.delete_kb_article(article_id, store_id)

    def search_store_kb(
        self,
        store_id: str,
        query: str,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search store's persistent knowledge base for keyword matches."""
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
        # Ensure store exists in DB
        existing = self.db.get_store(config.store_id)
        if not existing:
            self.db.create_store(
                store_id=config.store_id,
                merchant_id="merch_system",
                store_name=config.store_name,
                platform=config.platform.value,
                api_url=config.api_url,
                return_window_days=config.return_window_days,
            )
        else:
            self.db.update_store(
                store_id=config.store_id,
                store_name=config.store_name,
                platform=config.platform.value,
                api_url=config.api_url,
                return_window_days=config.return_window_days,
            )

        self._init_connector(config)
        logger.info("Registered %s store '%s' (ID: %s)", config.platform.value, config.store_name, config.store_id)

    def get_connector(self, store_id: str) -> BaseStoreConnector:
        """Retrieve connector for a store ID, falling back to simulator if unknown."""
        connector = self._connectors.get(store_id)
        if not connector:
            cfg = self.get_store_config(store_id)
            self._init_connector(cfg)
            connector = self._connectors.get(store_id)
        return connector or self._connectors.get("demo-store") or list(self._connectors.values())[0]

    def get_store_config(self, store_id: str) -> StoreConfig:
        row = self.db.get_store(store_id)
        if not row:
            row = self.db.get_store("demo-store")
        if not row:
            return StoreConfig(
                store_id=store_id,
                store_name="My Store",
                platform=StorePlatform.NATIVE,
                api_url="",
                return_window_days=30,
            )

        plat_str = row.get("platform", "native").lower()
        try:
            plat = StorePlatform(plat_str)
        except Exception:
            plat = StorePlatform.NATIVE

        return StoreConfig(
            store_id=row["store_id"],
            store_name=row["store_name"],
            platform=plat,
            api_url=row.get("api_url") or "",
            api_token=row.get("api_token_enc") or "",
            return_window_days=int(row.get("return_window_days", 30)),
        )

    def reset(self) -> None:
        """Reset state and database to pristine default demo store."""
        for conn in self._connectors.values():
            if hasattr(conn, "reset"):
                conn.reset()
        self.db.reset_database()
        self._init_default_data()

    def _row_to_order_details(self, row: dict[str, Any]) -> OrderDetails:
        """Convert a database row into a canonical OrderDetails object."""
        items_raw = json.loads(row.get("items_json") or "[]")
        items = [
            OrderItem(
                item_id=it.get("id", f"it_{idx}"),
                title=it.get("title", "Product"),
                quantity=it.get("quantity", 1),
                price_cents=int(it.get("unit_price", 0) * 100) or int(it.get("price_cents", 0)),
                sku=it.get("sku", ""),
            )
            for idx, it in enumerate(items_raw)
        ]
        status_str = row.get("fulfillment_status", "delivered").lower()
        try:
            fulfillment_status = OrderFulfillmentStatus(status_str)
        except Exception:
            fulfillment_status = OrderFulfillmentStatus.DELIVERED

        return OrderDetails(
            order_id=str(row["order_id"]),
            order_number=str(row["order_id"]),
            customer_email=row["customer_email"],
            customer_name=row.get("customer_name") or "Valued Customer",
            created_at=row.get("created_at") or "",
            total_cents=int(row["total_amount"] * 100),
            currency=row.get("currency", "USD"),
            fulfillment_status=fulfillment_status,
            items=items,
            delivered_at=row.get("delivered_at"),
            tracking_company=row.get("carrier"),
            tracking_number=row.get("tracking_number"),
            tracking_url=row.get("tracking_url"),
            store_id=row["store_id"],
        )

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

        # 1. Query persistent SQLite database first
        db_order = self.db.get_order(clean_num, store_id)
        if not db_order and store_id != "demo-store":
            # Check demo-store fallback if querying demo store orders
            db_order = self.db.get_order(clean_num, "demo-store")

        if db_order:
            order = self._row_to_order_details(db_order)
        else:
            # 2. Fallback to external store connector (Shopify / WooCommerce / Simulator)
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
        window_days = cfg.return_window_days

        if order.fulfillment_status != OrderFulfillmentStatus.DELIVERED:
            return ReturnRemediationDecision(
                eligible=False,
                status="NOT_DELIVERED",
                reason=f"Order is currently '{order.fulfillment_status.value}'. Returns can only be initiated after delivery.",
                days_since_delivery=None,
                return_window_days=window_days,
                order_number=order_number,
                total_refund_cents=order.total_cents,
                requires_human_approval=False,
            )

        if not order.delivered_at:
            days_since = 3
        else:
            try:
                del_time = datetime.fromisoformat(order.delivered_at.replace("Z", "+00:00"))
                days_since = (datetime.now(timezone.utc) - del_time).days
            except Exception:
                days_since = 3

        eligible = days_since <= window_days
        status = "ELIGIBLE" if eligible else "OUTSIDE_RETURN_WINDOW"
        reason_text = (
            f"Delivered {days_since} days ago. Within the {window_days}-day return policy window."
            if eligible
            else f"Delivered {days_since} days ago. Exceeds the store's {window_days}-day return policy window."
        )

        requires_human = order.total_cents > 5000

        return ReturnRemediationDecision(
            eligible=eligible,
            status=status,
            reason=reason_text,
            days_since_delivery=days_since,
            return_window_days=window_days,
            order_number=order_number,
            total_refund_cents=order.total_cents,
            items_to_return=[it.to_dict() for it in order.items],
            requires_human_approval=requires_human,
        )

    async def request_high_risk_refund(
        self,
        store_id: str,
        order_number: str,
        customer_email: str,
        amount_cents: int,
        reason: str,
    ) -> dict[str, Any]:
        """Queue a high-risk refund request for Human-in-the-Loop merchant review."""
        manager = get_approval_manager()

        request_data = manager.request_approval(
            tool_name="ecommerce_request_refund",
            arguments={
                "store_id": store_id,
                "order_number": order_number,
                "customer_email": customer_email,
                "amount_cents": amount_cents,
                "reason": reason,
            },
            tenant_id=store_id,
            user_id=f"customer:{customer_email}",
        )

        # Persist approval ticket to SQLite
        self.db.create_approval(
            approval_id=request_data["approval_id"],
            store_id=store_id,
            tool_name="ecommerce_request_refund",
            parameters={
                "store_id": store_id,
                "order_number": order_number,
                "customer_email": customer_email,
                "amount_cents": amount_cents,
                "reason": reason,
            },
            token=request_data["approval_token"],
        )

        audit = get_audit_logger()
        audit.log_action(
            action="ecommerce:refund_requested_held",
            parameters={
                "order_number": order_number,
                "amount_cents": amount_cents,
                "approval_id": request_data["approval_id"],
            },
            status="PENDING_APPROVAL",
        )

        return {
            "status": "held_for_approval",
            "approval_id": request_data["approval_id"],
            "approval_token": request_data["approval_token"],
            "order_number": order_number,
            "amount_cents": amount_cents,
            "message": f"Refund of ${amount_cents / 100:.2f} requires merchant authorization. Approval ticket {request_data['approval_id']} queued.",
        }

    async def execute_approved_refund(
        self,
        store_id: str,
        order_number: str,
        approval_id: str,
        approval_token: str,
        amount_cents: int,
        reason: str = "Authorized by merchant",
    ) -> dict[str, Any]:
        """Execute refund after validating single-use cryptographic approval token."""
        manager = get_approval_manager()

        # Enforce single-use token consumption (prevents replay attacks)
        if not manager.verify_and_consume(approval_id, approval_token):
            db_appr = self.db.get_approval_by_token(approval_token)
            if not db_appr or db_appr["status"] != "PENDING":
                raise PolicyError(
                    code="APPROVAL_TOKEN_INVALID",
                    hint=f"Approval request '{approval_id}' has already been consumed, expired, or is invalid.",
                )

        connector = self.get_connector(store_id)
        result = await connector.issue_refund(
            order_id=order_number,
            amount_cents=amount_cents,
            reason=reason,
        )

        # Mark token settled in DB
        self.db.decide_approval(approval_token, "APPROVE")

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
