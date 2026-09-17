"""Automated simulation of an external MCP host connecting to AgentGuard.

This replicates exactly how Claude Desktop or Cursor launches the server as a child process
and interacts with it using the Model Context Protocol over standard input/output.
"""

import asyncio
import sys
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def simulate_host_interaction():
    print("================================================================")
    print(" MCP HOST SIMULATION (Claude Desktop / Cursor -> AgentGuard)")
    print("================================================================")

    # 1. Configuration as defined in claude_desktop_config.json
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agentguard.server"],
    )
    print(f"\n[HOST] Spawning subprocess: {server_params.command} {' '.join(server_params.args)}")

    # 2. Host establishes pipe connection over stdin / stdout
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            
            # Step A: Handshake
            print("[HOST -> SERVER] Sending 'initialize' request...")
            init_response = await session.initialize()
            print(f"[SERVER -> HOST] Handshake accepted.")
            print(f"                 Connected to: {init_response.serverInfo.name} (v{init_response.serverInfo.version})")

            # Step B: Capability Discovery
            print("\n[HOST -> SERVER] Sending 'tools/list' discovery query...")
            tools_response = await session.list_tools()
            available_tools = tools_response.tools
            print(f"[SERVER -> HOST] Available tools advertised: {[t.name for t in available_tools]}")
            for t in available_tools:
                print(f"                 Tool: '{t.name}'")
                print(f"                 Description: {t.description}")
                print(f"                 Input Schema: {t.inputSchema}")

            # Step C: Tool Invocation
            target_tool = "greet"
            target_args = {"name": "Alice"}
            print(f"\n[HOST -> SERVER] LLM chose to call '{target_tool}' with args: {target_args}")
            call_response = await session.call_tool(target_tool, arguments=target_args)
            
            result_text = call_response.content[0].text
            print(f"[SERVER -> HOST] Execution Result: \"{result_text}\"")

            assert result_text == "Hello, Alice!"
            print("\n[HOST] SUCCESS: Host successfully executed tool and received result.")
            print("================================================================")


if __name__ == "__main__":
    asyncio.run(simulate_host_interaction())
