"""SQL Abstract Syntax Tree (AST) validator ensuring read-only SELECT queries."""

from __future__ import annotations
import sqlparse
from sqlparse.sql import Token, TokenList
from sqlparse.tokens import DDL, DML, Keyword

from agentguard.errors import ValidationError

# Operations strictly forbidden in agent queries
_FORBIDDEN_KEYWORDS = frozenset({
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
    "EXEC", "EXECUTE", "CREATE", "GRANT", "REVOKE", "REPLACE",
    "MERGE", "CALL", "UPSERT", "VACUUM", "COPY", "SET",
})


def validate_sql_ast(sql: str) -> str:
    """Validate that incoming SQL is strictly a single, read-only SELECT statement using AST analysis.

    Raises:
        ValidationError: If the query is empty, chained, or contains mutating / administrative commands.
    """
    clean_sql = sql.strip()
    if not clean_sql:
        raise ValidationError(
            code="EMPTY_QUERY",
            hint="SQL query cannot be empty. Please provide a valid SELECT statement.",
            retryable=False,
        )

    parsed = sqlparse.parse(clean_sql)
    # Filter out empty statements or dangling comments
    statements = [s for s in parsed if str(s).strip() and not str(s).strip().startswith("--")]

    # 1. Defend against multi-statement query chaining (e.g. "SELECT 1; DROP TABLE users;")
    if len(statements) != 1:
        raise ValidationError(
            code="MULTI_STATEMENT_FORBIDDEN",
            hint=(
                f"Query contains {len(statements)} statements. "
                "Chained multi-statement queries are strictly forbidden for security."
            ),
            retryable=False,
            context={"statement_count": len(statements)},
        )

    stmt = statements[0]
    stmt_type = stmt.get_type()

    # 2. Defend against non-SELECT queries at top-level
    if stmt_type != "SELECT":
        raise ValidationError(
            code="SQL_MUTATION_FORBIDDEN",
            hint=(
                f"Forbidden SQL operation: '{stmt_type or 'UNKNOWN'}'. "
                "AgentGuard database tools are strictly read-only. Only SELECT queries are permitted."
            ),
            retryable=False,
            context={"attempted_type": stmt_type},
        )

    # 3. Deep AST token traversal to catch embedded mutations, subqueries, or administrative statements
    def _inspect_tokens(token_list: TokenList) -> None:
        for token in token_list.tokens:
            if token.is_group:
                _inspect_tokens(token)
            else:
                val = token.value.strip().upper()
                if val in _FORBIDDEN_KEYWORDS:
                    raise ValidationError(
                        code="FORBIDDEN_SQL_KEYWORD",
                        hint=(
                            f"SQL query contains forbidden keyword '{val}'. "
                            "Write operations and administrative statements are blocked."
                        ),
                        retryable=False,
                        context={"keyword": val},
                    )

    _inspect_tokens(stmt)
    return clean_sql

