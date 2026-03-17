"""Tests for skill groups, reference injection, and get_injectable_content."""

from pathlib import Path

from aion.skills.loader import Skill
from aion.skills.registry import get_skill_registry


class TestSkillGroups:

    def test_groups_loaded(self):
        r = get_skill_registry()
        groups = r.list_groups()
        assert len(groups) >= 1
        archimate = next(g for g in groups if g.name == "archimate")
        assert archimate.enabled is True
        assert len(archimate.skills) == 2

    def test_group_members_have_correct_fields(self):
        r = get_skill_registry()
        entries = {e.name: e for e in r.list_skills()}

        gen = entries["archimate-generator"]
        assert gen.group == "archimate"
        assert gen.type == "skill"
        assert gen.load_order == 1

        view = entries["archimate-view-generator"]
        assert view.group == "archimate"
        assert view.type == "skill"
        assert view.load_order == 2

    def test_ungrouped_skills_have_empty_group(self):
        r = get_skill_registry()
        entries = {e.name: e for e in r.list_skills()}
        assert entries["ainstein-identity"].group == ""

    def test_archimate_generator_has_references(self):
        """archimate-generator should include shared references via group merge."""
        r = get_skill_registry()
        content = r.get_skill_content(active_tags=["archimate"])
        assert "allowed-relations" in content or "Allowed Relations" in content
        assert "element-types" in content or "Element Types" in content

    def test_load_order_within_group(self):
        r = get_skill_registry()
        content = r.get_skill_content(active_tags=["archimate"])
        assert len(content) > 0
        assert "ArchiMate" in content

    def test_shared_references_merged_into_members(self):
        """Shared references from archimate-shared should appear in both member skills."""
        r = get_skill_registry()
        content = r.get_skill_content(active_tags=["archimate"])
        # Shared refs: element-types, allowed-relations, xml-template
        assert "element-types" in content
        assert "allowed-relations" in content
        assert "xml-template" in content
        # Skill-specific refs should also be present
        assert "concept-mapping" in content  # archimate-generator only
        assert "view-layout" in content  # archimate-view-generator only

    def test_shared_references_group_field(self):
        """The archimate group should have shared_references set."""
        r = get_skill_registry()
        groups = r.list_groups()
        archimate = next(g for g in groups if g.name == "archimate")
        assert archimate.shared_references == "archimate-shared"

    def test_no_duplicate_references(self):
        """Shared refs should not exist as duplicates in member skill directories."""
        from pathlib import Path
        gen_refs = Path("skills/archimate-generator/references")
        view_refs = Path("skills/archimate-view-generator/references")
        # These should NOT exist in member dirs (canonical copies in archimate-shared)
        assert not (gen_refs / "element-types.md").exists()
        assert not (gen_refs / "allowed-relations.md").exists()
        assert not (view_refs / "element-types.md").exists()
        assert not (view_refs / "allowed-relations.md").exists()

    def test_execution_model_archimate_tag(self):
        """archimate tag should route to generation execution model."""
        r = get_skill_registry()
        assert r.get_execution_model(["archimate"]) == "generation"

    def test_generation_skill_lookup(self):
        """get_generation_skill should return archimate-generator with validation_tool."""
        r = get_skill_registry()
        gen = r.get_generation_skill(["archimate"])
        assert gen is not None
        assert gen.name == "archimate-generator"
        assert gen.validation_tool == "validate_archimate"


class TestInjectableContent:

    def test_injectable_content_includes_markdown_refs(self):
        """String references (markdown files) should be appended."""
        skill = Skill(
            name="test-skill",
            description="test",
            content="Main instructions here.",
            path=Path("/fake"),
            references={
                "ref-alpha": "Alpha reference content",
                "ref-beta": "Beta reference content",
            },
        )
        result = skill.get_injectable_content()
        assert "## Skill: test-skill" in result
        assert "Main instructions here." in result
        assert "### ref-alpha" in result
        assert "Alpha reference content" in result
        assert "### ref-beta" in result
        assert "Beta reference content" in result

    def test_injectable_content_excludes_dict_refs(self):
        """YAML-parsed references (dicts) should NOT be appended."""
        skill = Skill(
            name="test-skill",
            description="test",
            content="Main instructions here.",
            path=Path("/fake"),
            references={
                "thresholds": {"abstention": {"distance_threshold": 0.5}},
                "real-ref": "This is a markdown reference",
            },
        )
        result = skill.get_injectable_content()
        assert "### real-ref" in result
        assert "thresholds" not in result
        assert "distance_threshold" not in result

    def test_injectable_content_no_refs(self):
        """Skill with no references should return just the header + content."""
        skill = Skill(
            name="test-skill",
            description="test",
            content="Just instructions.",
            path=Path("/fake"),
        )
        result = skill.get_injectable_content()
        assert result == "## Skill: test-skill\n\nJust instructions."
        assert "---" not in result

    def test_injectable_content_refs_sorted(self):
        """References should be appended in sorted order by name."""
        skill = Skill(
            name="test-skill",
            description="test",
            content="Instructions.",
            path=Path("/fake"),
            references={
                "zebra": "Z content",
                "alpha": "A content",
            },
        )
        result = skill.get_injectable_content()
        alpha_pos = result.index("### alpha")
        zebra_pos = result.index("### zebra")
        assert alpha_pos < zebra_pos
