"""Shared helper for attaching plugin-supplied MCP tools to a Pydantic AI agent.

Each ``_build_<agent>_agent()`` function in this package registers its static
``@agent.tool`` decorators. Plugin-supplied MCP tools (synthesized via
``aion.mcp.tool_bridge.build_mcp_tool_callable``) are dynamic — discovered at
agent construction time from the multi-registry and the running
MCPPluginManager — and need a uniform registration path so the loop isn't
duplicated across six agent files.

``attach_mcp_tools(agent, tools)`` is that path. Each callable must already
have its ``__signature__`` set (tool_bridge does this via PEP 362) so
Pydantic AI's tool-spec generator picks the right shape for the LLM.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Sequence

logger = logging.getLogger(__name__)


def attach_mcp_tools(
    agent: Any,
    tools: Sequence[Callable[..., Awaitable[Any]]] | None,
) -> None:
    """Register each MCP-bridged tool on the agent.

    ``agent`` is a ``pydantic_ai.Agent`` instance (typed as ``Any`` to avoid
    importing Pydantic AI in this shared helper — each caller already
    has the import). ``tools`` may be ``None`` or empty — both are no-ops.

    Failures registering an individual tool are logged at WARNING and
    skipped; one bad MCP tool doesn't break the agent's static tools.
    """
    if not tools:
        return
    for tool_callable in tools:
        try:
            agent.tool(tool_callable)
        except Exception:
            logger.exception(
                "Failed to attach MCP tool %r to agent — skipping",
                getattr(tool_callable, "__name__", repr(tool_callable)),
            )
