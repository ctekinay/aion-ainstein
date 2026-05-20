"""Tests for the dynamic skill-tags addendum in Persona's classification prompt.

The 5 canonical AInstein tags keep their hand-tuned guidance in the
hardcoded prompt. Plugin-supplied tags appear in an auto-generated
addendum that's rebuilt whenever the multi-registry reloads.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from aion.persona import Persona, _CANONICAL_SKILL_TAGS
from aion.skills.multi_registry import (
    MultiPluginRegistry,
    _reset_multi_registry_for_tests,
)
from aion.skills.plugin import load_plugin_manifest


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


def _install_registry(plugin_root: Path) -> MultiPluginRegistry:
    """Build a multi-registry from one plugin and install as singleton."""
    _reset_multi_registry_for_tests()
    multi = MultiPluginRegistry()
    multi.add_plugin_from_object(load_plugin_manifest(plugin_root))
    multi.load()
    import aion.skills.multi_registry as mr
    mr._global_multi = multi
    return multi


# ---------------------------------------------------------------------- canonical


class TestCanonicalPromptUntouched:
    def test_canonical_tags_always_in_hardcoded_prompt(self, tmp_path):
        """The canonical rows are unconditional — present regardless of registry."""
        # Empty registry: nothing in the registry → no addendum, only canonical.
        plugin_root = _make_plugin(tmp_path / "p", "demo", skills=[])
        _install_registry(plugin_root)

        p = Persona()
        prompt = p._get_classification_prompt()
        for tag in _CANONICAL_SKILL_TAGS:
            assert f'`"{tag}"`' in prompt, f"canonical tag {tag} missing from prompt"
        # With no on-demand skills present, no addendum heading.
        assert "## Additional plugin tags" not in prompt

    def test_canonical_tags_are_documented(self):
        """The canonical set must match the 5 hand-tuned rows in the prompt."""
        assert _CANONICAL_SKILL_TAGS == {
            "archimate",
            "vocabulary",
            "principle-quality",
            "generate-principle",
            "repo-analysis",
        }

    def test_addendum_appears_when_registry_has_noncanonical_tags(self, tmp_path):
        """A skill with a non-canonical tag triggers the addendum heading."""
        plugin_root = _make_plugin(tmp_path / "p", "demo", skills=[{
            "name": "skill-with-extra-tag",
            "path": "skill-with-extra-tag/SKILL.md",
            "description": "operates on widgets",
            "enabled": True,
            "inject_mode": "on_demand",
            "tags": ["widget"],
        }])
        _install_registry(plugin_root)

        p = Persona()
        prompt = p._get_classification_prompt()
        assert "## Additional plugin tags" in prompt
        assert '`"widget"`' in prompt


# ---------------------------------------------------------------------- addendum


class TestPluginTagsAddendum:
    def test_plugin_tag_appears_in_addendum(self, tmp_path):
        plugin_root = _make_plugin(tmp_path / "p", "demo", skills=[{
            "name": "skill-foo",
            "path": "skill-foo/SKILL.md",
            "description": "Foo-specific operations on widgets",
            "enabled": True,
            "inject_mode": "on_demand",
            "tags": ["custom-tag"],
        }])
        _install_registry(plugin_root)

        p = Persona()
        prompt = p._get_classification_prompt()
        assert "## Additional plugin tags" in prompt
        assert '`"custom-tag"`' in prompt
        assert "Foo-specific operations on widgets" in prompt

    def test_multiple_plugin_tags_sorted_alphabetically(self, tmp_path):
        plugin_root = _make_plugin(tmp_path / "p", "demo", skills=[
            {
                "name": "skill-z",
                "path": "skill-z/SKILL.md",
                "description": "zebra description",
                "enabled": True,
                "inject_mode": "on_demand",
                "tags": ["zeta-tag"],
            },
            {
                "name": "skill-a",
                "path": "skill-a/SKILL.md",
                "description": "alpha description",
                "enabled": True,
                "inject_mode": "on_demand",
                "tags": ["alpha-tag"],
            },
        ])
        _install_registry(plugin_root)

        p = Persona()
        prompt = p._get_classification_prompt()
        alpha_pos = prompt.find('`"alpha-tag"`')
        zeta_pos = prompt.find('`"zeta-tag"`')
        assert alpha_pos != -1 and zeta_pos != -1
        assert alpha_pos < zeta_pos

    def test_canonical_tag_with_extra_skill_does_not_duplicate(self, tmp_path):
        """A plugin skill with a canonical tag ("archimate") does NOT appear in the addendum."""
        plugin_root = _make_plugin(tmp_path / "p", "demo", skills=[{
            "name": "extra-archimate-skill",
            "path": "extra-archimate-skill/SKILL.md",
            "description": "extra arch operations",
            "enabled": True,
            "inject_mode": "on_demand",
            "tags": ["archimate"],  # canonical
        }])
        _install_registry(plugin_root)

        p = Persona()
        prompt = p._get_classification_prompt()
        # archimate row already in canonical table; addendum should NOT add it.
        assert "## Additional plugin tags" not in prompt

    def test_skill_with_canonical_plus_aliases_drops_all_aliases(self, tmp_path):
        """Skill with canonical tag + retrieval-side aliases: ALL aliases dropped.

        This is the production case for esa-workflow's skosmos-vocabulary:
        tags = [vocabulary, skosmos, definition, terminology, standard, IEC,
        abbreviation]. The canonical 'vocabulary' row covers the routing
        destination; the six aliases are noise in the classification prompt.
        """
        plugin_root = _make_plugin(tmp_path / "p", "demo", skills=[{
            "name": "vocab-like",
            "path": "vocab-like/SKILL.md",
            "description": "vocabulary lookups with aliases",
            "enabled": True,
            "inject_mode": "on_demand",
            # vocabulary is canonical; rest are aliases for the same destination.
            "tags": ["vocabulary", "skosmos", "definition", "IEC", "abbreviation"],
        }])
        _install_registry(plugin_root)

        p = Persona()
        prompt = p._get_classification_prompt()
        # No addendum at all — the canonical row covers the whole skill.
        assert "## Additional plugin tags" not in prompt
        # And none of the alias tags appear in the prompt body.
        for alias in ("skosmos", "definition", "IEC", "abbreviation"):
            assert f'`"{alias}"`' not in prompt

    def test_skill_with_canonical_plus_genuinely_new_tag_still_drops_new(self, tmp_path):
        """Owning-skill filter is per-skill, not per-tag.

        If a plugin author wants a genuinely-new tag, the skill should not
        also declare a canonical tag — they should split into two skills.
        Documents the tradeoff in the filter: canonical-tagged skills are
        treated as fully described by the canonical row.
        """
        plugin_root = _make_plugin(tmp_path / "p", "demo", skills=[{
            "name": "mixed-skill",
            "path": "mixed-skill/SKILL.md",
            "description": "mixes archimate with something new",
            "enabled": True,
            "inject_mode": "on_demand",
            "tags": ["archimate", "genuinely-new-tag"],
        }])
        _install_registry(plugin_root)

        p = Persona()
        prompt = p._get_classification_prompt()
        # The "genuinely-new-tag" doesn't appear because its owning skill
        # has a canonical tag. This is a documented tradeoff — plugin
        # authors should split orthogonal tags into separate skills.
        assert "genuinely-new-tag" not in prompt

    def test_disabled_skill_excluded_from_addendum(self, tmp_path):
        plugin_root = _make_plugin(tmp_path / "p", "demo", skills=[{
            "name": "disabled-foo",
            "path": "disabled-foo/SKILL.md",
            "description": "should not appear",
            "enabled": False,
            "inject_mode": "on_demand",
            "tags": ["disabled-tag"],
        }])
        _install_registry(plugin_root)

        p = Persona()
        prompt = p._get_classification_prompt()
        assert "## Additional plugin tags" not in prompt
        assert "disabled-tag" not in prompt

    def test_inject_mode_always_skill_excluded(self, tmp_path):
        """Framework-style always-loaded skills don't contribute slash-routing tags."""
        plugin_root = _make_plugin(tmp_path / "p", "demo", skills=[{
            "name": "always-skill",
            "path": "always-skill/SKILL.md",
            "description": "framework",
            "enabled": True,
            "inject_mode": "always",
            "tags": ["always-tag"],
        }])
        _install_registry(plugin_root)

        p = Persona()
        prompt = p._get_classification_prompt()
        assert "always-tag" not in prompt


# ---------------------------------------------------------------------- reload


class TestOnReloadRebuildsPrompt:
    def test_prompt_rebuilt_on_registry_reload(self, tmp_path):
        plugin_root = _make_plugin(tmp_path / "p", "demo", skills=[{
            "name": "skill-foo",
            "path": "skill-foo/SKILL.md",
            "description": "initial",
            "enabled": True,
            "inject_mode": "on_demand",
            "tags": ["initial-tag"],
        }])
        multi = _install_registry(plugin_root)

        p = Persona()
        assert '`"initial-tag"`' in p._get_classification_prompt()

        # Mutate the registry on disk: add a second tag-bearing skill.
        # Easiest: load a new registry, swap singleton, reload.
        import yaml as _yaml
        registry_path = plugin_root / ".ainstein-plugin" / "skills-registry.yaml"
        new_content = _yaml.safe_dump({
            "skills": [
                {
                    "name": "skill-foo",
                    "path": "skill-foo/SKILL.md",
                    "description": "initial",
                    "enabled": True,
                    "inject_mode": "on_demand",
                    "tags": ["initial-tag"],
                },
                {
                    "name": "skill-bar",
                    "path": "skill-bar/SKILL.md",
                    "description": "added later",
                    "enabled": True,
                    "inject_mode": "on_demand",
                    "tags": ["new-tag"],
                },
            ]
        }, sort_keys=False)
        registry_path.write_text(new_content, encoding="utf-8")
        # Also create the new skill folder so it can load.
        bar_dir = plugin_root / "skills" / "skill-bar"
        bar_dir.mkdir(parents=True, exist_ok=True)
        (bar_dir / "SKILL.md").write_text(
            "---\nname: skill-bar\ndescription: x\n---\nbody\n", encoding="utf-8",
        )

        # Trigger reload — Persona's on_reload callback should rebuild the prompt.
        multi.reload()

        prompt2 = p._get_classification_prompt()
        assert '`"initial-tag"`' in prompt2
        assert '`"new-tag"`' in prompt2
