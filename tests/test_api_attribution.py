"""Tests for api.py attribution under skill-name collision.

Specifically guards against the find_plugin_for_skill first-match-wins
bug: when two plugins declare the same skill name, both list_plugins
and list_skills must attribute each entry to its correct owning plugin,
not collapse both into whichever plugin loads first.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml

from aion.skills.multi_registry import (
    MultiPluginRegistry,
    _reset_multi_registry_for_tests,
)
from aion.skills.plugin import load_plugin_manifest


def _make_plugin(
    root: Path,
    name: str,
    skills: list[dict],
) -> Path:
    plugin_dir = root / ".ainstein-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({
            "name": name,
            "runtime": "ainstein",
            "version": "0.1.0",
            "description": f"description for {name}",
            "author": {"name": "test"},
        }),
        encoding="utf-8",
    )
    (plugin_dir / "skills-registry.yaml").write_text(
        yaml.safe_dump({"skills": skills}, sort_keys=False),
        encoding="utf-8",
    )
    skills_dir = root / "skills"
    skills_dir.mkdir(exist_ok=True)
    for s in skills:
        sdir = skills_dir / s["name"]
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "SKILL.md").write_text(
            textwrap.dedent(f"""\
            ---
            name: {s["name"]}
            description: {s.get("description", "stub")}
            ---
            body
            """),
            encoding="utf-8",
        )
    return root


def _install_two_plugin_collision(tmp_path: Path) -> MultiPluginRegistry:
    """Two SYNTHETIC tmp_path plugins (not the real bundled set) both
    declare 'shared'. `legacy-domain` is a generic stand-in for a shadowed
    legacy provider; it declares conflicts_with so load succeeds, the
    authoritative provider wins on owner, `legacy-domain` is shadowed.
    This is a generic api.py attribution unit test, not a test of the
    real ainstein-core→enterpower supersession."""
    _reset_multi_registry_for_tests()
    ep = _make_plugin(tmp_path / "ep", "enterpower-architecture", skills=[
        {"name": "shared", "path": "shared/SKILL.md", "description": "ep version"},
        {"name": "ep-only", "path": "ep-only/SKILL.md", "description": "only in ep"},
    ])
    core = _make_plugin(tmp_path / "core", "legacy-domain", skills=[
        {
            "name": "shared",
            "path": "shared/SKILL.md",
            "description": "core version",
            "conflicts_with": ["enterpower-architecture/shared"],
        },
        {"name": "core-only", "path": "core-only/SKILL.md", "description": "only in core"},
    ])
    multi = MultiPluginRegistry()
    multi.add_plugin_from_object(load_plugin_manifest(ep))
    multi.add_plugin_from_object(load_plugin_manifest(core))
    multi.load()

    # Install as the process-wide singleton so api.py's module-level
    # _registry reference resolves to our test instance.
    import aion.skills.multi_registry as mr
    mr._global_multi = multi
    return multi


class TestListSkillsCollisionAttribution:
    def test_list_skills_returns_one_entry_per_plugin_for_shared_name(self, tmp_path):
        _install_two_plugin_collision(tmp_path)
        from aion.skills.api import list_skills

        rows = list_skills()
        shared_rows = [r for r in rows if r["name"] == "shared"]
        assert len(shared_rows) == 2, (
            "expected one 'shared' row per declaring plugin, "
            "got {} rows: {}".format(len(shared_rows), [r["plugin"] for r in shared_rows])
        )
        plugins_seen = {r["plugin"] for r in shared_rows}
        assert plugins_seen == {"enterpower-architecture", "legacy-domain"}

    def test_list_skills_plugin_field_is_correct_per_entry(self, tmp_path):
        _install_two_plugin_collision(tmp_path)
        from aion.skills.api import list_skills

        rows = list_skills()
        # Each plugin contributes exactly the skills it declared.
        ep_rows = [r["name"] for r in rows if r["plugin"] == "enterpower-architecture"]
        core_rows = [r["name"] for r in rows if r["plugin"] == "legacy-domain"]
        assert sorted(ep_rows) == ["ep-only", "shared"]
        assert sorted(core_rows) == ["core-only", "shared"]

    def test_list_skills_enabled_flags_reflect_per_plugin_state(self, tmp_path):
        _install_two_plugin_collision(tmp_path)
        from aion.skills.api import list_skills

        rows = list_skills()
        # ep's shared is enabled (it wins); core's shared is auto-disabled
        # by conflicts_with.
        for r in rows:
            if r["plugin"] == "enterpower-architecture" and r["name"] == "shared":
                assert r["enabled"] is True
            if r["plugin"] == "legacy-domain" and r["name"] == "shared":
                assert r["enabled"] is False


class TestListPluginsCollisionAttribution:
    def test_skill_counts_per_plugin_are_correct_under_collision(self, tmp_path):
        _install_two_plugin_collision(tmp_path)
        from aion.skills.api import list_plugins

        plugins = list_plugins()
        by_name = {p["name"]: p for p in plugins}

        # Each plugin declared 2 skills (one shared, one unique).
        assert by_name["enterpower-architecture"]["skill_count"] == 2
        assert by_name["legacy-domain"]["skill_count"] == 2

    def test_enabled_counts_reflect_conflicts_with_auto_disable(self, tmp_path):
        _install_two_plugin_collision(tmp_path)
        from aion.skills.api import list_plugins

        plugins = list_plugins()
        by_name = {p["name"]: p for p in plugins}

        # ep: both skills enabled (no conflict declared on its side).
        assert by_name["enterpower-architecture"]["enabled_count"] == 2
        # core: 'shared' auto-disabled by conflicts_with; 'core-only' still enabled.
        assert by_name["legacy-domain"]["enabled_count"] == 1

    def test_manifest_metadata_attributed_to_correct_plugin(self, tmp_path):
        _install_two_plugin_collision(tmp_path)
        from aion.skills.api import list_plugins

        plugins = list_plugins()
        by_name = {p["name"]: p for p in plugins}
        # description was set distinctly per plugin in _make_plugin.
        assert by_name["enterpower-architecture"]["description"] == "description for enterpower-architecture"
        assert by_name["legacy-domain"]["description"] == "description for legacy-domain"


class TestToggleSkillEnabledInPluginUnderCollision:
    """The documented re-enable-a-shadowed-skill flow MUST reach the
    DuplicateSkillError preflight, not be silently rejected with HTTP 404.
    Pre-fix, find_plugin_for_skill returned the wrong plugin, the api
    function raised ValueError, and the dup-check was unreachable.
    """

    def test_re_enable_shadowed_skill_raises_duplicate_skill_error(self, tmp_path):
        _install_two_plugin_collision(tmp_path)
        from aion.skills.api import toggle_skill_enabled_in_plugin
        from aion.skills.multi_registry import DuplicateSkillError

        # legacy-domain's 'shared' is currently auto-disabled. User clicks
        # "re-enable" on the legacy-domain row. The plugin-scoped route MUST
        # reach the preflight and raise — not return a wrong-plugin 404.
        with pytest.raises(DuplicateSkillError, match="would conflict"):
            toggle_skill_enabled_in_plugin("legacy-domain", "shared", True)

    def test_disable_active_copy_succeeds(self, tmp_path):
        _install_two_plugin_collision(tmp_path)
        from aion.skills.api import toggle_skill_enabled_in_plugin

        # Disable enterpower's active 'shared'.
        result = toggle_skill_enabled_in_plugin("enterpower-architecture", "shared", False)
        assert result["success"] is True
        assert result["plugin"] == "enterpower-architecture"
        assert result["skill"] == "shared"
        assert result["enabled"] is False

    def test_wrong_plugin_raises_value_error(self, tmp_path):
        _install_two_plugin_collision(tmp_path)
        from aion.skills.api import toggle_skill_enabled_in_plugin

        # ep-only doesn't exist in legacy-domain.
        with pytest.raises(ValueError, match="does not define skill"):
            toggle_skill_enabled_in_plugin("legacy-domain", "ep-only", True)
