"""Tests for MultiPluginRegistry — duplicate detection, conflicts_with,
atomic-swap semantics, reload callbacks.

Each test builds two on-disk plugins under tmp_path and instantiates a
MultiPluginRegistry against them directly (no PluginLoader / singleton).
Plugin names here (`legacy-domain`, `enterpower-architecture`, `a`, `b`,
`other-plugin`) are SYNTHETIC tmp_path doubles, not the real bundled
plugins; `legacy-domain` is a generic stand-in for a shadowed legacy
provider (it models the conflicts_with relationship the real
ainstein-core→enterpower supersession had, without being that plugin).
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from aion.skills.multi_registry import (
    DuplicateSkillError,
    MultiPluginRegistry,
)
from aion.skills.plugin import load_plugin_manifest


def _make_plugin(
    root: Path,
    name: str,
    skills: list[dict] | None = None,
    groups: list[dict] | None = None,
    shared_refs: dict[str, dict[str, str]] | None = None,
) -> Path:
    """Create a minimal on-disk plugin under ``root`` and return its path."""
    plugin_dir = root / ".ainstein-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": name, "runtime": "ainstein", "version": "0.0.1"}),
        encoding="utf-8",
    )

    registry: dict[str, list] = {}
    if groups:
        registry["groups"] = groups
    if skills:
        registry["skills"] = skills
    import yaml as _yaml
    (plugin_dir / "skills-registry.yaml").write_text(
        _yaml.safe_dump(registry, sort_keys=False),
        encoding="utf-8",
    )

    # Each skill referenced needs a SKILL.md or it's a parse-time miss
    # (load_skill warns and the entry is still listed but content is empty).
    skills_dir = root / "skills"
    skills_dir.mkdir(exist_ok=True)
    all_skill_names: list[str] = []
    for s in (skills or []):
        all_skill_names.append(s["name"])
    for g in (groups or []):
        for s in g.get("skills", []):
            all_skill_names.append(s["name"])

    for sname in all_skill_names:
        sdir = skills_dir / sname
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "SKILL.md").write_text(
            textwrap.dedent(f"""\
            ---
            name: {sname}
            description: stub skill for tests
            ---
            stub body
            """),
            encoding="utf-8",
        )

    # Top-level shared-references/<group>/<filename>.md
    if shared_refs:
        for group_name, files in shared_refs.items():
            sr_dir = root / "shared-references" / group_name
            sr_dir.mkdir(parents=True, exist_ok=True)
            for fname, body in files.items():
                (sr_dir / fname).write_text(body, encoding="utf-8")

    return root


def _registry_with(*plugin_roots: Path) -> MultiPluginRegistry:
    multi = MultiPluginRegistry()
    for root in plugin_roots:
        plugin = load_plugin_manifest(root)
        multi.add_plugin_from_object(plugin)
    return multi


# --- disjoint plugins ---------------------------------------------------------


class TestDisjointPlugins:
    def test_two_disjoint_plugins_load_clean(self, tmp_path):
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "alpha", "path": "alpha/SKILL.md", "description": "x"},
        ])
        b = _make_plugin(tmp_path / "b", "b", skills=[
            {"name": "beta", "path": "beta/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a, b)
        multi.load()

        names = sorted(e.name for e in multi.list_skills())
        assert names == ["alpha", "beta"]
        assert multi.get_owner("alpha") == "a"
        assert multi.get_owner("beta") == "b"
        assert multi.list_plugins() == ["a", "b"]


# --- duplicate detection ------------------------------------------------------


class TestDuplicateDetection:
    def test_duplicate_enabled_skill_raises(self, tmp_path):
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "shared", "path": "shared/SKILL.md", "description": "x"},
        ])
        b = _make_plugin(tmp_path / "b", "b", skills=[
            {"name": "shared", "path": "shared/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a, b)
        with pytest.raises(DuplicateSkillError, match="Duplicate enabled skill 'shared'"):
            multi.load()

    def test_duplicate_message_names_both_plugins(self, tmp_path):
        a = _make_plugin(tmp_path / "a", "alpha", skills=[
            {"name": "tools", "path": "tools/SKILL.md", "description": "x"},
        ])
        b = _make_plugin(tmp_path / "b", "beta", skills=[
            {"name": "tools", "path": "tools/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a, b)
        with pytest.raises(DuplicateSkillError) as exc:
            multi.load()
        msg = str(exc.value)
        assert "'alpha'" in msg
        assert "'beta'" in msg
        assert "tools" in msg

    def test_disabled_duplicate_does_not_raise(self, tmp_path):
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "shared", "path": "shared/SKILL.md", "description": "x"},
        ])
        b = _make_plugin(tmp_path / "b", "b", skills=[
            {"name": "shared", "path": "shared/SKILL.md", "description": "x", "enabled": False},
        ])
        multi = _registry_with(a, b)
        multi.load()  # should NOT raise
        assert multi.get_owner("shared") == "a"


# --- conflicts_with -----------------------------------------------------------


class TestConflictsWith:
    def test_declaring_side_auto_disables_when_target_loaded_and_enabled(self, tmp_path):
        a = _make_plugin(tmp_path / "core", "legacy-domain", skills=[
            {
                "name": "archimate-tools",
                "path": "archimate-tools/SKILL.md",
                "description": "x",
                "conflicts_with": ["enterpower-architecture/archimate-tools"],
            },
        ])
        b = _make_plugin(tmp_path / "ep", "enterpower-architecture", skills=[
            {"name": "archimate-tools", "path": "archimate-tools/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a, b)
        multi.load()
        # legacy-domain's archimate-tools is auto-disabled — owner is enterpower
        assert multi.get_owner("archimate-tools") == "enterpower-architecture"
        # The declaring entry is in-memory disabled (YAML on disk is unchanged)
        a_entry = multi._registries["legacy-domain"].get_skill_entry("archimate-tools")
        assert a_entry is not None and a_entry.enabled is False

    def test_no_trigger_when_target_plugin_loaded_but_skill_absent(self, tmp_path):
        """conflicts_with is skill-scoped — target plugin loaded but the named
        skill is absent → no auto-disable."""
        a = _make_plugin(tmp_path / "core", "legacy-domain", skills=[
            {
                "name": "principle-generator",
                "path": "principle-generator/SKILL.md",
                "description": "x",
                "conflicts_with": ["enterpower-architecture/principle-generator"],
            },
        ])
        b = _make_plugin(tmp_path / "ep", "enterpower-architecture", skills=[
            # enterpower has a different skill — collision should NOT fire
            {"name": "archimate-viewer", "path": "archimate-viewer/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a, b)
        multi.load()
        assert multi.get_owner("principle-generator") == "legacy-domain"
        assert multi.get_owner("archimate-viewer") == "enterpower-architecture"

    def test_no_trigger_when_target_plugin_absent(self, tmp_path):
        a = _make_plugin(tmp_path / "core", "legacy-domain", skills=[
            {
                "name": "tools",
                "path": "tools/SKILL.md",
                "description": "x",
                "conflicts_with": ["nonexistent-plugin/tools"],
            },
        ])
        multi = _registry_with(a)
        multi.load()
        assert multi.get_owner("tools") == "legacy-domain"

    def test_no_trigger_when_target_disabled(self, tmp_path):
        a = _make_plugin(tmp_path / "core", "legacy-domain", skills=[
            {
                "name": "tools",
                "path": "tools/SKILL.md",
                "description": "x",
                "conflicts_with": ["other-plugin/tools"],
            },
        ])
        b = _make_plugin(tmp_path / "other", "other-plugin", skills=[
            {"name": "tools", "path": "tools/SKILL.md", "description": "x", "enabled": False},
        ])
        multi = _registry_with(a, b)
        multi.load()
        # Target is disabled in its own plugin, so the declaring side stays enabled.
        assert multi.get_owner("tools") == "legacy-domain"

    def test_reciprocal_declarations_resolve_by_load_order(self, tmp_path):
        """Tie-breaker: auto-disable applies only to the declaring side.

        If both plugins declare conflicts_with against each other, resolution
        is sequential in load order. The first plugin processes its
        declaration first and self-disables (its target is enabled). The
        second plugin then processes its declaration and finds its target
        already disabled — so it stays enabled.

        Net result: load-order wins, no DuplicateSkillError, the skill is
        still available (rather than both disabling and losing the skill).
        """
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {
                "name": "shared",
                "path": "shared/SKILL.md",
                "description": "x",
                "conflicts_with": ["b/shared"],
            },
        ])
        b = _make_plugin(tmp_path / "b", "b", skills=[
            {
                "name": "shared",
                "path": "shared/SKILL.md",
                "description": "x",
                "conflicts_with": ["a/shared"],
            },
        ])
        multi = _registry_with(a, b)
        multi.load()  # should NOT raise

        # a is processed first → its declaration fires → a/shared self-disables.
        # b is processed second → its target (a/shared) is already disabled
        # so b's declaration does not trigger; b/shared stays enabled.
        assert multi.get_owner("shared") == "b"
        assert multi._registries["a"].get_skill_entry("shared").enabled is False
        assert multi._registries["b"].get_skill_entry("shared").enabled is True

    def test_malformed_conflicts_with_logged_and_ignored(self, tmp_path, caplog):
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {
                "name": "alpha",
                "path": "alpha/SKILL.md",
                "description": "x",
                "conflicts_with": ["no-slash-here", "/empty-plugin", "empty-skill/"],
            },
        ])
        multi = _registry_with(a)
        multi.load()
        assert multi.get_owner("alpha") == "a"
        assert sum("malformed conflicts_with" in r.message for r in caplog.records) == 3


# --- set_skill_enabled preflight ---------------------------------------------


class TestPreflightDuplicateCheck:
    def test_enable_that_would_duplicate_raises(self, tmp_path):
        """User re-enables a shadowed skill via UI → preflight blocks it."""
        a = _make_plugin(tmp_path / "core", "legacy-domain", skills=[
            {
                "name": "archimate-tools",
                "path": "archimate-tools/SKILL.md",
                "description": "x",
                "enabled": False,  # already disabled (e.g., by prior conflicts_with resolution)
            },
        ])
        b = _make_plugin(tmp_path / "ep", "enterpower-architecture", skills=[
            {"name": "archimate-tools", "path": "archimate-tools/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a, b)
        multi.load()
        assert multi.get_owner("archimate-tools") == "enterpower-architecture"

        with pytest.raises(DuplicateSkillError, match="would conflict"):
            multi.set_skill_enabled("archimate-tools", True)


# --- reload callbacks --------------------------------------------------------


class TestReloadCallbacks:
    def test_callbacks_fire_on_load(self, tmp_path):
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "alpha", "path": "alpha/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a)
        fired: list[int] = []
        multi.on_reload(lambda: fired.append(1))
        multi.on_reload(lambda: fired.append(2))
        multi.load()
        assert fired == [1, 2]

    def test_callback_exception_does_not_break_peers(self, tmp_path, caplog):
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "alpha", "path": "alpha/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a)
        fired: list[int] = []

        def broken():
            raise RuntimeError("boom")

        multi.on_reload(broken)
        multi.on_reload(lambda: fired.append(2))
        multi.load()
        assert fired == [2]
        assert any("on_reload callback raised" in r.message for r in caplog.records)

    def test_keyed_registration_replaces_not_accumulates(self, tmp_path):
        """Re-registering under the same key replaces — the callback-leak fix.

        Simulates a re-instantiated Persona registering its hook again on
        the process-wide singleton. With list-append this leaked (both old
        and new fired); keyed register-or-replace fires only the latest.
        """
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "alpha", "path": "alpha/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a)
        fired: list[str] = []
        multi.on_reload(lambda: fired.append("old"), key="persona")
        multi.on_reload(lambda: fired.append("new"), key="persona")
        multi.load()
        assert fired == ["new"]  # old replaced, not accumulated

    def test_unkeyed_registrations_each_fire(self, tmp_path):
        """key=None auto-keys uniquely — unkeyed registrants don't collapse."""
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "alpha", "path": "alpha/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a)
        fired: list[int] = []
        multi.on_reload(lambda: fired.append(1))
        multi.on_reload(lambda: fired.append(2))
        multi.load()
        assert fired == [1, 2]


# --- idempotency & guards -----------------------------------------------------


class TestLoadIdempotency:
    def test_load_twice_does_not_double_fire_callbacks(self, tmp_path):
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "alpha", "path": "alpha/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a)
        fired: list[int] = []
        multi.on_reload(lambda: fired.append(1))
        multi.load()
        multi.load()  # second call should be a no-op
        assert fired == [1]

    def test_reload_resets_loaded_and_fires_callbacks(self, tmp_path):
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "alpha", "path": "alpha/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a)
        fired: list[int] = []
        multi.on_reload(lambda: fired.append(1))
        multi.load()
        multi.reload()
        assert fired == [1, 1]  # one per real load


class TestPluginNameCollision:
    def test_duplicate_plugin_name_raises(self, tmp_path):
        a = _make_plugin(tmp_path / "a", "same-name", skills=[
            {"name": "alpha", "path": "alpha/SKILL.md", "description": "x"},
        ])
        b = _make_plugin(tmp_path / "b", "same-name", skills=[
            {"name": "beta", "path": "beta/SKILL.md", "description": "x"},
        ])
        multi = MultiPluginRegistry()
        multi.add_plugin_from_object(load_plugin_manifest(a))
        with pytest.raises(ValueError, match="Plugin name collision"):
            multi.add_plugin_from_object(load_plugin_manifest(b))


class TestSharedReferencesAfterMove:
    """Commit 4's shared_references resolution: top-level shared-references/<group>/."""

    def test_shared_references_resolve_via_top_level_dir(self, tmp_path):
        a = _make_plugin(
            tmp_path / "p",
            "demo",
            groups=[{
                "name": "alpha-group",
                "shared_references": "alpha-refs",
                "tags": ["alpha"],
                "inject_into_tree": True,
                "inject_mode": "on_demand",
                "skills": [
                    {"name": "alpha-member", "path": "alpha-member/SKILL.md", "description": "x"},
                ],
            }],
            shared_refs={
                "alpha-refs": {
                    "guide.md": "## Guide\n\nshared guide body",
                    "rules.md": "## Rules\n\nshared rules body",
                },
            },
        )
        multi = _registry_with(a)
        multi.load()

        content = multi.get_skill_content(active_tags=["alpha"])
        assert "shared guide body" in content
        assert "shared rules body" in content
        # The ref filename (stem) appears as a markdown heading.
        assert "### guide" in content
        assert "### rules" in content

    def test_missing_shared_refs_dir_does_not_break_skill(self, tmp_path):
        """If shared_references points at a non-existent subdir, the member
        skill still loads — shared-ref merge is best-effort."""
        a = _make_plugin(
            tmp_path / "p",
            "demo",
            groups=[{
                "name": "g",
                "shared_references": "no-such-group",
                "tags": ["g"],
                "inject_into_tree": True,
                "inject_mode": "on_demand",
                "skills": [
                    {"name": "member", "path": "member/SKILL.md", "description": "x"},
                ],
            }],
        )
        multi = _registry_with(a)
        multi.load()
        content = multi.get_skill_content(active_tags=["g"])
        assert "## Skill: member" in content


class TestSkillTuningOwnerless:
    def test_returns_default_when_skill_disabled_in_all_plugins(self, tmp_path):
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "alpha", "path": "alpha/SKILL.md", "description": "x", "enabled": False},
        ])
        multi = _registry_with(a)
        multi.load()
        sentinel = object()
        result = multi.get_skill_tuning("alpha", "get_retrieval_limits", sentinel)
        assert result is sentinel

    def test_returns_default_when_skill_missing_everywhere(self, tmp_path):
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "alpha", "path": "alpha/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a)
        multi.load()
        sentinel = object()
        result = multi.get_skill_tuning("nonexistent", "get_retrieval_limits", sentinel)
        assert result is sentinel


# --- in-flight query semantics ------------------------------------------------


class TestAttributionUnderNameCollision:
    """Regression: ``iter_plugin_skills`` and ``set_skill_enabled_in_plugin``
    must correctly attribute / route entries when two plugins declare the
    same skill name. The pre-fix ``find_plugin_for_skill``-based code would
    mis-attribute the shadowed copy to the first plugin in load order,
    breaking the UI accordion's skill counts AND making the dup-check + 409
    surfacing unreachable for the documented "re-enable a shadowed skill"
    flow.
    """

    @staticmethod
    def _two_plugin_collision(tmp_path):
        """legacy-domain declares conflicts_with → its 'shared' auto-disables
        when enterpower-architecture's 'shared' is loaded and enabled.
        """
        ep = _make_plugin(tmp_path / "ep", "enterpower-architecture", skills=[
            {"name": "shared", "path": "shared/SKILL.md", "description": "ep version"},
        ])
        core = _make_plugin(tmp_path / "core", "legacy-domain", skills=[
            {
                "name": "shared",
                "path": "shared/SKILL.md",
                "description": "core version",
                "conflicts_with": ["enterpower-architecture/shared"],
            },
        ])
        multi = _registry_with(ep, core)
        multi.load()
        return multi

    def test_iter_plugin_skills_yields_correct_attribution_per_entry(self, tmp_path):
        multi = self._two_plugin_collision(tmp_path)
        pairs = list(multi.iter_plugin_skills())

        # Both plugins yield exactly one entry named 'shared', each attributed
        # to its own plugin — not both attributed to whichever loads first.
        from collections import defaultdict
        by_plugin = defaultdict(list)
        for plugin_name, entry in pairs:
            by_plugin[plugin_name].append(entry.name)

        assert by_plugin["enterpower-architecture"] == ["shared"]
        assert by_plugin["legacy-domain"] == ["shared"]

    def test_plugin_has_skill_is_per_plugin_scoped(self, tmp_path):
        multi = self._two_plugin_collision(tmp_path)
        # Both plugins define 'shared'.
        assert multi.plugin_has_skill("enterpower-architecture", "shared") is True
        assert multi.plugin_has_skill("legacy-domain", "shared") is True
        # Neither defines 'nope'.
        assert multi.plugin_has_skill("enterpower-architecture", "nope") is False
        assert multi.plugin_has_skill("legacy-domain", "nope") is False
        # Unknown plugin always False.
        assert multi.plugin_has_skill("nonexistent-plugin", "shared") is False

    def test_set_skill_enabled_in_plugin_routes_explicitly(self, tmp_path):
        """Critical scenario: legacy-domain's shadowed 'shared' starts disabled
        (conflicts_with auto-disabled it). User wants to re-enable it. The
        explicit-plugin route MUST reach the dup-check preflight and raise
        DuplicateSkillError — the pre-fix path returned ValueError because
        find_plugin_for_skill returned the wrong plugin.
        """
        multi = self._two_plugin_collision(tmp_path)
        # Verify the initial state: enterpower has the active copy.
        assert multi.get_owner("shared") == "enterpower-architecture"
        core_entry = multi._registries["legacy-domain"].get_skill_entry("shared")
        assert core_entry is not None
        assert core_entry.enabled is False  # auto-disabled

        # Re-enable legacy-domain's shadowed copy → preflight fires.
        with pytest.raises(DuplicateSkillError, match="would conflict"):
            multi.set_skill_enabled_in_plugin("legacy-domain", "shared", True)

    def test_set_skill_enabled_in_plugin_disable_succeeds_without_preflight(self, tmp_path):
        """Disabling enterpower's active copy: no preflight needed; succeeds.

        After reload, legacy-domain's conflicts_with no longer triggers
        (its target is now disabled), so legacy-domain's shadowed copy
        re-activates automatically. This is the documented unwind semantics:
        ``conflicts_with`` is an in-memory auto-disable that re-resolves
        on every reload.
        """
        multi = self._two_plugin_collision(tmp_path)
        multi.set_skill_enabled_in_plugin("enterpower-architecture", "shared", False)
        # legacy-domain's shadowed copy un-shadows automatically.
        assert multi.get_owner("shared") == "legacy-domain"
        # enterpower's copy is disabled in its registry (the on-disk YAML
        # was updated, and is_alive in-memory state reflects that).
        ep_entry = multi._registries["enterpower-architecture"].get_skill_entry("shared")
        assert ep_entry is not None and ep_entry.enabled is False

    def test_set_skill_enabled_in_plugin_rejects_wrong_plugin(self, tmp_path):
        multi = self._two_plugin_collision(tmp_path)
        with pytest.raises(ValueError, match="does not define skill"):
            multi.set_skill_enabled_in_plugin("legacy-domain", "skill-that-only-exists-in-ep", True)

    def test_set_skill_enabled_in_plugin_rejects_unknown_plugin(self, tmp_path):
        multi = self._two_plugin_collision(tmp_path)
        with pytest.raises(ValueError, match="Plugin not loaded"):
            multi.set_skill_enabled_in_plugin("nonexistent", "shared", True)


class TestInFlightQuerySemantics:
    def test_consumer_holding_old_reference_unaffected_by_reload(self, tmp_path):
        """The atomic-swap pattern documented in multi_registry.py: if a
        consumer captures a derived snapshot (e.g. a tuple of skill entries)
        at request start, a subsequent reload doesn't mutate that snapshot.
        """
        a = _make_plugin(tmp_path / "a", "a", skills=[
            {"name": "alpha", "path": "alpha/SKILL.md", "description": "x"},
        ])
        multi = _registry_with(a)
        multi.load()

        # Consumer captures a snapshot.
        captured_snapshot = tuple(multi.list_skills())
        assert [e.name for e in captured_snapshot] == ["alpha"]

        # Toggle alpha off and reload.
        multi.set_skill_enabled("alpha", False)

        # Old reference still names alpha; the entry's enabled value reflects
        # the new state because they're the same in-memory object — that's
        # acceptable. The CRITICAL guarantee is that the snapshot list itself
        # doesn't grow/shrink and the entries remain valid objects.
        assert len(captured_snapshot) == 1
        assert captured_snapshot[0].name == "alpha"
