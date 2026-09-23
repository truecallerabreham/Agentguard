"""Atomic tool for enterprise knowledge base search (returns, warranty, billing)."""

from __future__ import annotations
import re
from typing import Any
from agentguard.tools.atomic.postgres import postgres_query


async def kb_search(query: str, category: str | None = None) -> list[dict[str, Any]]:
    """Search enterprise knowledge base documentation for relevant policies and instructions."""
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

    # Sort descending by relevance score
    matches.sort(key=lambda x: x[0], reverse=True)
    return [m[1] for m in matches]

