"""Atomic tool for executing queries against PostgreSQL with Row-Level Security."""

from __future__ import annotations
from typing import Any
from agentguard.db.pool import get_db_manager
from agentguard.governance.tenant import current_tenant
from agentguard.errors import PolicyError
from agentguard.validation.sql import validate_sql_ast


async def postgres_query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """Execute a read-only SQL query within the caller's tenant-isolated database session.

    The query automatically inherits the tenant context established by the authentication token
    and row-level security (RLS) policies. You cannot query or view data belonging to other tenants.
    """
    tenant_id = current_tenant.get()
    if not tenant_id:
        raise PolicyError("Cannot execute database query: Missing or invalid tenant context.")

    # Validate SQL via AST analysis (strictly SELECT only, no chained queries)
    clean_sql = validate_sql_ast(sql)

    db = get_db_manager()
    return await db.execute_query(tenant_id=tenant_id, sql=clean_sql, params=params)
