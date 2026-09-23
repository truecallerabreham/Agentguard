"""Atomic tool for enterprise knowledge base search (returns, warranty, billing)."""

from __future__ import annotations
import re
from typing import Any

from agentguard.ecommerce.service import get_ecommerce_service
from agentguard.governance.tenant import current_tenant
from agentguard.tools.atomic.postgres import postgres_query


async def kb_search(
    query: str,
    category: str | None = None,
    store_id: str | None = None,
) -> list[dict[str, Any]]:
    """Search enterprise and store-specific knowledge base documentation for relevant policies and FAQs."""
    target_store = store_id or current_tenant.get() or "demo-store"
    svc = get_ecommerce_service()

    # 1. Search store-specific custom policies first
    custom_results = svc.search_store_kb(store_id=target_store, query=query, category=category)

    # 2. Query enterprise database knowledge base articles
    articles = await postgres_query("SELECT * FROM kb_articles")

    keywords = set(re.findall(r"\w+", query.lower()))
    matches: list[tuple[float, dict[str, Any]]] = []

    for article in articles:
        if category and article.get("category", "").lower() != category.lower():
            continue

        title = article.get("title", "").lower()
        content = article.get("content", "").lower()

        # Calculate keyword match score
        score = 0.0
        for kw in keywords:
            if kw in title:
                score += 3.0  # Title match carries higher weight
            if kw in content:
                score += 1.0

        if score > 0 or not keywords:
            match_data = dict(article)
            match_data["relevance_score"] = round(score, 2)
            matches.append((score, match_data))

    matches.sort(key=lambda x: x[0], reverse=True)
    global_results = [m[1] for m in matches]

    # Combine: store custom policies first, then global articles
    seen_titles = set()
    combined: list[dict[str, Any]] = []

    for item in custom_results:
        t = item.get("title", "").lower()
        if t not in seen_titles:
            seen_titles.add(t)
            combined.append(item)

    for item in global_results:
        t = item.get("title", "").lower()
        if t not in seen_titles:
            seen_titles.add(t)
            combined.append(item)

    return combined

