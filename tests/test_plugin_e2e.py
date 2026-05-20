"""End-to-end test for plugin architecture migration.

Exercises the full chain — discovery, multi-plugin registry,
conflicts_with resolution, slash routing, MCP server lifecycle,
per-skill tool routing, attribution under collision, hook firing —
using ``tests/fixtures/fake_plugin/`` alongside the in-tree
``enterpower-architecture``. No FastAPI/Weaviate/Ollama: the test drives
the plugin runtime directly so it runs anywhere pytest does.

RE-BASELINE (Phase-5/supersession, user-authorized — intended program
consequence, not a silent break): ainstein-core was deleted;
enterpower-architecture is the authoritative owner of ``archimate-tools``
(and the rest of the architecture domain). The conflicts_with collision
this e2e exercises is preserved by re-pointing the fixture's
``conflicts_with`` target from ``ainstein-core/archimate-tools`` to
``enterpower-architecture/archimate-tools`` — the auto-disable /
attribution / DuplicateSkillError plumbing under test is unchanged in
kind.

The fixture is deliberately designed to:

* declare ``archimate-tools`` (collision with enterpower-architecture)
  with ``conflicts_with: [enterpower-architecture/archimate-tools]`` —
  auto-disable resolves the load, re-enable raises DuplicateSkillError;
* declare two skills both pointing at the same stub MCP server but
  routing to different agent types (archimate + tree) — exercises the
  per-skill MCP routing rule AND the race fix in
  MCPPluginManager.get_server via concurrent asyncio.gather discovery;
* ship a tiny Python MCP server (~30 lines, ``mcp`` SDK) that advertises
  one ``echo`` tool — small enough that protocol-drift maintenance is
  trivial;
* fire a PostToolUse hook on ``Write`` that captures the stdin payload
  to ``$WRITE_LOG`` so the test can assert the hook plumbing end-to-end.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aion.mcp.plugin_mcp import (
    MCPPluginManager,
    _reset_mcp_plugin_manager_for_tests,
    get_mcp_plugin_manager,
)
from aion.skills.multi_registry import (
    DuplicateSkillError,
    MultiPluginRegistry,
    _reset_multi_registry_for_tests,
)
from aion.skills.plugin import load_plugin_manifest


FAKE_PLUGIN_ROOT = Path(__file__).parent / "fixtures" / "fake_plugin"
ENTERPOWER_ROOT = Path(__file__).parent.parent / "plugins" / "enterpower-architecture"


@pytest.fixture
def dual_registry(monkeypatch):
    """Build a multi-registry with fake-plugin and enterpower-architecture.

    Order is deterministic: env-var/fake first (via add_plugin_from_object
    order), in-tree enterpower-architecture second. Matches production
    discovery order so conflicts_with resolution behaves the same way.
    """
    _reset_multi_registry_for_tests()
    _reset_mcp_plugin_manager_for_tests()

    fake = load_plugin_manifest(FAKE_PLUGIN_ROOT)
    enterpower = load_plugin_manifest(ENTERPOWER_ROOT)

    multi = MultiPluginRegistry()
    multi.add_plugin_from_object(fake)
    multi.add_plugin_from_object(enterpower)
    multi.load()

    # Install as the process-wide singleton so api.py sees this state.
    import aion.skills.multi_registry as mr
    mr._global_multi = multi

    yield multi

    _reset_multi_registry_for_tests()
    _reset_mcp_plugin_manager_for_tests()


# ---------------------------------------------------------------------------
# Discovery + conflicts_with resolution


class TestDiscoveryAndConflictResolution:
    def test_both_plugins_load_clean(self, dual_registry):
        names = dual_registry.list_plugins()
        assert "fake-plugin" in names
        assert "enterpower-architecture" in names

    def test_fake_plugin_archimate_tools_auto_disabled(self, dual_registry):
        """The fixture's archimate-tools declares conflicts_with —
        enterpower-architecture's copy is enabled, so the fixture's
        self-disables."""
        # enterpower-architecture wins on owner.
        assert dual_registry.get_owner("archimate-tools") == "enterpower-architecture"
        # fake-plugin's copy exists but is_enabled=False in memory.
        fake_entry = dual_registry._registries["fake-plugin"].get_skill_entry("archimate-tools")
        assert fake_entry is not None
        assert fake_entry.enabled is False
        # enterpower-architecture's copy stays enabled.
        ep_entry = dual_registry._registries["enterpower-architecture"].get_skill_entry("archimate-tools")
        assert ep_entry is not None
        assert ep_entry.enabled is True

    def test_fake_rag_helper_owned_by_fake_plugin(self, dual_registry):
        """fake-rag-helper exists only in fake-plugin — no collision."""
        assert dual_registry.get_owner("fake-rag-helper") == "fake-plugin"


# ---------------------------------------------------------------------------
# Attribution under collision (api.py wiring)


class TestAttributionViaApi:
    def test_list_skills_attributes_each_archimate_tools_to_its_plugin(self, dual_registry):
        from aion.skills.api import list_skills

        rows = list_skills()
        at_rows = [r for r in rows if r["name"] == "archimate-tools"]
        assert len(at_rows) == 2

        by_plugin = {r["plugin"]: r for r in at_rows}
        assert "fake-plugin" in by_plugin
        assert "enterpower-architecture" in by_plugin

        # Enabled flags reflect conflicts_with auto-disable.
        assert by_plugin["fake-plugin"]["enabled"] is False
        assert by_plugin["enterpower-architecture"]["enabled"] is True

    def test_list_plugins_skill_counts_per_plugin_under_collision(self, dual_registry):
        from aion.skills.api import list_plugins

        plugins = list_plugins()
        by_name = {p["name"]: p for p in plugins}

        # fake-plugin declares 2 skills (archimate-tools + fake-rag-helper).
        assert by_name["fake-plugin"]["skill_count"] == 2
        # Phase-5 supersession re-baseline (intended, documented — not a
        # silent break): ainstein-core was deleted; enterpower-architecture
        # is the authoritative architecture-domain provider with 9 skills
        # (archimate-oxc-generator/-oxc-view-generator/-tools/-viewer/
        # -visual-composer, principle-generator/-quality-assessor,
        # repo-to-archimate, repo-architecture-explorer). The
        # fake-plugin↔enterpower conflicts_with collision this test
        # exercises is preserved: archimate-tools stays in enterpower.
        assert by_name["enterpower-architecture"]["skill_count"] == 9

        # fake-plugin's archimate-tools auto-disabled — only fake-rag-helper enabled.
        assert by_name["fake-plugin"]["enabled_count"] == 1

    def test_re_enable_shadowed_skill_returns_duplicate_skill_error(self, dual_registry):
        """The locked-decision scenario: user clicks "re-enable" on
        fake-plugin/archimate-tools (shadowed). The plugin-scoped API
        MUST reach the preflight and raise DuplicateSkillError so the
        UI surfaces HTTP 409. Pre-attribution-fix, this returned HTTP
        404 instead because find_plugin_for_skill misrouted.
        """
        from aion.skills.api import toggle_skill_enabled_in_plugin

        with pytest.raises(DuplicateSkillError, match="would conflict"):
            toggle_skill_enabled_in_plugin("fake-plugin", "archimate-tools", True)


# ---------------------------------------------------------------------------
# Slash command routing


class TestSlashRoutingAgainstFakePlugin:
    def test_slash_router_finds_invocable_fake_skill(self, dual_registry):
        """fake-rag-helper has inject_mode: on_demand, so the slash router
        accepts /fake-rag-helper. fake-plugin's archimate-tools is
        auto-disabled, so /archimate-tools resolves to
        enterpower-architecture's copy (still invocable)."""
        from aion.skills.slash_router import SlashRouter

        router = SlashRouter(dual_registry)
        cmd = router.parse("/fake-rag-helper")
        assert cmd is not None
        assert cmd.skill_name == "fake-rag-helper"
        # Disabled skills aren't invocable.
        # fake-plugin/archimate-tools is auto-disabled but
        # enterpower-architecture's is enabled, so /archimate-tools resolves.
        cmd2 = router.parse("/archimate-tools")
        assert cmd2 is not None
        assert cmd2.skill_name == "archimate-tools"


# ---------------------------------------------------------------------------
# MCP server lifecycle + race fix


class TestStubMcpServerLifecycle:
    @pytest.mark.asyncio
    async def test_mcp_server_spawns_and_lists_echo_tool(self, dual_registry):
        """Spawns the fixture's real Python MCP server (subprocess) and
        verifies the ``echo`` tool is discovered via list_tools."""
        mgr = get_mcp_plugin_manager()
        # Register fake-plugin's MCP servers (uses root .mcp.json fallback).
        mgr.register_plugin(dual_registry.get_plugin("fake-plugin"))

        try:
            server = await mgr.get_server("fake-plugin", "stub")
            tools = await server.list_tools()
            tool_names = [t.name for t in tools]
            assert "echo" in tool_names

            result = await server.call_tool("echo", {"text": "hello e2e"})
            assert "hello e2e" in result
        finally:
            await mgr.shutdown_all()

    @pytest.mark.asyncio
    async def test_concurrent_get_server_returns_same_real_subprocess(self, dual_registry):
        """The race-fix regression test in test_plugin_mcp.py uses a fake
        StdioServer. This version uses the REAL fixture subprocess: two
        agent-type discovery paths racing on get_server(fake-plugin, stub)
        must end up sharing one subprocess, not orphan one.
        """
        mgr = get_mcp_plugin_manager()
        mgr.register_plugin(dual_registry.get_plugin("fake-plugin"))

        try:
            srv1, srv2 = await asyncio.gather(
                mgr.get_server("fake-plugin", "stub"),
                mgr.get_server("fake-plugin", "stub"),
            )
            assert srv1 is srv2
            assert srv1.is_alive()
        finally:
            await mgr.shutdown_all()


# ---------------------------------------------------------------------------
# Per-skill MCP-to-agent routing (D10)


class TestMcpServersForAgentUnderFixture:
    def test_archimate_agent_gets_stub_server(self, dual_registry):
        """fake-plugin's archimate-tools is auto-disabled, but
        enterpower-architecture's archimate-tools also routes to archimate
        (no mcp_servers though). The stub server should NOT appear on the
        archimate agent because the only declaring skill is
        auto-disabled."""
        from aion.mcp.tool_bridge import mcp_servers_for_agent

        archimate_targets = mcp_servers_for_agent("archimate", dual_registry)
        # archimate-tools is auto-disabled in fake-plugin and has no
        # mcp_servers declaration in enterpower-architecture, so no MCP
        # routing.
        assert ("fake-plugin", "stub") not in archimate_targets

    def test_tree_agent_gets_stub_server_from_fake_rag_helper(self, dual_registry):
        """fake-rag-helper is enabled and routes to tree with mcp_servers=[stub]."""
        from aion.mcp.tool_bridge import mcp_servers_for_agent

        tree_targets = mcp_servers_for_agent("tree", dual_registry)
        assert ("fake-plugin", "stub") in tree_targets


# ---------------------------------------------------------------------------
# Hook firing — the manifest-driven path-referenced hooks.json


class TestPostToolUseHookFiring:
    def test_artifact_save_path_fires_log_write_hook(self, dual_registry, tmp_path, monkeypatch):
        """The fixture's hooks.json declares PostToolUse matcher 'Write'
        targeting log-write.sh. The hook writes the stdin JSON payload
        to $WRITE_LOG. We invoke ``fire_post_tool_use`` directly and
        verify the sentinel file gets written with the correct payload.
        """
        from aion.skills.hooks import fire_post_tool_use

        write_log = tmp_path / "hook-output.json"
        # log-write.sh reads $WRITE_LOG from env. Default hook env passes
        # through parent process env (minus secrets) so setting WRITE_LOG
        # here is sufficient.
        monkeypatch.setenv("WRITE_LOG", str(write_log))

        fire_post_tool_use("my-artifact.html", tool_name="Write")

        assert write_log.exists(), "hook did not write the sentinel file"
        payload = json.loads(write_log.read_text(encoding="utf-8"))
        assert payload == {
            "tool_name": "Write",
            "tool_input": {"file_path": "my-artifact.html"},
        }


# ---------------------------------------------------------------------------
# Bridged-tool registration against a real Pydantic AI agent


class TestBridgedToolsAttachToRealAgent:
    @pytest.mark.asyncio
    async def test_attach_bridged_tool_no_warning(self, dual_registry, caplog):
        """Combines fixture MCP discovery with the real-Pydantic-AI-agent
        integration verified at the unit level in commit 7's fixup.
        Discovers the stub server's tools end-to-end, attaches to a
        fresh Agent, asserts no silent-skip warning.
        """
        import logging
        from pydantic_ai import Agent
        from aion.mcp.tool_bridge import build_mcp_tools

        mgr = get_mcp_plugin_manager()
        mgr.register_plugin(dual_registry.get_plugin("fake-plugin"))

        try:
            tools = await build_mcp_tools("fake-plugin", "stub")
            assert len(tools) == 1
            assert tools[0]._mcp_tool_name == "echo"

            caplog.set_level(logging.WARNING, logger="aion.agents._mcp_inject")
            from aion.agents._mcp_inject import attach_mcp_tools
            agent: Agent = Agent("test")
            attach_mcp_tools(agent, tools)

            assert not any(
                "Failed to attach MCP tool" in r.message for r in caplog.records
            ), "Pydantic AI rejected the bridged echo tool"
        finally:
            await mgr.shutdown_all()
