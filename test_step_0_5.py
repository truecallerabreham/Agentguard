"""Test client for Step 0.5: verify running agentguard over stdio JSON-RPC."""

import asyncio
import sys
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def test_stdio_server():
    print("1. Starting agentguard stdio server process via stdio_client...")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agentguard.server"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            print("2. Performing MCP handshake (initialize)...")
            init_result = await session.initialize()
            print(f"   Handshake successful! Server: {init_result.serverInfo.name} v{init_result.serverInfo.version}")

            print("3. Discovering available tools (tools/list)...")
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"   Found tool: '{tool.name}' -> {tool.description}")

            print("4. Executing tool call (tools/call) with argument name='Abreham'...")
            call_result = await session.call_tool("greet", arguments={"name": "Abreham"})
            print(f"   Tool execution output: {call_result.content[0].text}")

            assert call_result.content[0].text == "Hello, Abreham!"
            print("\n*** ALL TESTS PASSED: AgentGuard stdio server is functioning perfectly! ***")


if __name__ == "__main__":
    asyncio.run(test_stdio_server())
