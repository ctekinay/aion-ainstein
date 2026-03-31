"""Generic MCP client using the mcp SDK's Streamable HTTP transport.

Connects to any remote MCP server registered in config.yaml and calls
tools by name. Used by server-specific wrappers (e.g., github.py).
"""

import base64
import logging

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from aion.config import settings

from .registry import MCPServerConfig

logger = logging.getLogger(__name__)


def _extract_text(content_blocks: list) -> str:
    """Extract text from MCP content blocks.

    Handles three block types returned by MCP tools:
    - TextContent (type="text"): plain text in .text
    - EmbeddedResource (type="resource"): file content in .resource.text
      or base64-encoded binary in .resource.blob
    - ImageContent: skipped (not relevant for text extraction)

    For get_file_contents, the GitHub MCP server returns a TextContent
    status message ("successfully downloaded...") AND an EmbeddedResource
    with the actual file content. We prefer EmbeddedResource content
    when present, falling back to TextContent.
    """
    resource_texts = []
    plain_texts = []

    for block in content_blocks:
        block_type = getattr(block, "type", None)

        if block_type == "resource":
            resource = getattr(block, "resource", None)
            if resource and hasattr(resource, "text"):
                resource_texts.append(resource.text)
            elif resource and hasattr(resource, "blob"):
                resource_texts.append(
                    base64.b64decode(resource.blob).decode("utf-8")
                )
        elif block_type == "text" and hasattr(block, "text"):
            plain_texts.append(block.text)

    # Prefer embedded resource content (actual file data) over
    # plain text (status messages like "successfully downloaded...")
    return "\n".join(resource_texts) if resource_texts else "\n".join(plain_texts)


async def call_tool(
    server: MCPServerConfig,
    tool_name: str,
    arguments: dict,
    timeout: float = settings.timeout_llm_call,
) -> str:
    """Call an MCP tool on a remote server and return the text result.

    Creates a session per call (connect → initialize → call → close).
    The remote server handles session lifecycle.

    Args:
        server: Server config from registry.
        tool_name: MCP tool name (e.g., "get_file_contents").
        arguments: Tool arguments as a dict.
        timeout: Request timeout in seconds.

    Returns:
        Tool result as a string (extracted from content blocks).

    Raises:
        ValueError: If no token, tool returns error, or no text content.
    """
    if not server.token:
        raise ValueError(
            f"No auth token for MCP server '{server.name}'. "
            f"Set {server.auth_env_var} in your .env file."
        )

    http_client = httpx.AsyncClient(
        headers=server.auth_headers,
        timeout=timeout,
    )

    async with streamable_http_client(server.url, http_client=http_client) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

    if result.isError:
        raise ValueError(f"MCP tool '{tool_name}' failed: {result.content}")

    text = _extract_text(result.content)
    if not text:
        raise ValueError(f"MCP tool '{tool_name}' returned no text content")

    return text
