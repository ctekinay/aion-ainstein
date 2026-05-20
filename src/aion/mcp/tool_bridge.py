"""Synthesize Pydantic AI ``@agent.tool`` callables from MCP tool descriptors.

When an agent is built, we want the LLM to see the MCP-supplied tools with
proper schemas — argument names, types, descriptions. The MCP server publishes
this metadata via ``ClientSession.list_tools()``; this module turns each
descriptor into an async callable whose ``inspect.signature`` matches the
schema, so Pydantic AI's tool-spec generator picks the right shape.

Two-tier strategy:

1. **Per-tool callable** — one function per MCP tool, signature derived from
   ``inputSchema.properties``. Required props become positional/keyword
   parameters; optional props get ``None`` defaults. ``__signature__`` is set
   via ``inspect.Signature`` (PEP 362), which Pydantic AI honors.
2. **Async dispatcher body** — the function body looks up the running
   ``StdioServer`` from the ``MCPPluginManager`` singleton and calls
   ``server.call_tool(tool_name, kwargs)``. The agent's ``RunContext`` is
   the first parameter — present for parity with the rest of AInstein's
   Pydantic AI tools, ignored here.

The MCP JSON-Schema → Python-type mapping is intentionally narrow: enough
for what plugin authors actually write (strings, ints, floats, bools, plus
the catch-all ``Any`` for nested objects/arrays). Pydantic AI can serialize
``Any`` fine; the LLM sees the original JSON-schema in the tool description.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Awaitable, Callable

from pydantic_ai.tools import RunContext

logger = logging.getLogger(__name__)


_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
    # "null" → no Python type; falls back to Any.
}


def _python_type_from_schema(prop_schema: dict) -> Any:
    """Pick a Python type annotation for a JSON-schema property.

    JSON-Schema is richer than what we need to encode — anyOf/oneOf,
    nested objects, enums, etc. fall back to ``Any`` so Pydantic AI
    accepts whatever the LLM emits.
    """
    json_type = prop_schema.get("type")
    if isinstance(json_type, list):
        # ``"type": ["string", "null"]`` etc. — degrade to Any.
        return Any
    if isinstance(json_type, str):
        mapped = _JSON_TYPE_MAP.get(json_type)
        if mapped is not None:
            return mapped
    return Any


def build_mcp_tool_callable(
    plugin_name: str,
    server_name: str,
    tool_name: str,
    description: str,
    input_schema: dict,
    server_lookup: Callable[[str, str], Awaitable[Any]] | None = None,
) -> Callable[..., Awaitable[str]]:
    """Construct an async callable for one MCP tool.

    ``server_lookup`` defaults to ``MCPPluginManager.get_server`` from the
    process-wide singleton; tests can inject a stub.

    The returned function:
        * has ``__name__ = "<server>_<tool>"`` (Pydantic-AI-safe identifier),
        * has ``__doc__ = description``,
        * has ``__signature__`` matching the MCP input schema,
        * accepts a leading ``ctx`` positional parameter (RunContext) which
          is ignored — present so Pydantic AI's introspector picks the right
          shape across our codebase's conventions.
    """
    properties: dict = input_schema.get("properties", {}) or {}
    required: list[str] = list(input_schema.get("required", []) or [])

    if server_lookup is None:
        from aion.mcp.plugin_mcp import get_mcp_plugin_manager

        async def _default_lookup(p: str, s: str):
            return await get_mcp_plugin_manager().get_server(p, s)

        server_lookup = _default_lookup

    # Build the signature: ctx (RunContext), then one keyword-only param per
    # property. Pydantic AI's tool-spec generator requires the first parameter
    # to be annotated with ``RunContext[...]`` when registered via
    # ``@agent.tool`` (the context-taking variant). The bridged tool body
    # doesn't actually use ctx, but the annotation has to be correct or
    # registration fails with "First parameter of tools that take context
    # must be annotated with RunContext[...]".
    params: list[inspect.Parameter] = [
        inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=RunContext[Any]),
    ]
    for prop_name, prop_schema in properties.items():
        annot = _python_type_from_schema(prop_schema if isinstance(prop_schema, dict) else {})
        if prop_name in required:
            params.append(inspect.Parameter(
                prop_name,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=annot,
            ))
        else:
            params.append(inspect.Parameter(
                prop_name,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=annot,
                default=None,
            ))
    signature = inspect.Signature(parameters=params, return_annotation=str)

    async def _tool(ctx: Any = None, **kwargs: Any) -> str:
        # Drop None defaults for optional params so the MCP server sees only
        # what the LLM actually provided.
        payload = {k: v for k, v in kwargs.items() if v is not None}
        server = await server_lookup(plugin_name, server_name)
        return await server.call_tool(tool_name, payload)

    safe_name = f"{server_name}_{tool_name}".replace("-", "_")
    _tool.__name__ = safe_name
    _tool.__qualname__ = safe_name
    _tool.__doc__ = description or f"MCP tool {plugin_name}/{server_name}/{tool_name}"
    _tool.__signature__ = signature  # type: ignore[attr-defined]

    # Pydantic AI's tool-spec generator reads parameter types via
    # ``typing.get_type_hints(fn)`` — which inspects ``__annotations__``,
    # not ``__signature__``. Set both in lock-step so introspectors that
    # use either path see the same shape (without this, Pydantic AI raises
    # KeyError on each synthesized parameter name and the tool fails to
    # register — caught silently by attach_mcp_tools's try/except).
    annotations = {
        p.name: p.annotation
        for p in params
        if p.annotation is not inspect.Parameter.empty
    }
    annotations["return"] = str
    _tool.__annotations__ = annotations

    # Decorate so downstream code can identify MCP-bridged tools.
    _tool._is_mcp_bridged = True  # type: ignore[attr-defined]
    _tool._mcp_plugin = plugin_name  # type: ignore[attr-defined]
    _tool._mcp_server = server_name  # type: ignore[attr-defined]
    _tool._mcp_tool_name = tool_name  # type: ignore[attr-defined]
    return _tool


async def build_mcp_tools(
    plugin_name: str,
    server_name: str,
    server_lookup: Callable[[str, str], Awaitable[Any]] | None = None,
) -> list[Callable[..., Awaitable[str]]]:
    """Discover an MCP server's tools and synthesize a Pydantic-AI-ready list.

    Spawns the server if needed (via ``server_lookup``) to call
    ``list_tools()``. Tests can pre-stub ``server_lookup`` to skip the
    spawn entirely.
    """
    if server_lookup is None:
        from aion.mcp.plugin_mcp import get_mcp_plugin_manager

        async def _default_lookup(p: str, s: str):
            return await get_mcp_plugin_manager().get_server(p, s)

        server_lookup = _default_lookup

    server = await server_lookup(plugin_name, server_name)
    descriptors = await server.list_tools()

    callables: list[Callable[..., Awaitable[str]]] = []
    for desc in descriptors:
        name = getattr(desc, "name", None) or ""
        description = getattr(desc, "description", "") or ""
        # MCP SDK >=1.x: ``inputSchema`` is a dict.
        schema = getattr(desc, "inputSchema", None) or {}
        if not name:
            logger.warning(
                "MCP server %s/%s advertised a tool with no name — skipping", plugin_name, server_name,
            )
            continue
        callables.append(
            build_mcp_tool_callable(
                plugin_name=plugin_name,
                server_name=server_name,
                tool_name=name,
                description=description,
                input_schema=schema if isinstance(schema, dict) else {},
                server_lookup=server_lookup,
            )
        )
    return callables


# ----------------------------------------------------------------------
# Per-agent routing — which (plugin, server) pairs route to which agent type?

# Module-level cache to avoid duplicate misuse warnings across the N
# per-agent-type calls at startup (one per agent the factory builds).
_warned_framework_misuse: set[str] = set()


def mcp_servers_for_agent(agent_type: str, multi_registry) -> list[tuple[str, str]]:
    """Aggregate the ``(plugin, server)`` pairs needed by skills routing to ``agent_type``.

    Reads each enabled skill's ``execution`` and ``mcp_servers`` fields from
    the multi-registry. The plugin owner comes from
    ``multi_registry.get_owner(skill.name)``. Returns a deduplicated list
    in (plugin, server) lexicographic order for deterministic agent builds.

    Skills with empty/missing ``execution`` (no agent dispatch) that
    nevertheless declare ``mcp_servers`` produce a one-time startup
    warning and are ignored — framework-level skills cannot route MCP
    tools to agents. The warning fires once per offending skill across
    all ``mcp_servers_for_agent`` invocations, not once per agent type.
    """
    seen: set[tuple[str, str]] = set()
    for entry in multi_registry.list_skills():
        if not entry.enabled or not entry.mcp_servers:
            continue
        if not entry.execution:
            # Framework-level skill declaring MCP servers — misuse.
            if entry.name not in _warned_framework_misuse:
                logger.warning(
                    "Skill %r declares mcp_servers but no execution — MCP tools ignored "
                    "(framework-level skills cannot route MCP tools to agents).",
                    entry.name,
                )
                _warned_framework_misuse.add(entry.name)
            continue
        if entry.execution != agent_type:
            continue
        owner = multi_registry.get_owner(entry.name)
        if owner is None:
            # Conflicts_with auto-disable already removed this from the owner map;
            # the not-enabled check above would normally have caught it. Safety no-op.
            continue
        for server_name in entry.mcp_servers:
            seen.add((owner, server_name))

    return sorted(seen)


def _reset_framework_misuse_warnings_for_tests() -> None:
    """Drop the module-level warning cache. Tests call this to verify warnings fire."""
    _warned_framework_misuse.clear()
