"""The smallest MCP server that works."""

from __future__ import annotations

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server

mcp = Server("agentguard-hello")


@mcp.tool()
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


async def main() -> None:
    async with stdio_server() as (read, write):
        await mcp.run(read, write, mcp.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
