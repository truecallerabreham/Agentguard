"""ACID-compliant SQLite database manager for AgentGuard with WAL mode and thread safety."""

from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

from agentguard.config import ServerSettings, get_settings

logger = logging.getLogger("agentguard.storage.sqlite")

SCHEMA_FILE = Path(__file__).parent / "schema.sql"


class SqliteDatabaseManager:
    """Manages persistent SQLite operations with WAL mode, foreign keys, and dictionary rows."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            settings = get_settings()
            db_path = getattr(settings, "db_path", "data/agentguard.db")

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Yield a connection with WAL mode and ensure it is properly closed."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database schema and seed initial data if empty."""
        with self._lock:
            with self._get_connection() as conn:
                if SCHEMA_FILE.exists():
                    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
                else:
                    logger.error("Schema file not found at %s", SCHEMA_FILE)

            # Check if default store is seeded
            self._seed_default_data_if_needed()

    def reset_database(self) -> None:
        """Clear all data, preserve schema, and re-seed default production data."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("PRAGMA foreign_keys = OFF;")
                for tbl in ["sessions", "approvals", "knowledge_articles", "orders", "products", "stores", "merchants"]:
                    conn.execute(f"DELETE FROM {tbl};")
                conn.commit()
                conn.execute("PRAGMA foreign_keys = ON;")
                conn.commit()
            self._seed_default_data_if_needed()

    def _seed_default_data_if_needed(self) -> None:
        """Seed default store, merchant, products, orders, and policies if not present."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) as cnt FROM stores WHERE store_id = 'demo-store'")
                if cursor.fetchone()["cnt"] > 0:
                    return

                logger.info("Seeding default production data into persistent SQLite database: %s", self.db_path)
                now = datetime.now(timezone.utc)
                now_str = now.isoformat()
                delivered_6d_ago = (now - timedelta(days=6)).isoformat()
                delivered_48d_ago = (now - timedelta(days=48)).isoformat()

                salt = "agentguard_salt_2026"
                pwd_hash = hashlib.sha256(f"{salt}:demo123".encode("utf-8")).hexdigest()

                # 1. Merchant
                conn.execute(
                    """
                    INSERT OR IGNORE INTO merchants 
                    (merchant_id, email, password_hash, salt, store_name, store_id, api_key, platform, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "merch_demo",
                        "demo@lumina-audio.com",
                        pwd_hash,
                        salt,
                        "Lumina Audio & Acoustics",
                        "demo-store",
                        "ag_live_demo_token",
                        "native",
                        now_str,
                    ),
                )

                # 2. Store
                conn.execute(
                    """
                    INSERT OR IGNORE INTO stores
                    (store_id, merchant_id, store_name, platform, api_url, return_window_days, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "demo-store",
                        "merch_demo",
                        "Lumina Audio & Acoustics",
                        "native",
                        "https://demo.lumina-audio.com",
                        30,
                        now_str,
                    ),
                )

                # 3. Products
                products = [
                    ("prod_101", "demo-store", "Studio ANC Wireless Headphones", "Flagship active noise cancelling studio headphones", 249.00, 42, "/static/headphones.jpg"),
                    ("prod_102", "demo-store", "Waterproof Rugged Speaker", "IPX7 waterproof portable bluetooth speaker with 24h battery", 89.00, 118, "/static/speaker.jpg"),
                    ("prod_103", "demo-store", "Broadcast Pro Condenser Mic", "High-fidelity cardioid condenser microphone for creators", 179.00, 24, "/static/mic.jpg"),
                    ("prod_104", "demo-store", "Studio Acoustic Reference Monitors", "Pair of bi-amplified 5-inch studio reference monitors", 349.00, 15, "/static/monitors.jpg"),
                ]
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO products
                    (product_id, store_id, title, description, price, inventory_count, image_url, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [(p[0], p[1], p[2], p[3], p[4], p[5], p[6], now_str) for p in products],
                )

                # 4. Orders
                orders = [
                    (
                        "1001",
                        "demo-store",
                        "sarah.connor@example.com",
                        "Sarah Connor",
                        114.00,
                        "USD",
                        "fulfilled",
                        "delivered",
                        "USPS",
                        "9400111899562537624128",
                        "https://tools.usps.com/go/TrackConfirmAction?tLabels=9400111899562537624128",
                        json.dumps([
                            {"id": "item_1", "title": "Wireless Noise-Canceling Headphones", "quantity": 1, "unit_price": 99.00},
                            {"id": "item_2", "title": "Braided Audio Cable 3.5mm", "quantity": 1, "unit_price": 15.00},
                        ]),
                        (now - timedelta(days=12)).isoformat(),
                        delivered_6d_ago,
                    ),
                    (
                        "1002",
                        "demo-store",
                        "alex.chen@example.com",
                        "Alex Chen",
                        249.00,
                        "USD",
                        "processing",
                        "in_transit",
                        "UPS",
                        "1Z9999999999999999",
                        "https://www.ups.com/track?tracknum=1Z9999999999999999",
                        json.dumps([{"id": "item_3", "title": "Smart Ergonomic Desk Chair", "quantity": 1, "unit_price": 249.00}]),
                        (now - timedelta(days=2)).isoformat(),
                        None,
                    ),
                    (
                        "1003",
                        "demo-store",
                        "elena.rostova@example.com",
                        "Elena Rostova",
                        135.00,
                        "USD",
                        "fulfilled",
                        "delivered",
                        "DHL Express",
                        "4209021093612898",
                        "https://www.dhl.com/en/express/tracking.html?AWB=4209021093612898",
                        json.dumps([{"id": "item_4", "title": "Mechanical Gaming Keyboard RGB", "quantity": 1, "unit_price": 135.00}]),
                        (now - timedelta(days=55)).isoformat(),
                        delivered_48d_ago,
                    ),
                    (
                        "1004",
                        "demo-store",
                        "marcus.vance@example.com",
                        "Marcus Vance",
                        89.00,
                        "USD",
                        "processing",
                        "out_for_delivery",
                        "FedEx",
                        "794829103948",
                        "https://www.fedex.com/apps/fedextrack/?tracknumbers=794829103948",
                        json.dumps([{"id": "item_5", "title": "Compact Espresso Machine", "quantity": 1, "unit_price": 89.00}]),
                        (now - timedelta(days=3)).isoformat(),
                        None,
                    ),
                ]
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO orders
                    (order_id, store_id, customer_email, customer_name, total_amount, currency, status, fulfillment_status, carrier, tracking_number, tracking_url, items_json, created_at, delivered_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    orders,
                )

                # 5. Policies
                articles = [
                    ("kb_1", "demo-store", "returns", "Lumina Audio 30-Day Return & Replacement Policy", "Customers may return any product within 30 days of delivery for a full refund or exchange. Items must be in original condition with all accessories.", now_str),
                    ("kb_2", "demo-store", "warranty", "Lumina Audio 1-Year Comprehensive Hardware Warranty", "All headphones and audio hardware come with a 1-year limited warranty covering manufacturing defects, audio driver failure, and loose wiring.", now_str),
                    ("kb_3", "demo-store", "shipping", "Shipping Rates & Delivery Timeframes", "Standard shipping takes 3-5 business days via USPS or UPS. Priority express shipping delivers in 1-2 business days with real-time tracking.", now_str),
                ]
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO knowledge_articles
                    (article_id, store_id, category, title, content, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    articles,
                )
                conn.commit()

    # --- Query Execution Helpers ---

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Execute a write query and return rowcount."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur.rowcount

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Execute a query and return a single row as a dict."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(sql, params)
                row = cur.fetchone()
                return dict(row) if row is not None else None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute a query and return all rows as dicts."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(sql, params)
                rows = cur.fetchall()
                return [dict(r) for r in rows]

    def list_tables(self) -> list[str]:
        """List all user tables in the database."""
        rows = self.fetch_all("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        return [r["name"] for r in rows]

    # --- Merchant & Session Methods ---

    def create_merchant(
        self,
        merchant_id: str,
        email: str,
        password_hash: str,
        salt: str,
        store_name: str,
        store_id: str,
        api_key: str,
        platform: str = "native",
    ) -> dict[str, Any]:
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            self.execute(
                """
                INSERT INTO merchants (merchant_id, email, password_hash, salt, store_name, store_id, api_key, platform, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (merchant_id, email, password_hash, salt, store_name, store_id, api_key, platform, now),
            )
            return self.fetch_one("SELECT * FROM merchants WHERE merchant_id = ?", (merchant_id,))

    def get_merchant_by_email(self, email: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM merchants WHERE LOWER(email) = LOWER(?)", (email.strip(),))

    def get_merchant_by_id(self, merchant_id: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM merchants WHERE merchant_id = ?", (merchant_id,))

    def get_merchant_by_api_key(self, api_key: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM merchants WHERE api_key = ?", (api_key,))

    def get_merchant_by_store_id(self, store_id: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM merchants WHERE store_id = ?", (store_id,))

    def create_session(self, session_id: str, merchant_id: str, days: int = 30) -> dict[str, Any]:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        self.execute(
            "INSERT INTO sessions (session_id, merchant_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (session_id, merchant_id, expires_at, now),
        )
        return self.fetch_one("SELECT * FROM sessions WHERE session_id = ?", (session_id,))

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        return self.fetch_one(
            "SELECT s.*, m.email, m.store_name, m.store_id, m.api_key FROM sessions s JOIN merchants m ON s.merchant_id = m.merchant_id WHERE s.session_id = ? AND s.expires_at > ?",
            (session_id, now),
        )

    def delete_session(self, session_id: str) -> None:
        self.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    # --- Store & Product Methods ---

    def create_store(
        self,
        store_id: str,
        merchant_id: str,
        store_name: str,
        platform: str = "native",
        api_url: str | None = None,
        return_window_days: int = 30,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        self.execute(
            """
            INSERT INTO stores (store_id, merchant_id, store_name, platform, api_url, return_window_days, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (store_id, merchant_id, store_name, platform, api_url, return_window_days, now),
        )
        return self.fetch_one("SELECT * FROM stores WHERE store_id = ?", (store_id,))

    def get_store(self, store_id: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM stores WHERE store_id = ?", (store_id,))

    def update_store(
        self,
        store_id: str,
        store_name: str | None = None,
        platform: str | None = None,
        api_url: str | None = None,
        return_window_days: int | None = None,
    ) -> dict[str, Any]:
        current = self.get_store(store_id)
        if not current:
            raise ValueError(f"Store {store_id} not found")
        
        name = store_name if store_name is not None else current["store_name"]
        plat = platform if platform is not None else current["platform"]
        url = api_url if api_url is not None else current["api_url"]
        window = return_window_days if return_window_days is not None else current["return_window_days"]
        
        self.execute(
            "UPDATE stores SET store_name = ?, platform = ?, api_url = ?, return_window_days = ? WHERE store_id = ?",
            (name, plat, url, window, store_id),
        )
        return self.get_store(store_id)

    def list_products(self, store_id: str) -> list[dict[str, Any]]:
        return self.fetch_all("SELECT * FROM products WHERE store_id = ? ORDER BY price DESC", (store_id,))

    # --- Orders Methods ---

    def get_order(self, order_id: str, store_id: str) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM orders WHERE order_id = ? AND store_id = ?",
            (str(order_id).strip(), store_id.strip()),
        )

    def list_orders(self, store_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM orders WHERE store_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (store_id, limit, offset),
        )

    def create_order(
        self,
        order_id: str,
        store_id: str,
        customer_email: str,
        customer_name: str,
        total_amount: float,
        carrier: str = "FedEx",
        tracking_number: str = "",
        fulfillment_status: str = "fulfilled",
        status: str = "delivered",
        items: list[dict[str, Any]] | None = None,
        delivered_at: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        items_json = json.dumps(items or [])
        tracking_url = f"https://www.fedex.com/fedextrack/?trknbr={tracking_number}" if carrier.lower() == "fedex" else ""
        
        self.execute(
            """
            INSERT INTO orders 
            (order_id, store_id, customer_email, customer_name, total_amount, currency, status, fulfillment_status, carrier, tracking_number, tracking_url, items_json, created_at, delivered_at)
            VALUES (?, ?, ?, ?, ?, 'USD', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(order_id).strip(),
                store_id,
                customer_email.strip().lower(),
                customer_name.strip(),
                float(total_amount),
                status,
                fulfillment_status,
                carrier,
                tracking_number,
                tracking_url,
                items_json,
                now,
                delivered_at or (now if fulfillment_status == "delivered" else None),
            ),
        )
        return self.get_order(order_id, store_id)

    # --- Knowledge Base Articles ---

    def list_kb_articles(self, store_id: str) -> list[dict[str, Any]]:
        return self.fetch_all("SELECT * FROM knowledge_articles WHERE store_id = ? ORDER BY created_at DESC", (store_id,))

    def add_kb_article(self, article_id: str, store_id: str, category: str, title: str, content: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        self.execute(
            "INSERT INTO knowledge_articles (article_id, store_id, category, title, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (article_id, store_id, category, title, content, now),
        )
        return self.fetch_one("SELECT * FROM knowledge_articles WHERE article_id = ?", (article_id,))

    def delete_kb_article(self, article_id: str, store_id: str) -> bool:
        rows = self.execute("DELETE FROM knowledge_articles WHERE article_id = ? AND store_id = ?", (article_id, store_id))
        return rows > 0

    # --- Approvals ---

    def create_approval(
        self,
        approval_id: str,
        store_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        token: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        params_json = json.dumps(parameters)
        self.execute(
            """
            INSERT INTO approvals (approval_id, store_id, tool_name, parameters_json, token, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (approval_id, store_id, tool_name, params_json, token, now),
        )
        return self.fetch_one("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,))

    def get_approval_by_token(self, token: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM approvals WHERE token = ?", (token,))

    def list_approvals(self, store_id: str, status: str = "PENDING") -> list[dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM approvals WHERE store_id = ? AND status = ? ORDER BY created_at DESC",
            (store_id, status),
        )

    def decide_approval(self, token: str, decision: str, resolved_by: str = "merchant:web") -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        status = "SETTLED" if decision.upper() == "APPROVE" else "REJECTED"
        self.execute(
            "UPDATE approvals SET status = ?, resolved_at = ?, resolved_by = ? WHERE token = ?",
            (status, now, resolved_by, token),
        )
        return self.get_approval_by_token(token)


# Singleton instance
_sqlite_manager: SqliteDatabaseManager | None = None
_manager_lock = threading.Lock()


def get_sqlite_db(settings: ServerSettings | None = None) -> SqliteDatabaseManager:
    """Get or initialize singleton SQLite database manager."""
    global _sqlite_manager
    if _sqlite_manager is None:
        with _manager_lock:
            if _sqlite_manager is None:
                path = getattr(settings, "db_path", "data/agentguard.db") if settings else "data/agentguard.db"
                _sqlite_manager = SqliteDatabaseManager(db_path=path)
    return _sqlite_manager
