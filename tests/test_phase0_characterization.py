"""Phase 0 — characterization harness (Plugin-Centered Architecture Program).

Captures the cross-phase invariants the migration must NOT silently change:
the four implicit contribution-point outputs + per-skill storage envelope
+ per-group merged shared-reference set, against the real bundled plugin
set.

RE-BASELINE (Phase-5/supersession, user-authorized): ainstein-core was
deleted; enterpower-architecture is the authoritative architecture-domain
provider. The characterized AGGREGATE legitimately changed (different
skill set/names — e.g. archimate-generator → archimate-oxc-generator,
plus enterpower's archimate-viewer/-visual-composer). This is a
deliberate, documented re-baseline of the goldens to the NEW aggregate —
NOT a silent break. The behavioural no-regression gate for the
supersession is the live KB regression (retrieval/abstention/
disambiguation depend on ainstein-kernel's rag-qa + esa-document-ontology,
not the domain skills), run separately.

Two classes of evidence, asserted differently (plan Amendment 6):
  (a) DETERMINISTIC goldens — structure-identical assertions here
      (no LLM, no network); must stay stable through later phases.
  (b) LLM-backed parity captures (generated artifact bodies) are NOT in
      this file — non-deterministic; Phase-6 audit territory.

Golden-freshness guard: every characterization first asserts the harness
actually exercised plugins and skills — a vacuous "all goldens match" on
an empty registry is the dangerous failure this guard prevents.

Aggregates are keyed plugin-AGNOSTICALLY (skill name, tag, agent type) so
plugin re-homes preserve them: the invariant is the union across plugins,
not per-plugin ownership.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aion.skills.multi_registry import (
    MultiPluginRegistry,
    _reset_multi_registry_for_tests,
)
from aion.skills.plugin import load_plugin_manifest

_PLUGINS_DIR = Path(__file__).parent.parent / "plugins"
# Post-supersession bundled set: ainstein-kernel (kernel) +
# esa-workflow (ESA domain) + enterpower-architecture (authoritative
# architecture domain). Sorted to match PluginLoader's <repo>/plugins/*/
# scan order. ASSERTED goldens are plugin-agnostic aggregates.
_BUNDLED_PLUGIN_ROOTS = sorted(
    p for p in (
        _PLUGINS_DIR / "ainstein-kernel",
        _PLUGINS_DIR / "esa-workflow",
        _PLUGINS_DIR / "enterpower-architecture",
    ) if (p / ".ainstein-plugin").is_dir()
)


def _build_core_registry() -> MultiPluginRegistry:
    """Build a fresh registry with the full in-tree bundled plugin set.

    Mirrors the production/e2e construction path. Post-supersession the
    bundled skills live across ainstein-kernel + esa-workflow +
    enterpower-architecture; the characterized AGGREGATE is the invariant.
    """
    _reset_multi_registry_for_tests()
    multi = MultiPluginRegistry()
    for root in _BUNDLED_PLUGIN_ROOTS:
        multi.add_plugin_from_object(load_plugin_manifest(root))
    multi.load()
    return multi


def _assert_fresh(multi: MultiPluginRegistry) -> None:
    """Golden-freshness guard — fail loudly if nothing was exercised."""
    plugins = multi.list_plugins()
    skills = multi.list_skills()
    assert plugins, "freshness guard: zero plugins discovered — goldens would be vacuous"
    assert skills, "freshness guard: zero skills loaded — goldens would be vacuous"
    # The kernel carries the always-on skills + the thresholds the KB path
    # routes to; enterpower carries the authoritative domain.
    assert "ainstein-kernel" in plugins, f"kernel missing, got {plugins}"
    assert "enterpower-architecture" in plugins, f"enterpower missing, got {plugins}"


@pytest.fixture
def core() -> MultiPluginRegistry:
    multi = _build_core_registry()
    _assert_fresh(multi)
    import aion.skills.multi_registry as mr
    mr._global_multi = multi
    yield multi
    _reset_multi_registry_for_tests()


# --------------------------------------------------------------------------
# Canonical post-supersession aggregate (ainstein-core deleted; enterpower
# authoritative). 15 skills: 5 kernel + 1 ESA-workflow + 9 enterpower.
# --------------------------------------------------------------------------

EXPECTED_SKILLS = sorted([
    "ainstein-identity", "persona-orchestrator", "response-formatter",
    "rag-quality-assurance", "esa-document-ontology",          # 5 kernel
    "skosmos-vocabulary",                                       # 1 ESA workflow
    "archimate-oxc-generator", "archimate-oxc-view-generator",  # enterpower
    "archimate-tools", "archimate-viewer",                      #  authoritative
    "archimate-visual-composer", "principle-generator",         #  architecture
    "principle-quality-assessor", "repo-to-archimate",          #  domain (9)
    "repo-architecture-explorer",
])
EXPECTED_ALWAYS = sorted([
    "ainstein-identity", "persona-orchestrator", "response-formatter",
    "rag-quality-assurance", "esa-document-ontology",
])
EXPECTED_ON_DEMAND = sorted([
    "skosmos-vocabulary", "archimate-oxc-generator",
    "archimate-oxc-view-generator", "archimate-tools", "archimate-viewer",
    "archimate-visual-composer", "principle-generator",
    "principle-quality-assessor", "repo-to-archimate",
    "repo-architecture-explorer",
])


class TestInventory:
    def test_aggregate_inventory_is_15(self, core):
        names = sorted(e.name for e in core.list_skills())
        assert names == EXPECTED_SKILLS, (
            f"inventory drift — expected the 15 post-supersession skills, got {names}"
        )
        assert len(names) == 15

    def test_deleted_plugins_absent(self, core):
        names = {e.name for e in core.list_skills()}
        plugins = set(core.list_plugins())
        assert "architecture-enterprise-oracle" not in names, (
            "Pre-Phase-0 dead-scaffold cleanup not applied"
        )
        assert "ainstein-core" not in plugins, (
            "ainstein-core should be deleted (superseded by enterpower)"
        )


# --------------------------------------------------------------------------
# Class-(a) deterministic goldens — the four contribution-point surfaces
# --------------------------------------------------------------------------


class TestExtensionPointGoldens:
    def test_slash_invocable_set(self, core):
        """Slash surface = enabled ∧ inject_mode == on_demand."""
        invocable = sorted(e.name for e in core.invocable_skills())
        assert invocable == EXPECTED_ON_DEMAND, (
            f"slash-invocable surface drift: {invocable}"
        )

    def test_always_on_set(self, core):
        always = sorted(
            e.name for e in core.list_skills()
            if e.enabled and e.inject_mode == "always"
        )
        assert always == EXPECTED_ALWAYS, f"always-on surface drift: {always}"

    def test_agent_routing_surface(self, core):
        """tag-set → ExecutionModel, per skill (plugin-agnostic key)."""
        routes = {
            e.name: str(core.get_execution_model(e.tags))
            for e in sorted(core.list_skills(), key=lambda x: x.name)
        }
        assert set(routes) == set(EXPECTED_SKILLS)
        assert all(v for v in routes.values()), routes
        second = _build_core_registry()
        routes2 = {
            e.name: str(second.get_execution_model(e.tags))
            for e in sorted(second.list_skills(), key=lambda x: x.name)
        }
        _reset_multi_registry_for_tests()
        assert routes == routes2, "agent-routing surface is non-deterministic"

    def test_mcp_server_union(self, core):
        """MCP contribution = union of (plugin, server) per agent type.

        No bundled plugin routes an MCP server via the per-skill
        `mcp_servers` field today. enterpower ships a `preview` MCP server
        in .mcp.json but no skill declares `mcp_servers: [preview]`, so
        AInstein's D10 routing bridges nothing — the union is empty for
        every agent type. This golden makes that explicit so wiring the
        viewer's preview server later is a visible, intended diff.
        """
        agent_types = (
            "tree", "vocabulary", "archimate",
            "principle", "repo_analysis", "generation",
        )
        union = {
            at: sorted(core.mcp_contributions(at)) for at in agent_types
        }
        assert union == {at: [] for at in agent_types}, (
            f"MCP union expected empty (preview server unwired), got {union}"
        )

    def test_classification_tag_surface_deterministic(self, core):
        """Persona classification-tag addendum: deterministic + surfaces
        exactly the registry's enabled on_demand non-canonical tags.
        """
        from aion.persona import Persona, _CANONICAL_SKILL_TAGS

        p1 = Persona()
        add1 = p1._build_skill_tags_addendum()
        p2 = Persona()
        add2 = p2._build_skill_tags_addendum()
        assert add1 == add2, "classification addendum is non-deterministic"

        expected_tags = set()
        for e in core.list_skills():
            if not e.enabled or e.inject_mode != "on_demand":
                continue
            if any(t in _CANONICAL_SKILL_TAGS for t in e.tags):
                continue
            expected_tags.update(e.tags)
        for tag in expected_tags:
            assert tag in add1, (
                f"classification surface lost tag {tag!r} — contribution drift"
            )


# --------------------------------------------------------------------------
# Storage envelope (deterministic) — filename/content_type contract
# --------------------------------------------------------------------------


class TestStorageEnvelope:
    def test_per_skill_storage_envelope(self, core):
        envelope = {
            e.name: (e.content_type, e.type)
            for e in sorted(core.list_skills(), key=lambda x: x.name)
        }
        assert set(envelope) == set(EXPECTED_SKILLS)
        second = _build_core_registry()
        envelope2 = {
            e.name: (e.content_type, e.type)
            for e in sorted(second.list_skills(), key=lambda x: x.name)
        }
        _reset_multi_registry_for_tests()
        assert envelope == envelope2, "storage envelope is non-deterministic"


# --------------------------------------------------------------------------
# A0 — per-group merged shared-reference set (plugin-scoped invariant)
# --------------------------------------------------------------------------


class TestSharedReferenceMergeGolden:
    def test_grouped_skills_receive_merged_shared_refs(self, core):
        """Every member of a group declaring `shared_references` must, when
        loaded, carry the merged reference files from that plugin's
        `shared-references/<subfolder>/`. A0: plugin-scoped — a severed
        co-location silently no-ops; this golden turns that into a failure.

        Post-supersession the archimate group is enterpower's
        (`shared_references: archimate-shared`); the Phase-4 fix moved
        enterpower's flat refs into that subdir so the merge resolves.
        """
        groups = [g for g in core.list_groups() if g.shared_references]
        assert groups, (
            "freshness: expected at least the enterpower `archimate` group "
            "with shared_references — none found"
        )
        active = {s.name: s for s in core.get_active_skills()}
        captured: dict[str, dict[str, list[str]]] = {}
        for g in groups:
            captured[g.name] = {}
            for member in g.skills:
                skill = active.get(member)
                if skill is None:
                    continue
                ref_keys = sorted(
                    k for k, v in skill.references.items()
                    if isinstance(v, str)
                )
                captured[g.name][member] = ref_keys
                assert ref_keys, (
                    f"group {g.name!r} member {member!r} received NO merged "
                    f"shared references — A0 co-location is broken"
                )
        assert "archimate" in captured, f"groups seen: {list(captured)}"
        archimate_members = captured["archimate"]
        assert archimate_members, "archimate group has no active members"
        for member, refs in archimate_members.items():
            assert any("element-types" in r for r in refs), (
                f"archimate member {member!r} missing element-types ref: {refs}"
            )
