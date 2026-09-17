"""The smallest MCP server that works."""

from __future__ import annotations

import asyncio
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# Initialize the MCP Server protocol object
mcp = Server("agentguard-hello")


# Handler for tool discovery: clients invoke tools/list to see available tools
@mcp.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Return the list of tools exposed by this server."""
    return [
        types.Tool(
            name="greet",
            description="Greet someone by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The name of the person to greet."}
                },
                "required": ["name"],
            },
        )
    ]


# Handler for tool execution: clients invoke tools/call with the tool name and arguments
@mcp.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """Execute a tool requested by the client."""
    if name == "greet":
        person_name = (arguments or {}).get("name", "World")
        return [types.TextContent(type="text", text=f"Hello, {person_name}!")]
    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    # Run the server over stdio streams (stdin for receiving, stdout for responding)
    async with stdio_server() as (read, write):
        await mcp.run(read, write, mcp.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
