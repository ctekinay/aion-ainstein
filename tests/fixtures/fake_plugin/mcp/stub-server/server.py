"""Minimal stdio MCP server for end-to-end tests.

Single tool ``echo`` returns its ``text`` argument verbatim. The schema
is intentionally simple so test assertions can verify the full chain:
  - tool discovery via ClientSession.list_tools()
  - parameter forwarding via call_tool with arguments
  - text-content extraction via _extract_text in StdioServer
"""

from __future__ import annotations

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


server = Server("stub-server")


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name="echo",
            description="Echo the given text back verbatim",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to echo"},
                },
                "required": ["text"],
            },
        ),
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "echo":
        return [TextContent(type="text", text=arguments.get("text", ""))]
    raise ValueError(f"unknown tool: {name}")


async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
