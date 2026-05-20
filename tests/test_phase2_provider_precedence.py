"""Phase 2b — capability-scoped provider-precedence resolver + named
contribution accessors.

The mandated positive control (plan Phase-2 gate): two providers for ONE
capability, precedence decides the winner, AND reordering discovery does
NOT change the winner. An assert-not-load-order-dependent test is vacuous
without the control proving load order could otherwise have decided it,
so both directions are asserted in the same scenarios.

Inertness control: when NO skill declares `capability`, the legacy
conflicts_with path must behave byte-identically (Phase-0 goldens are the
real cross-phase guard; here it is asserted directly on a synthetic case).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from aion.skills.multi_registry import (
    DuplicateSkillError,
    MultiPluginRegistry,
)
from aion.skills.plugin import load_plugin_manifest


def _mk(root: Path, name: str, skills: list[dict], role: str = "domain") -> Path:
    """Minimal on-disk plugin; each skill gets a stub SKILL.md."""
    d = root / ".ainstein-plugin"
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.json").write_text(
        json.dumps({"name": name, "runtime": "ainstein", "role": role}),
        encoding="utf-8",
    )
    (d / "skills-registry.yaml").write_text(
        yaml.safe_dump({"skills": skills}, sort_keys=False), encoding="utf-8"
    )
    sd = root / "skills"
    for s in skills:
        skd = sd / s["name"]
        skd.mkdir(parents=True, exist_ok=True)
        (skd / "SKILL.md").write_text(
            f"---\nname: {s['name']}\ndescription: {s.get('description','x')}\n---\nbody\n",
            encoding="utf-8",
        )
    return root


def _reg(*roots: Path) -> MultiPluginRegistry:
    m = MultiPluginRegistry()
    for r in roots:
        m.add_plugin_from_object(load_plugin_manifest(r))
    return m


CAP = "architecture.archimate.generation"


class TestProviderPrecedencePositiveControl:
    def test_higher_precedence_wins_and_loser_disabled(self, tmp_path):
        a = _mk(tmp_path / "a", "plug-a", [{
            "name": "gen-a", "path": "gen-a/SKILL.md", "description": "A",
            "capability": CAP, "provider_precedence": 50,
        }])
        b = _mk(tmp_path / "b", "plug-b", [{
            "name": "gen-b", "path": "gen-b/SKILL.md", "description": "B",
            "capability": CAP, "provider_precedence": 100,
        }])
        m = _reg(a, b)
        m.load()
        by = {e.name: e for e in m.list_skills()}
        assert by["gen-b"].enabled is True, "higher precedence (100) must win"
        assert by["gen-a"].enabled is False, "lower precedence (50) must lose"
        assert m.get_owner("gen-b") == "plug-b"
        assert m.get_owner("gen-a") is None  # disabled → not in owner map

    def test_winner_is_precedence_not_discovery_order(self, tmp_path):
        """THE control: same providers, REVERSED add order — winner must
        not change. Without this, the test above could pass for the wrong
        reason (load order, not precedence)."""
        def build(order):
            a = _mk(tmp_path / f"a{order}", f"pa{order}", [{
                "name": "gen-a", "path": "gen-a/SKILL.md", "description": "A",
                "capability": CAP, "provider_precedence": 50,
            }])
            b = _mk(tmp_path / f"b{order}", f"pb{order}", [{
                "name": "gen-b", "path": "gen-b/SKILL.md", "description": "B",
                "capability": CAP, "provider_precedence": 100,
            }])
            return a, b

        a1, b1 = build("fwd")
        m1 = _reg(a1, b1)          # a then b
        m1.load()
        a2, b2 = build("rev")
        m2 = _reg(b2, a2)          # b then a — reversed discovery
        m2.load()

        win1 = {e.name for e in m1.list_skills() if e.enabled}
        win2 = {e.name for e in m2.list_skills() if e.enabled}
        assert win1 == win2 == {"gen-b"}, (
            f"winner changed with discovery order: {win1} vs {win2} — "
            "resolution is load-order dependent (must be precedence-only)"
        )

    def test_equal_precedence_tie_deterministic_and_warned(self, tmp_path, caplog):
        a = _mk(tmp_path / "a", "plug-a", [{
            "name": "gen", "path": "gen/SKILL.md", "description": "A",
            "capability": CAP, "provider_precedence": 100,
        }])
        b = _mk(tmp_path / "b", "plug-b", [{
            "name": "gen2", "path": "gen2/SKILL.md", "description": "B",
            "capability": CAP, "provider_precedence": 100,
        }])
        with caplog.at_level(logging.WARNING):
            m = _reg(b, a)  # add b first; tiebreak must be (plugin,skill), not order
            m.load()
        enabled = {e.name for e in m.list_skills() if e.enabled}
        # Tiebreak (-prec, plugin_name, skill_name): plug-a < plug-b → gen wins.
        assert enabled == {"gen"}, f"deterministic tiebreak failed: {enabled}"
        assert any("Provider-precedence tie" in r.message for r in caplog.records)

    def test_lifecycle_removed_excluded(self, tmp_path):
        a = _mk(tmp_path / "a", "plug-a", [{
            "name": "old", "path": "old/SKILL.md", "description": "old",
            "capability": CAP, "provider_precedence": 999,
            "lifecycle": "removed",
        }])
        b = _mk(tmp_path / "b", "plug-b", [{
            "name": "new", "path": "new/SKILL.md", "description": "new",
            "capability": CAP, "provider_precedence": 1,
        }])
        m = _reg(a, b)
        m.load()
        enabled = {e.name for e in m.list_skills() if e.enabled}
        assert enabled == {"new"}, (
            "lifecycle:removed must be excluded even at precedence 999"
        )

    def test_kernel_role_excluded_from_domain_precedence(self, tmp_path):
        """A kernel-role plugin's skill does not compete for domain
        provider-precedence (it is skipped by the resolver)."""
        k = _mk(tmp_path / "k", "kern", [{
            "name": "kskill", "path": "kskill/SKILL.md", "description": "k",
            "capability": CAP, "provider_precedence": 100,
        }], role="kernel")
        d = _mk(tmp_path / "d", "dom", [{
            "name": "dskill", "path": "dskill/SKILL.md", "description": "d",
            "capability": CAP, "provider_precedence": 1,
        }])
        m = _reg(k, d)
        m.load()
        enabled = {e.name for e in m.list_skills() if e.enabled}
        # kernel skill skipped by resolver → not disabled by it, and the
        # lone domain provider stays enabled (no competition registered).
        assert "dskill" in enabled, "domain provider wrongly disabled"
        assert "kskill" in enabled, "kernel skill must not be precedence-disabled"


class TestInertnessWhenNoCapabilityDeclared:
    def test_legacy_conflicts_with_unchanged_by_resolver(self, tmp_path):
        """No skill declares `capability` → resolver is a no-op → the
        legacy conflicts_with auto-disable behaves exactly as before."""
        a = _mk(tmp_path / "a", "plug-a", [{
            "name": "dup", "path": "dup/SKILL.md", "description": "A",
            "conflicts_with": ["plug-b/dup"],
        }])
        b = _mk(tmp_path / "b", "plug-b", [{
            "name": "dup", "path": "dup/SKILL.md", "description": "B",
        }])
        m = _reg(a, b)
        m.load()  # plug-a declares conflicts_with → plug-a/dup self-disables
        assert m.get_owner("dup") == "plug-b"
        by = {(p, e.name): e for p, e in m.iter_plugin_skills()}
        assert by[("plug-a", "dup")].enabled is False
        assert by[("plug-b", "dup")].enabled is True

    def test_undeclared_collision_still_hard_fails(self, tmp_path):
        """No capability, no conflicts_with, same name in two plugins →
        still DuplicateSkillError (the resolver did not silently pick)."""
        a = _mk(tmp_path / "a", "plug-a", [
            {"name": "same", "path": "same/SKILL.md", "description": "A"},
        ])
        b = _mk(tmp_path / "b", "plug-b", [
            {"name": "same", "path": "same/SKILL.md", "description": "B"},
        ])
        m = _reg(a, b)
        try:
            m.load()
            raised = False
        except DuplicateSkillError:
            raised = True
        assert raised, "undeclared same-name collision must hard-fail, not auto-pick"


class TestNamedAccessorsParity:
    def test_accessors_exist_and_match_legacy_outputs(self, tmp_path):
        """The named accessors return exactly what the prior inline
        consumers computed (pure refactor behind identical outputs)."""
        a = _mk(tmp_path / "a", "plug-a", [
            {"name": "od", "path": "od/SKILL.md", "description": "on demand",
             "inject_mode": "on_demand", "tags": ["custom-tag"]},
            {"name": "fw", "path": "fw/SKILL.md", "description": "framework",
             "inject_mode": "always"},
        ])
        m = _reg(a)
        m.load()
        # invocable_skills (slash surface) — enabled ∧ on_demand
        assert sorted(e.name for e in m.invocable_skills()) == ["od"]
        # classification_tags — same aggregation persona used
        ct = m.classification_tags()
        assert ct.get("custom-tag") == "on demand"
        # execution_routes is an exact alias of get_execution_model
        assert m.execution_routes(["custom-tag"]) == m.get_execution_model(
            ["custom-tag"]
        )
        # mcp_contributions delegates to the same impl (no MCP here → [])
        assert m.mcp_contributions("tree") == []
