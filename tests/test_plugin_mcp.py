"""Tests for MCPPluginManager — plugin .mcp.json parsing, lazy spawn, registration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aion.mcp.plugin_mcp import (
    MCPPluginManager,
    _reset_mcp_plugin_manager_for_tests,
    get_mcp_plugin_manager,
)
from aion.skills.plugin import Plugin, PluginManifest


def _stub_plugin(root: Path, name: str, mcp_config: dict | None = None) -> Plugin:
    plugin_dir = root / ".ainstein-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": name, "runtime": "ainstein", "version": "0.0.1"}),
        encoding="utf-8",
    )
    if mcp_config is not None:
        (root / ".mcp.json").write_text(json.dumps(mcp_config), encoding="utf-8")
    return Plugin(
        root=root,
        manifest=PluginManifest(name=name, runtime="ainstein", version="0.0.1"),
    )


@pytest.fixture(autouse=True)
def _isolate_manager_singleton():
    _reset_mcp_plugin_manager_for_tests()
    yield
    _reset_mcp_plugin_manager_for_tests()


class TestRegistration:
    def test_no_mcp_config_is_a_noop(self, tmp_path):
        plugin = _stub_plugin(tmp_path, "demo")
        mgr = MCPPluginManager()
        mgr.register_plugin(plugin)
        assert mgr.list_servers() == []

    def test_registers_declared_servers(self, tmp_path):
        plugin = _stub_plugin(tmp_path, "demo", mcp_config={
            "mcpServers": {
                "preview": {"command": "bash", "args": ["start.sh"]},
                "echo": {"command": "node", "args": ["echo.js"]},
            }
        })
        mgr = MCPPluginManager()
        mgr.register_plugin(plugin)
        assert set(mgr.list_servers()) == {("demo", "preview"), ("demo", "echo")}

    def test_substitutes_ainstein_plugin_root_in_args(self, tmp_path):
        plugin = _stub_plugin(tmp_path, "demo", mcp_config={
            "mcpServers": {
                "preview": {
                    "command": "bash",
                    "args": ["${AINSTEIN_PLUGIN_ROOT}/mcp/server/start.sh"],
                }
            }
        })
        mgr = MCPPluginManager()
        mgr.register_plugin(plugin)
        cfg = mgr._configs[("demo", "preview")]
        assert cfg["args"] == [f"{tmp_path}/mcp/server/start.sh"]

    def test_substitutes_ainstein_plugin_root_in_command_env_cwd(self, tmp_path):
        plugin = _stub_plugin(tmp_path, "demo", mcp_config={
            "mcpServers": {
                "s": {
                    "command": "${AINSTEIN_PLUGIN_ROOT}/bin/server",
                    "args": [],
                    "env": {"DATA_DIR": "${AINSTEIN_PLUGIN_ROOT}/data"},
                    "cwd": "${AINSTEIN_PLUGIN_ROOT}/working",
                }
            }
        })
        mgr = MCPPluginManager()
        mgr.register_plugin(plugin)
        cfg = mgr._configs[("demo", "s")]
        assert cfg["command"] == f"{tmp_path}/bin/server"
        assert cfg["env"] == {"DATA_DIR": f"{tmp_path}/data"}
        assert cfg["cwd"] == f"{tmp_path}/working"

    def test_default_cwd_is_plugin_root(self, tmp_path):
        plugin = _stub_plugin(tmp_path, "demo", mcp_config={
            "mcpServers": {"s": {"command": "bash"}}
        })
        mgr = MCPPluginManager()
        mgr.register_plugin(plugin)
        assert mgr._configs[("demo", "s")]["cwd"] == str(tmp_path)

    def test_malformed_json_is_logged_and_skipped(self, tmp_path, caplog):
        plugin = _stub_plugin(tmp_path, "demo")
        (tmp_path / ".mcp.json").write_text("not-json{", encoding="utf-8")
        mgr = MCPPluginManager()
        mgr.register_plugin(plugin)
        assert mgr.list_servers() == []
        assert any("invalid .mcp.json" in r.message for r in caplog.records)

    def test_missing_command_skips_server(self, tmp_path, caplog):
        plugin = _stub_plugin(tmp_path, "demo", mcp_config={
            "mcpServers": {
                "good": {"command": "bash"},
                "bad": {"args": ["no-command-here"]},
            }
        })
        mgr = MCPPluginManager()
        mgr.register_plugin(plugin)
        assert mgr.list_servers() == [("demo", "good")]
        assert any("missing/invalid 'command'" in r.message for r in caplog.records)


class TestLazySpawn:
    @pytest.mark.asyncio
    async def test_get_server_returns_lazy_started_instance(self, tmp_path, monkeypatch):
        plugin = _stub_plugin(tmp_path, "demo", mcp_config={
            "mcpServers": {"s": {"command": "bash"}}
        })
        mgr = MCPPluginManager()
        mgr.register_plugin(plugin)

        # Patch StdioServer to avoid spawning a real subprocess.
        from aion.mcp import plugin_mcp as pm
        start_calls = []

        class _FakeStdioServer:
            def __init__(self, command, args, env, cwd):
                self.command = command
                self.alive = False

            def is_alive(self):
                return self.alive

            async def start(self):
                start_calls.append(self.command)
                self.alive = True

            async def stop(self, suppress_errors=False):
                self.alive = False

        monkeypatch.setattr(pm, "StdioServer", _FakeStdioServer)

        # First call spawns.
        srv1 = await mgr.get_server("demo", "s")
        assert isinstance(srv1, _FakeStdioServer)
        assert start_calls == ["bash"]

        # Second call reuses the same instance.
        srv2 = await mgr.get_server("demo", "s")
        assert srv2 is srv1
        assert start_calls == ["bash"]  # not re-spawned

    @pytest.mark.asyncio
    async def test_get_server_respawns_dead_process(self, tmp_path, monkeypatch):
        plugin = _stub_plugin(tmp_path, "demo", mcp_config={
            "mcpServers": {"s": {"command": "bash"}}
        })
        mgr = MCPPluginManager()
        mgr.register_plugin(plugin)

        from aion.mcp import plugin_mcp as pm
        start_calls: list[int] = []

        class _FakeStdioServer:
            def __init__(self, command, args, env, cwd):
                self.alive = False

            def is_alive(self):
                return self.alive

            async def start(self):
                start_calls.append(1)
                self.alive = True

            async def stop(self, suppress_errors=False):
                self.alive = False

        monkeypatch.setattr(pm, "StdioServer", _FakeStdioServer)

        srv = await mgr.get_server("demo", "s")
        assert len(start_calls) == 1
        # Simulate process death.
        srv.alive = False
        await mgr.get_server("demo", "s")
        assert len(start_calls) == 2  # respawned

    @pytest.mark.asyncio
    async def test_get_server_unknown_raises_keyerror(self, tmp_path):
        plugin = _stub_plugin(tmp_path, "demo")
        mgr = MCPPluginManager()
        mgr.register_plugin(plugin)
        with pytest.raises(KeyError, match="not registered"):
            await mgr.get_server("demo", "nonexistent")

    @pytest.mark.asyncio
    async def test_concurrent_get_server_same_key_constructs_once(self, tmp_path, monkeypatch):
        """Race regression: two coroutines requesting the same (plugin, server)
        concurrently must share a single StdioServer instance — not each
        construct a fresh one and orphan a subprocess.

        Pre-fix, both coroutines would pass ``self._servers.get(key) is None``,
        both construct a StdioServer, both call ``start()``, and the second's
        assignment to ``self._servers[key]`` would overwrite the first
        without cleanup — leaking the first subprocess. The cross-agent
        routing path (one MCP server consumed by skills routing to two
        different agent types) makes this reachable from production startup.
        """
        plugin = _stub_plugin(tmp_path, "demo", mcp_config={
            "mcpServers": {"shared": {"command": "bash"}}
        })
        mgr = MCPPluginManager()
        mgr.register_plugin(plugin)

        from aion.mcp import plugin_mcp as pm
        import asyncio as _asyncio
        construct_count = 0

        class _CountingFakeStdioServer:
            def __init__(self, command, args, env, cwd):
                nonlocal construct_count
                construct_count += 1
                self.alive = False

            def is_alive(self):
                return self.alive

            async def start(self):
                # Small await to maximize the chance of interleaving.
                await _asyncio.sleep(0)
                self.alive = True

            async def stop(self, suppress_errors=False):
                self.alive = False

        monkeypatch.setattr(pm, "StdioServer", _CountingFakeStdioServer)

        srv1, srv2 = await _asyncio.gather(
            mgr.get_server("demo", "shared"),
            mgr.get_server("demo", "shared"),
        )

        assert srv1 is srv2, "concurrent get_server returned different instances"
        assert construct_count == 1, (
            f"expected exactly one StdioServer construction, got {construct_count}"
        )


class TestSingleton:
    def test_singleton_returns_same_instance(self):
        a = get_mcp_plugin_manager()
        b = get_mcp_plugin_manager()
        assert a is b
