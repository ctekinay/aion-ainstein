"""Tests for the MCP-to-Pydantic-AI tool bridge."""

from __future__ import annotations

import inspect
import json
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aion.mcp.tool_bridge import (
    _python_type_from_schema,
    build_mcp_tool_callable,
    build_mcp_tools,
    mcp_servers_for_agent,
)
from aion.skills.multi_registry import MultiPluginRegistry
from aion.skills.plugin import load_plugin_manifest


# ---------------------------------------------------------------------- type mapping


class TestPythonTypeFromSchema:
    @pytest.mark.parametrize("json_type,expected", [
        ("string", str),
        ("integer", int),
        ("number", float),
        ("boolean", bool),
        ("object", dict),
        ("array", list),
    ])
    def test_known_types(self, json_type, expected):
        assert _python_type_from_schema({"type": json_type}) is expected

    def test_unknown_type_falls_back_to_any(self):
        assert _python_type_from_schema({"type": "something-exotic"}) is Any

    def test_list_type_degrades_to_any(self):
        # "type": ["string", "null"] etc.
        assert _python_type_from_schema({"type": ["string", "null"]}) is Any

    def test_missing_type_falls_back_to_any(self):
        assert _python_type_from_schema({}) is Any


# ---------------------------------------------------------------------- single callable


class TestBuildMcpToolCallable:
    def test_signature_has_ctx_plus_keyword_only_params(self):
        async def fake_lookup(p, s):
            return None  # unused for signature check

        fn = build_mcp_tool_callable(
            plugin_name="demo",
            server_name="preview",
            tool_name="preview_start",
            description="Start preview",
            input_schema={
                "properties": {
                    "code": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["code"],
            },
            server_lookup=fake_lookup,
        )

        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        # First is ctx, rest are keyword-only.
        assert params[0].name == "ctx"
        kw = {p.name: p for p in params[1:]}
        assert "code" in kw and "title" in kw
        assert kw["code"].kind == inspect.Parameter.KEYWORD_ONLY
        assert kw["code"].default is inspect.Parameter.empty
        assert kw["title"].default is None  # optional

    def test_metadata_set_for_introspection(self):
        async def fake_lookup(p, s):
            return None

        fn = build_mcp_tool_callable(
            plugin_name="demo", server_name="preview", tool_name="preview_start",
            description="d", input_schema={}, server_lookup=fake_lookup,
        )
        assert fn.__name__ == "preview_preview_start"
        assert fn.__doc__ == "d"
        assert getattr(fn, "_is_mcp_bridged") is True
        assert getattr(fn, "_mcp_plugin") == "demo"
        assert getattr(fn, "_mcp_server") == "preview"
        assert getattr(fn, "_mcp_tool_name") == "preview_start"

    def test_dashes_in_names_become_underscores(self):
        async def fake_lookup(p, s):
            return None

        fn = build_mcp_tool_callable(
            plugin_name="x", server_name="my-server", tool_name="my-tool",
            description="d", input_schema={}, server_lookup=fake_lookup,
        )
        assert fn.__name__ == "my_server_my_tool"

    @pytest.mark.asyncio
    async def test_call_drops_none_optionals_and_dispatches_to_server(self):
        # Mock server with an async call_tool that records args.
        fake_server = SimpleNamespace(call_tool=AsyncMock(return_value="ok"))

        async def fake_lookup(plugin, server):
            assert (plugin, server) == ("demo", "preview")
            return fake_server

        fn = build_mcp_tool_callable(
            plugin_name="demo", server_name="preview", tool_name="preview_start",
            description="",
            input_schema={
                "properties": {
                    "code": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["code"],
            },
            server_lookup=fake_lookup,
        )

        # title omitted → default None → must not be sent to the server.
        result = await fn(ctx=None, code="VIEWS = {}")
        assert result == "ok"
        fake_server.call_tool.assert_awaited_once_with("preview_start", {"code": "VIEWS = {}"})

    @pytest.mark.asyncio
    async def test_call_includes_all_provided_kwargs(self):
        fake_server = SimpleNamespace(call_tool=AsyncMock(return_value="ok"))

        async def fake_lookup(p, s):
            return fake_server

        fn = build_mcp_tool_callable(
            plugin_name="demo", server_name="preview", tool_name="preview_start",
            description="",
            input_schema={"properties": {"code": {"type": "string"}, "title": {"type": "string"}}},
            server_lookup=fake_lookup,
        )
        await fn(ctx=None, code="X", title="My Title")
        fake_server.call_tool.assert_awaited_once_with("preview_start", {"code": "X", "title": "My Title"})


# ---------------------------------------------------------------------- build_mcp_tools


class TestBuildMcpTools:
    @pytest.mark.asyncio
    async def test_discovers_and_synthesizes_all_tools(self):
        fake_tools = [
            SimpleNamespace(
                name="preview_start",
                description="Start preview",
                inputSchema={"properties": {"code": {"type": "string"}}, "required": ["code"]},
            ),
            SimpleNamespace(
                name="preview_stop",
                description="Stop preview",
                inputSchema={},
            ),
        ]
        fake_server = SimpleNamespace(list_tools=AsyncMock(return_value=fake_tools))

        async def fake_lookup(p, s):
            return fake_server

        callables = await build_mcp_tools("demo", "preview", server_lookup=fake_lookup)
        names = [fn.__name__ for fn in callables]
        assert names == ["preview_preview_start", "preview_preview_stop"]

    @pytest.mark.asyncio
    async def test_skips_tools_with_no_name(self, caplog):
        fake_tools = [
            SimpleNamespace(name="", description="", inputSchema={}),
            SimpleNamespace(name="good", description="", inputSchema={}),
        ]
        fake_server = SimpleNamespace(list_tools=AsyncMock(return_value=fake_tools))

        async def fake_lookup(p, s):
            return fake_server

        callables = await build_mcp_tools("demo", "srv", server_lookup=fake_lookup)
        assert [fn.__name__ for fn in callables] == ["srv_good"]
        assert any("no name" in r.message for r in caplog.records)


# ---------------------------------------------------------------------- per-agent routing


def _make_plugin_with_skill(
    root: Path,
    plugin_name: str,
    skill_name: str,
    execution: str,
    mcp_servers: list[str],
) -> Path:
    plugin_dir = root / ".ainstein-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": plugin_name, "runtime": "ainstein", "version": "0.0.1"}),
        encoding="utf-8",
    )
    import yaml as _yaml
    (plugin_dir / "skills-registry.yaml").write_text(
        _yaml.safe_dump({
            "skills": [{
                "name": skill_name,
                "path": f"{skill_name}/SKILL.md",
                "description": "x",
                "enabled": True,
                "inject_mode": "on_demand",
                "execution": execution,
                "mcp_servers": mcp_servers,
            }],
        }, sort_keys=False),
        encoding="utf-8",
    )
    sdir = root / "skills" / skill_name
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "SKILL.md").write_text(
        textwrap.dedent(f"""\
        ---
        name: {skill_name}
        description: stub
        ---
        body
        """),
        encoding="utf-8",
    )
    return root


class TestMcpServersForAgent:
    def test_returns_only_servers_for_matching_execution(self, tmp_path):
        # archimate skill declares mcp_servers=[preview]; principle skill declares [other]
        a = _make_plugin_with_skill(
            tmp_path / "a", "plugin-a", "archimate-viewer", "archimate", ["preview"],
        )
        b = _make_plugin_with_skill(
            tmp_path / "b", "plugin-b", "principle-helper", "principle", ["other"],
        )

        multi = MultiPluginRegistry()
        multi.add_plugin_from_object(load_plugin_manifest(a))
        multi.add_plugin_from_object(load_plugin_manifest(b))
        multi.load()

        assert mcp_servers_for_agent("archimate", multi) == [("plugin-a", "preview")]
        assert mcp_servers_for_agent("principle", multi) == [("plugin-b", "other")]
        assert mcp_servers_for_agent("repo_analysis", multi) == []

    def test_dedupes_servers_across_skills(self, tmp_path):
        # Two skills route to the same agent and both declare the same server.
        plugin_dir = (tmp_path / "p" / ".ainstein-plugin")
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "p", "runtime": "ainstein", "version": "0.0.1"}),
            encoding="utf-8",
        )
        import yaml as _yaml
        (plugin_dir / "skills-registry.yaml").write_text(_yaml.safe_dump({
            "skills": [
                {
                    "name": "s1", "path": "s1/SKILL.md", "description": "x",
                    "enabled": True, "inject_mode": "on_demand",
                    "execution": "archimate", "mcp_servers": ["preview"],
                },
                {
                    "name": "s2", "path": "s2/SKILL.md", "description": "x",
                    "enabled": True, "inject_mode": "on_demand",
                    "execution": "archimate", "mcp_servers": ["preview"],
                },
            ],
        }, sort_keys=False), encoding="utf-8")
        for sname in ("s1", "s2"):
            sdir = tmp_path / "p" / "skills" / sname
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / "SKILL.md").write_text(
                f"---\nname: {sname}\ndescription: x\n---\nbody\n",
                encoding="utf-8",
            )

        multi = MultiPluginRegistry()
        multi.add_plugin_from_object(load_plugin_manifest(tmp_path / "p"))
        multi.load()
        assert mcp_servers_for_agent("archimate", multi) == [("p", "preview")]

    def test_disabled_skill_excluded(self, tmp_path):
        a = _make_plugin_with_skill(
            tmp_path / "a", "p", "viewer", "archimate", ["preview"],
        )
        # Patch enabled=False in the registry file before load.
        reg_path = a / ".ainstein-plugin" / "skills-registry.yaml"
        reg_text = reg_path.read_text(encoding="utf-8").replace(
            "enabled: true", "enabled: false",
        )
        reg_path.write_text(reg_text, encoding="utf-8")

        multi = MultiPluginRegistry()
        multi.add_plugin_from_object(load_plugin_manifest(a))
        multi.load()
        assert mcp_servers_for_agent("archimate", multi) == []

    def test_framework_skill_declaring_mcp_warns_and_ignores(self, tmp_path, caplog):
        # Skill with no execution (framework-level) that declares mcp_servers.
        plugin_dir = tmp_path / "p" / ".ainstein-plugin"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "p", "runtime": "ainstein", "version": "0.0.1"}),
            encoding="utf-8",
        )
        import yaml as _yaml
        (plugin_dir / "skills-registry.yaml").write_text(_yaml.safe_dump({
            "skills": [{
                "name": "framework", "path": "framework/SKILL.md",
                "description": "x", "enabled": True,
                "inject_mode": "always",  # always-loaded framework skill
                "execution": "",  # explicit empty = no agent dispatch
                "mcp_servers": ["preview"],
            }],
        }, sort_keys=False), encoding="utf-8")
        sdir = tmp_path / "p" / "skills" / "framework"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "SKILL.md").write_text(
            "---\nname: framework\ndescription: x\n---\nbody\n",
            encoding="utf-8",
        )

        multi = MultiPluginRegistry()
        multi.add_plugin_from_object(load_plugin_manifest(tmp_path / "p"))
        multi.load()
        result = mcp_servers_for_agent("archimate", multi)
        assert result == []
        assert any("framework-level skills" in r.message for r in caplog.records)
