"""The smallest MCP server that works."""

from __future__ import annotations

import asyncio
from mcp.server.fastmcp import FastMCP

# FastMCP provides the modern, developer-friendly interface with @mcp.tool()
mcp = FastMCP("agentguard-hello")


@mcp.tool()
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


def main() -> None:
    # Run the server over stdio streams
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
