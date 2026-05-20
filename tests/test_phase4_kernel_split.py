"""Phase 4 — ainstein-core split into ainstein-kernel + esa-workflow.

Gates (plan Phase-4): kernel policy enforced on every write path (with
positive controls — the op must succeed for a non-kernel skill so the
refusal isn't vacuous); kernel non-shadowable; deterministic 3-plugin
discovery order (hazard #2); the #1 risk (rag-quality-assurance
thresholds must route to ainstein-kernel) locked as a regression test;
A0 shared-references co-location.

NOTE: Phase-4 Decision 2 (esa-document-ontology = kernel) was later
REVERSED by explicit author decision — the ESA document ontology is
ESA-specific, so it now lives in esa-workflow (still inject_mode:always;
no longer kernel-protected). Owner asserted as esa-workflow below.

RE-BASELINE (Phase-5/supersession, user-authorized — documented as an
intended program consequence, NOT a silent break): ainstein-core was
deleted; enterpower-architecture is the authoritative architecture-domain
provider. The 3-plugin set is now ainstein-kernel + esa-workflow +
enterpower-architecture; the legacy 7 ainstein-core architecture skills
are superseded by enterpower's 9 (different names AND OXC output format —
e.g. archimate-generator → archimate-oxc-generator). The CROSS-PHASE
invariants Phase 4 actually gates — kernel policy on every write path,
the #1 rag-qa-thresholds-route-to-kernel risk, A0 shared-refs
co-location, deterministic discovery — are UNCHANGED in kind and are
re-pointed at the post-supersession aggregate. The behavioural
no-regression proof for the supersession itself is the live KB
regression (run separately), not these structural goldens.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aion.skills.multi_registry import (
    MultiPluginRegistry,
    _reset_multi_registry_for_tests,
)
from aion.skills.plugin import load_plugin_manifest

_PLUGINS = Path(__file__).parent.parent / "plugins"
KERNEL = _PLUGINS / "ainstein-kernel"
ESAWF = _PLUGINS / "esa-workflow"
ENTERPOWER = _PLUGINS / "enterpower-architecture"

# The 9 enterpower architecture-domain skills that supersede ainstein-core's
# legacy 7 (post Phase-5 supersession; enterpower is authoritative).
_ENTERPOWER_SKILLS = (
    "archimate-oxc-generator", "archimate-oxc-view-generator",
    "archimate-tools", "archimate-viewer", "archimate-visual-composer",
    "principle-generator", "principle-quality-assessor",
    "repo-to-archimate", "repo-architecture-explorer",
)


def _full() -> MultiPluginRegistry:
    _reset_multi_registry_for_tests()
    m = MultiPluginRegistry()
    for r in sorted([KERNEL, ESAWF, ENTERPOWER]):
        m.add_plugin_from_object(load_plugin_manifest(r))
    m.load()
    import aion.skills.multi_registry as mr
    mr._global_multi = m
    return m


class TestSplitLayout:
    def test_three_bundled_plugins_with_correct_roles(self):
        m = _full()
        plugs = {p: m.get_plugin(p) for p in m.list_plugins()}
        assert set(plugs) == {
            "ainstein-kernel", "esa-workflow", "enterpower-architecture"
        }
        assert plugs["ainstein-kernel"].role == "kernel"
        assert plugs["esa-workflow"].role == "domain"
        assert plugs["enterpower-architecture"].role == "domain"
        _reset_multi_registry_for_tests()

    def test_skill_homes(self):
        m = _full()
        # Owner map after resolution — who provides each skill.
        assert m.get_owner("ainstein-identity") == "ainstein-kernel"
        assert m.get_owner("persona-orchestrator") == "ainstein-kernel"
        assert m.get_owner("rag-quality-assurance") == "ainstein-kernel"
        assert m.get_owner("response-formatter") == "ainstein-kernel"
        # esa-document-ontology: REVERSES Phase-4 Decision 2 (was kernel
        # for ingestion/disambiguation) by explicit author decision — the
        # ESA ADR/PCP/DAR ontology is ESA-specific, not generic host
        # behaviour, so it now lives in esa-workflow (still
        # inject_mode:always; disableable + absent without esa-workflow).
        assert m.get_owner("esa-document-ontology") == "esa-workflow"
        assert m.get_owner("skosmos-vocabulary") == "esa-workflow"
        # Post-supersession: the architecture-domain skills are enterpower's
        # (authoritative; superseded ainstein-core's legacy 7).
        for s in _ENTERPOWER_SKILLS:
            assert m.get_owner(s) == "enterpower-architecture", s
        _reset_multi_registry_for_tests()

    def test_aggregate_is_15_post_supersession(self):
        """Cross-phase aggregate re-baseline (intended consequence):
        4 kernel + 2 esa-workflow + 9 enterpower = 15 (esa-document-
        ontology moved kernel→esa-workflow). The invariant Phase 4 gates
        is 'no skill silently lost in the re-home', re-pointed at the
        post-supersession union.
        """
        m = _full()
        assert len(m.list_skills()) == 15, (
            "aggregate skill count drift — expected the 15 skills "
            "(4 kernel + skosmos + esa-document-ontology + 9 enterpower)"
        )
        _reset_multi_registry_for_tests()


class TestThresholdsRoutingRegression:
    def test_rag_qa_thresholds_route_to_kernel(self):
        """THE #1 Phase-4 risk, locked (UNCHANGED by supersession —
        rag-quality-assurance is a kernel skill, untouched by the
        ainstein-core deletion): abstention/retrieval/truncation are
        consumed only via get_skill_tuning('rag-quality-assurance', ...)
        which routes to the OWNING plugin. rag-quality-assurance lives in
        ainstein-kernel, so its thresholds.yaml MUST resolve there — if
        they'd been left elsewhere this returns defaults and KB retrieval
        limits/abstention silently regress.
        """
        m = _full()
        assert m.get_owner("rag-quality-assurance") == "ainstein-kernel"
        trunc = m.get_skill_tuning("rag-quality-assurance", "get_truncation", {})
        assert trunc.get("max_context_results") == 50
        assert trunc.get("content_max_chars") == 800
        ab = m.get_skill_tuning(
            "rag-quality-assurance", "get_abstention_thresholds", 0.5
        )
        assert ab == 0.6, f"abstention threshold lost in split: {ab}"
        rl = m.get_skill_tuning("rag-quality-assurance", "get_retrieval_limits", {})
        assert rl.get("adr") == 8 and rl.get("principle") == 6
        _reset_multi_registry_for_tests()


class TestKernelPolicyWritePaths:
    def test_cannot_disable_kernel_skill_via_set_skill_enabled(self):
        m = _full()
        with pytest.raises(ValueError, match="[Kk]ernel"):
            m.set_skill_enabled("ainstein-identity", False)
        _reset_multi_registry_for_tests()

    def test_cannot_disable_kernel_skill_in_plugin(self):
        m = _full()
        with pytest.raises(ValueError, match="[Kk]ernel"):
            m.set_skill_enabled_in_plugin(
                "ainstein-kernel", "persona-orchestrator", False
            )
        _reset_multi_registry_for_tests()

    def test_non_kernel_skill_CAN_be_toggled_positive_control(self, tmp_path):
        """Positive control on a SYNTHETIC plugin (never committed source):
        the same mutation path that REFUSES a kernel skill SUCCEEDS for a
        domain skill — proving the kernel refusal is the policy firing, not
        the path being broken for everyone.

        Uses a throwaway tmp_path plugin pair because set_skill_enabled
        line-edits the registry YAML on disk; running it against the real
        ainstein-kernel/enterpower-architecture would mutate committed
        files (a destructive test side-effect — exactly what must never
        ship).
        """
        import json
        import yaml as _yaml

        def mk(root, name, role, skill):
            d = root / ".ainstein-plugin"
            d.mkdir(parents=True, exist_ok=True)
            (d / "plugin.json").write_text(
                json.dumps({"name": name, "runtime": "ainstein", "role": role}),
                encoding="utf-8",
            )
            (d / "skills-registry.yaml").write_text(
                _yaml.safe_dump({"skills": [{
                    "name": skill, "path": f"{skill}/SKILL.md",
                    "description": "x", "enabled": True,
                }]}, sort_keys=False),
                encoding="utf-8",
            )
            sd = root / "skills" / skill
            sd.mkdir(parents=True, exist_ok=True)
            (sd / "SKILL.md").write_text(
                f"---\nname: {skill}\ndescription: x\n---\nb\n", encoding="utf-8",
            )
            return root

        kroot = mk(tmp_path / "k", "synth-kernel", "kernel", "kskill")
        droot = mk(tmp_path / "d", "synth-domain", "domain", "dskill")
        _reset_multi_registry_for_tests()
        m = MultiPluginRegistry()
        m.add_plugin_from_object(load_plugin_manifest(kroot))
        m.add_plugin_from_object(load_plugin_manifest(droot))
        m.load()

        # Refusal: kernel skill cannot be disabled.
        with pytest.raises(ValueError, match="[Kk]ernel"):
            m.set_skill_enabled_in_plugin("synth-kernel", "kskill", False)
        # Positive control: SAME path, domain skill — succeeds.
        assert m.set_skill_enabled_in_plugin(
            "synth-domain", "dskill", False
        ) is True
        _reset_multi_registry_for_tests()


class TestA0SharedRefsCoLocated:
    def test_archimate_group_and_shared_refs_stay_co_located(self):
        """A0 (plugin-scoped shared-references), re-pointed at enterpower.
        Post-supersession the archimate group is enterpower's
        (`shared_references: archimate-shared`); the Phase-4/Phase-5 fix
        moved enterpower's flat refs into that subdir so the per-group
        merge resolves. A severed co-location would silently no-op — this
        turns it into a failure.
        """
        m = _full()
        groups = {g.name: g for g in m.list_groups()}
        assert "archimate" in groups
        assert groups["archimate"].shared_references == "archimate-shared"
        # The shared-references dir physically co-located with enterpower
        # (A0: plugin-scoped; the archimate-oxc-* skills live here).
        assert (
            ENTERPOWER / "shared-references" / "archimate-shared"
            / "archim-3.2-element-types.md"
        ).is_file()
        # A grouped member still receives the merged refs (no sever).
        active = {s.name: s for s in m.get_active_skills()}
        gen = active.get("archimate-oxc-generator")
        assert gen is not None
        merged = [
            k for k, v in gen.references.items()
            if isinstance(v, str) and v
        ]
        assert merged, (
            "archimate-oxc-generator lost its merged shared references "
            "(A0 break — group↔shared-refs co-location severed)"
        )
        assert any("element-types" in k for k in merged), (
            f"archimate-oxc-generator missing element-types ref: {merged}"
        )
        _reset_multi_registry_for_tests()


class TestDeterministicDiscoveryOrder:
    def test_bundled_plugins_discover_in_sorted_order(self):
        """Hazard #2: with 3 in-tree plugins, resolution must not depend on
        filesystem order. PluginLoader scans <repo>/plugins/*/ sorted;
        assert that order is deterministic and stable across two scans.
        """
        from aion.skills.plugin_loader import PluginLoader

        a = [p.name for p in PluginLoader.discover()]
        b = [p.name for p in PluginLoader.discover()]
        assert a == b, f"discovery order non-deterministic: {a} vs {b}"
        bundled = [n for n in a if n in {
            "ainstein-kernel", "esa-workflow", "enterpower-architecture"
        }]
        assert bundled == sorted(bundled), f"bundled not sorted: {bundled}"


# --------------------------------------------------------------------------
# Amendment 4 — load/startup-level kernel enforcement (R2 #4). Two
# invariants, each with the paired positive control the engagement's
# vacuous-pass discipline requires (an assert-raise / assert-refusal is
# green for the wrong reason unless a control proves the mechanism can
# also NOT fire), plus the kernel×domain intersection asserted in one
# ordered pass (silent bugs live in the combination).
# --------------------------------------------------------------------------


def _mk(root: Path, name: str, role: str, skills: list[tuple[str, bool]]) -> Path:
    """Synthetic plugin on tmp_path (never committed source). `skills` is
    [(skill_name, enabled), ...] so a skill can be born disabled in YAML.
    """
    import json
    import yaml as _yaml

    d = root / ".ainstein-plugin"
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.json").write_text(
        json.dumps({"name": name, "runtime": "ainstein", "role": role}),
        encoding="utf-8",
    )
    (d / "skills-registry.yaml").write_text(
        _yaml.safe_dump({"skills": [
            {"name": s, "path": f"{s}/SKILL.md", "description": "x",
             "enabled": en}
            for s, en in skills
        ]}, sort_keys=False),
        encoding="utf-8",
    )
    for s, _en in skills:
        sd = root / "skills" / s
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "SKILL.md").write_text(
            f"---\nname: {s}\ndescription: x\n---\nb\n", encoding="utf-8",
        )
    return root


class TestKernelPresenceStartupInvariant:
    """Invariant 1: the singleton/discovery path must reject a deployment
    with NO role:kernel plugin (a domain-only host can route nothing)."""

    def test_no_kernel_plugin_rejected(self, tmp_path):
        from aion.skills.multi_registry import _require_kernel_plugin

        domain_only = [
            load_plugin_manifest(_mk(tmp_path / "d1", "d1", "domain", [("s1", True)])),
            load_plugin_manifest(_mk(tmp_path / "d2", "d2", "domain", [("s2", True)])),
        ]
        with pytest.raises(RuntimeError, match="role: kernel|kernel"):
            _require_kernel_plugin(domain_only)

    def test_kernel_present_passes_positive_control(self, tmp_path):
        """SAME check, with a kernel plugin in the set — must NOT raise.
        Proves the rejection above is the policy firing, not an
        always-raise bug (vacuous-pass control)."""
        from aion.skills.multi_registry import _require_kernel_plugin

        mixed = [
            load_plugin_manifest(_mk(tmp_path / "d", "d", "domain", [("s", True)])),
            load_plugin_manifest(_mk(tmp_path / "k", "k", "kernel", [("ks", True)])),
        ]
        _require_kernel_plugin(mixed)  # no raise

    def test_real_bundled_discovery_satisfies_invariant(self):
        """Production-path positive control: the real in-tree bundled set
        contains ainstein-kernel (role:kernel), so discovery + the
        invariant pass end-to-end (the check is reachable and green on the
        shipping configuration, not only on synthetic inputs)."""
        from aion.skills.multi_registry import _require_kernel_plugin
        from aion.skills.plugin_loader import PluginLoader

        discovered = PluginLoader.discover()
        assert any(getattr(p, "role", "domain") == "kernel" for p in discovered), (
            f"real bundled set lost its kernel plugin: "
            f"{sorted(p.name for p in discovered)}"
        )
        _require_kernel_plugin(discovered)  # no raise on the shipping set


class TestKernelSkillForcedEnabledAtLoad:
    """Invariant 2: a kernel skill marked disabled in registry YAML is
    force-enabled at load (config drift can't silently remove kernel
    behavior); a disabled DOMAIN skill is left alone (positive control)."""

    def _loaded(self, *roots: Path) -> MultiPluginRegistry:
        _reset_multi_registry_for_tests()
        m = MultiPluginRegistry()
        for r in roots:
            m.add_plugin_from_object(load_plugin_manifest(r))
        m.load()
        return m

    def test_disabled_kernel_skill_is_force_enabled(self, tmp_path):
        k = _mk(tmp_path / "k", "synth-kernel", "kernel", [("kskill", False)])
        m = self._loaded(k)
        entry = m._registries["synth-kernel"].get_skill_entry("kskill")
        assert entry is not None and entry.enabled is True, (
            "kernel skill disabled in YAML must be force-enabled at load"
        )
        _reset_multi_registry_for_tests()

    def test_disabled_domain_skill_stays_disabled_positive_control(self, tmp_path):
        d = _mk(tmp_path / "d", "synth-domain", "domain", [("dskill", False)])
        m = self._loaded(d)
        entry = m._registries["synth-domain"].get_skill_entry("dskill")
        assert entry is not None and entry.enabled is False, (
            "domain skill disabled in YAML must STAY disabled — proves the "
            "force-enable is kernel-scoped policy, not force-everything"
        )
        _reset_multi_registry_for_tests()

    def test_kernel_and_domain_disabled_in_one_load_intersection(self, tmp_path):
        """Untested-intersection, single ordered pass: a kernel plugin
        (kernel skill born disabled) AND a domain plugin (domain skill
        born disabled) loaded into the SAME registry. Assert BOTH
        invariants together — kernel forced on, domain left off — so the
        silent combination (force-everything, or kernel policy not firing
        when a domain plugin is also present) cannot slip through split
        tests."""
        k = _mk(tmp_path / "k", "k-plug", "kernel", [("kskill", False)])
        d = _mk(tmp_path / "d", "d-plug", "domain", [("dskill", False)])
        m = self._loaded(k, d)
        k_entry = m._registries["k-plug"].get_skill_entry("kskill")
        d_entry = m._registries["d-plug"].get_skill_entry("dskill")
        assert k_entry is not None and k_entry.enabled is True, "kernel not forced on"
        assert d_entry is not None and d_entry.enabled is False, "domain wrongly enabled"
        _reset_multi_registry_for_tests()
