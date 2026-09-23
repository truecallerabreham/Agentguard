"""Database connection manager supporting PostgreSQL RLS transactions with in-memory fallback."""

from __future__ import annotations
import logging
import re
from typing import Any
import asyncpg

from agentguard.config import ServerSettings, get_settings
from agentguard.errors import UpstreamError

logger = logging.getLogger("agentguard.db")

# In-memory mock data matching deploy/sql/init.sql for zero-dependency local testing
MOCK_CUSTOMERS = [
    {"id": "CUST-1001", "tenant_id": "acme", "name": "Alicia Rivera", "email": "alicia@acme.com", "tier": "gold"},
    {"id": "CUST-2001", "tenant_id": "globex", "name": "Cho Nakamura", "email": "cho@globex.com", "tier": "gold"},
]

MOCK_ORDERS = [
    {"id": "o_9001", "tenant_id": "acme", "customer_id": "CUST-1001", "status": "delivered", "total_cents": 12900},
    {"id": "o_9002", "tenant_id": "acme", "customer_id": "CUST-1001", "status": "processing", "total_cents": 4500},
    {"id": "o_9101", "tenant_id": "globex", "customer_id": "CUST-2001", "status": "refund_pending", "total_cents": 8900},
]

MOCK_KB_ARTICLES = [
    {
        "id": "KB-101",
        "tenant_id": "global",
        "category": "returns",
        "title": "Return Policy & Refunds",
        "content": "Customers may request a return within 30 days of delivery. Gold tier members receive free return shipping and 100% refund with zero restocking fee. Standard tier has a 10% restocking fee. Items must be in original condition.",
    },
    {
        "id": "KB-102",
        "tenant_id": "global",
        "category": "warranty",
        "title": "Defective Merchandise & Replacement",
        "content": "Defective merchandise reported within 90 days qualifies for immediate return or direct replacement. Replacement orders are shipped via priority delivery within 24 hours of ticket confirmation.",
    },
    {
        "id": "KB-103",
        "tenant_id": "global",
        "category": "billing",
        "title": "Billing Inquiries & Payment Disputes",
        "content": "Invoices are generated upon shipment. Refunds take 3-5 business days to post to the original payment method after an RMA has been settled.",
    },
]

MOCK_TICKETS: list[dict[str, Any]] = []


class DatabaseManager:
    """Manages PostgreSQL connection pooling and executes queries inside tenant-isolated RLS transactions."""

    def __init__(self, settings: ServerSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self._pool: asyncpg.Pool | None = None
        self._is_fallback: bool = False
        self._initialized: bool = False

    @property
    def is_fallback(self) -> bool:
        """True if running in simulated in-memory RLS fallback mode."""
        return self._is_fallback

    async def initialize(self) -> None:
        """Attempt to connect to PostgreSQL. Fall back to in-memory RLS if unreachable."""
        if self._initialized:
            return
        self._initialized = True
        try:
            self._pool = await asyncpg.create_pool(
                dsn=self.settings.postgres_url,
                min_size=1,
                max_size=10,
                timeout=2.0,
            )
            self._is_fallback = False
            logger.info("Connected to PostgreSQL connection pool with RLS support.")
        except Exception as exc:
            self._pool = None
            self._is_fallback = True
            logger.warning(
                "PostgreSQL not reachable at %s (%s). Using in-memory RLS simulator.",
                self.settings.postgres_url,
                exc,
            )

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
        self._initialized = False

    async def execute_query(
        self,
        tenant_id: str,
        sql: str,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a SQL query inside a transaction strictly scoped to `tenant_id`."""
        if not self._initialized:
            await self.initialize()
        if not tenant_id:
            raise UpstreamError("Cannot execute query without an active tenant_id context.")

        params = params or []

        # 1. Real PostgreSQL execution with transaction-scoped RLS variable
        if self._pool is not None:
            try:
                async with self._pool.acquire() as conn:
                    async with conn.transaction():
                        # Set transaction-local session variable app.tenant_id
                        await conn.execute("SET LOCAL app.tenant_id = $1", tenant_id)
                        records = await conn.fetch(sql, *params)
                        return [dict(record) for record in records]
            except Exception as exc:
                raise UpstreamError(f"PostgreSQL query failed: {exc}") from exc

        # 2. In-Memory RLS Simulator (when Postgres service is offline)
        return self._simulate_rls_query(tenant_id, sql, params)

    def _simulate_rls_query(
        self,
        tenant_id: str,
        sql: str,
        params: list[Any] | tuple[Any, ...],
    ) -> list[dict[str, Any]]:
        """Simulate Postgres Row-Level Security by strictly filtering records by tenant_id."""
        normalized = sql.lower()

        # Determine target table
        if "customers" in normalized:
            rows = [dict(r) for r in MOCK_CUSTOMERS if r["tenant_id"] == tenant_id]
        elif "orders" in normalized:
            rows = [dict(r) for r in MOCK_ORDERS if r["tenant_id"] == tenant_id]
        elif "kb_articles" in normalized:
            rows = [dict(r) for r in MOCK_KB_ARTICLES if r["tenant_id"] in (tenant_id, "global")]
        elif "tickets" in normalized:
            rows = [dict(r) for r in MOCK_TICKETS if r["tenant_id"] == tenant_id]
        else:
            rows = []

        # Optional simple ID filter e.g. "WHERE id = $1" or "WHERE customer_id = $1"
        if params:
            target_val = str(params[0])
            rows = [
                r for r in rows
                if r.get("id") == target_val or r.get("customer_id") == target_val
            ]

        return rows

    def create_ticket(self, tenant_id: str, ticket: dict[str, Any]) -> dict[str, Any]:
        """Store a support ticket scoped to tenant_id."""
        record = dict(ticket)
        record["tenant_id"] = tenant_id
        MOCK_TICKETS.append(record)
        return record



_db_manager: DatabaseManager | None = None


def get_db_manager(settings: ServerSettings | None = None) -> DatabaseManager:
    """Singleton getter for DatabaseManager."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(settings)
    return _db_manager
