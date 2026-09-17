"""Baseline MCP Server for AgentGuard using stdio transport."""

from mcp.server.fastmcp import FastMCP

# Initialize the Model Context Protocol server instance
mcp = FastMCP("agentguard")


@mcp.tool()
def greet(name: str = "World") -> str:
    """Return a personalized greeting for an agent or user."""
    return f"Hello, {name}!"


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers together."""
    return a + b


@mcp.tool()
def echo(message: str) -> str:
    """Echo back the input message."""
    return f"AgentGuard received: {message}"


def main():
    """Run the MCP server over standard input/output (stdio)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
