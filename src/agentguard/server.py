"""AgentGuard server — with transport switch."""

from __future__ import annotations

import asyncio
import os
from mcp.server.fastmcp import FastMCP

# Initialize the MCP Server
mcp = FastMCP("agentguard")


# Register the greet tool
@mcp.tool()
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


def run_stdio() -> None:
    """Run the server using stdio transport (stdin/stdout)."""
    mcp.run(transport="stdio")


def main() -> None:
    # Check the environment variable to decide which transport to use
    transport = os.environ.get("AGENTGUARD_TRANSPORT", "stdio")

    if transport == "stdio":
        run_stdio()
    else:
        # If someone asks for HTTP, fail explicitly until Milestone 1 implements it
        raise NotImplementedError("HTTP transport — Milestone 1 (Step 1.1)")


if __name__ == "__main__":
    main()
