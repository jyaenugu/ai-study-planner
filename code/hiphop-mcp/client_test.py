"""Smoke-test the hiphop MCP server over stdio. Calls today_obsessed and appends to USAGE LOG.md."""
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).parent
LOG = Path.home() / "Documents" / "Obsidian Vault" / "USAGE LOG.md"


async def call_and_log():
    params = StdioServerParameters(
        command=str(HERE / ".venv" / "bin" / "python"),
        args=[str(HERE / "server.py")],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            result = await session.call_tool("today_obsessed", {"min_plays": 1})
            payload = result.content[0].text if result.content else "(empty)"
            return {
                "server_name": init.serverInfo.name,
                "tool_count": len(tool_names),
                "tool_called": "today_obsessed",
                "args": {"min_plays": 1},
                "result": payload,
            }


def append_log(entry: dict):
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M KST")
    block = (
        f"\n## {ts} — `hiphop.today_obsessed`\n"
        f"- **Server:** {entry['server_name']} (custom MCP, stdio)\n"
        f"- **Transport:** MCP Python SDK stdio client → FastMCP server\n"
        f"- **Tool:** `today_obsessed(min_plays=1)`\n"
        f"- **Tools registered on this server:** {entry['tool_count']}\n"
        f"- **Result (truncated):** `{entry['result'][:300]}`\n"
    )
    if not LOG.exists():
        LOG.write_text(
            "# USAGE LOG\n\n"
            "Log of MCP-mediated tool calls. One entry per call.\n"
        )
    with LOG.open("a") as f:
        f.write(block)
    print(f"Logged to {LOG}")


def main():
    entry = asyncio.run(call_and_log())
    print(json.dumps(entry, indent=2))
    append_log(entry)


if __name__ == "__main__":
    main()
