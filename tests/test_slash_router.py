"""Tests for SlashRouter — parse, validate, fall-through to Persona."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from aion.skills.multi_registry import MultiPluginRegistry
from aion.skills.plugin import load_plugin_manifest
from aion.skills.slash_router import SlashCommand, SlashRouter


def _make_plugin(
    root: Path,
    name: str,
    skills: list[dict] | None = None,
) -> Path:
    plugin_dir = root / ".ainstein-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": name, "runtime": "ainstein", "version": "0.0.1"}),
        encoding="utf-8",
    )
    import yaml as _yaml
    (plugin_dir / "skills-registry.yaml").write_text(
        _yaml.safe_dump({"skills": skills or []}, sort_keys=False),
        encoding="utf-8",
    )
    skills_dir = root / "skills"
    skills_dir.mkdir(exist_ok=True)
    for s in (skills or []):
        sdir = skills_dir / s["name"]
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "SKILL.md").write_text(
            textwrap.dedent(f"""\
            ---
            name: {s["name"]}
            description: stub
            ---
            body
            """),
            encoding="utf-8",
        )
    return root


def _registry_with_invocable(tmp_path: Path, *names_with_tags: tuple[str, list[str]]) -> MultiPluginRegistry:
    """Make a registry with each (name, tags) skill as inject_mode=on_demand."""
    skills = [
        {
            "name": name,
            "path": f"{name}/SKILL.md",
            "description": "x",
            "enabled": True,
            "inject_mode": "on_demand",
            "tags": list(tags),
        }
        for name, tags in names_with_tags
    ]
    root = _make_plugin(tmp_path / "p", "demo", skills=skills)
    multi = MultiPluginRegistry()
    multi.add_plugin_from_object(load_plugin_manifest(root))
    multi.load()
    return multi


# ---------------------------------------------------------------------- parse


class TestParseRegex:
    def test_simple_command_no_args(self, tmp_path):
        multi = _registry_with_invocable(tmp_path, ("archimate-viewer", ["archimate"]))
        cmd = SlashRouter(multi).parse("/archimate-viewer")
        assert isinstance(cmd, SlashCommand)
        assert cmd.skill_name == "archimate-viewer"
        assert cmd.args == ""
        assert cmd.raw_message == "/archimate-viewer"

    def test_command_with_args(self, tmp_path):
        multi = _registry_with_invocable(tmp_path, ("archimate-tools", ["x"]))
        cmd = SlashRouter(multi).parse("/archimate-tools validate model.xml")
        assert cmd is not None
        assert cmd.skill_name == "archimate-tools"
        assert cmd.args == "validate model.xml"

    def test_command_with_trailing_whitespace(self, tmp_path):
        multi = _registry_with_invocable(tmp_path, ("foo", []))
        cmd = SlashRouter(multi).parse("/foo   ")
        assert cmd is not None
        assert cmd.skill_name == "foo"
        assert cmd.args == ""

    def test_args_with_internal_whitespace_preserved(self, tmp_path):
        multi = _registry_with_invocable(tmp_path, ("foo", []))
        cmd = SlashRouter(multi).parse("/foo  bar    baz  ")
        # Leading whitespace eaten by regex; internal kept.
        assert cmd is not None
        assert cmd.args == "bar    baz"


class TestParseRejection:
    def test_non_slash_message_returns_none(self, tmp_path):
        multi = _registry_with_invocable(tmp_path, ("archimate-viewer", []))
        assert SlashRouter(multi).parse("What ADRs exist?") is None
        assert SlashRouter(multi).parse("Hello there") is None

    def test_empty_message_returns_none(self, tmp_path):
        multi = _registry_with_invocable(tmp_path, ("foo", []))
        assert SlashRouter(multi).parse("") is None

    def test_uppercase_skill_name_rejected_by_regex(self, tmp_path):
        # Convention: lowercase identifiers only.
        multi = _registry_with_invocable(tmp_path, ("foo", []))
        assert SlashRouter(multi).parse("/FOO") is None

    def test_unknown_command_falls_through(self, tmp_path):
        """Returns None for unknown skill names — caller forwards to Persona."""
        multi = _registry_with_invocable(tmp_path, ("archimate-viewer", []))
        assert SlashRouter(multi).parse("/unknown-skill") is None

    def test_always_loaded_skill_not_invocable(self, tmp_path):
        """Framework skills (inject_mode=always) are not invocable per D3."""
        # ainstein-identity-style: always-loaded framework skill.
        skills = [{
            "name": "framework-skill",
            "path": "framework-skill/SKILL.md",
            "description": "x",
            "enabled": True,
            "inject_mode": "always",  # ← excluded from invocable_skills
            "tags": [],
        }]
        root = _make_plugin(tmp_path / "p", "demo", skills=skills)
        multi = MultiPluginRegistry()
        multi.add_plugin_from_object(load_plugin_manifest(root))
        multi.load()
        assert SlashRouter(multi).parse("/framework-skill") is None

    def test_disabled_skill_not_invocable(self, tmp_path):
        skills = [{
            "name": "viewer",
            "path": "viewer/SKILL.md",
            "description": "x",
            "enabled": False,
            "inject_mode": "on_demand",
            "tags": [],
        }]
        root = _make_plugin(tmp_path / "p", "demo", skills=skills)
        multi = MultiPluginRegistry()
        multi.add_plugin_from_object(load_plugin_manifest(root))
        multi.load()
        assert SlashRouter(multi).parse("/viewer") is None

    def test_non_string_message_returns_none(self, tmp_path):
        multi = _registry_with_invocable(tmp_path, ("foo", []))
        assert SlashRouter(multi).parse(None) is None  # type: ignore[arg-type]
        assert SlashRouter(multi).parse(123) is None  # type: ignore[arg-type]

    def test_path_like_message_rejected_unless_skill_exists(self, tmp_path):
        """/tmp/foo matches the regex (tmp = first capture). Falls through
        to Persona unless a 'tmp' skill is registered."""
        multi = _registry_with_invocable(tmp_path, ("real-skill", []))
        assert SlashRouter(multi).parse("/tmp/foo") is None


class TestParseWithMultiplePlugins:
    def test_finds_invocable_across_plugins(self, tmp_path):
        a = _make_plugin(tmp_path / "a", "plugin-a", skills=[{
            "name": "skill-a",
            "path": "skill-a/SKILL.md",
            "description": "x",
            "enabled": True,
            "inject_mode": "on_demand",
            "tags": ["a"],
        }])
        b = _make_plugin(tmp_path / "b", "plugin-b", skills=[{
            "name": "skill-b",
            "path": "skill-b/SKILL.md",
            "description": "x",
            "enabled": True,
            "inject_mode": "on_demand",
            "tags": ["b"],
        }])
        multi = MultiPluginRegistry()
        multi.add_plugin_from_object(load_plugin_manifest(a))
        multi.add_plugin_from_object(load_plugin_manifest(b))
        multi.load()

        router = SlashRouter(multi)
        assert router.parse("/skill-a") is not None
        assert router.parse("/skill-b") is not None
        assert router.parse("/skill-c") is None
