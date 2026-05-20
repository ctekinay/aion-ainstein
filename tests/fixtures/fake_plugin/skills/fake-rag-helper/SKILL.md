---
name: fake-rag-helper
description: Fixture RAG helper. Routes to the tree agent and shares the stub MCP server with archimate-tools.
---

# fake-rag-helper (fixture)

Exists to exercise the per-skill MCP routing rule (D10) and the race fix
in MCPPluginManager.get_server: this skill declares
`mcp_servers: [stub]` with `execution: tree`, while the fixture's
`archimate-tools` declares the same `[stub]` with `execution: archimate`.
At AInstein lifespan, `_mcp_tools_for("tree")` and
`_mcp_tools_for("archimate")` both call `MCPPluginManager.get_server(
fake-plugin, stub)` concurrently via `asyncio.gather`. Without the
construct-and-store lock added in commit 8a, two StdioServer instances
would race to spawn — exactly the bug the race fix prevents.
