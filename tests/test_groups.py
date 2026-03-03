"""Tests for skill groups and reference-only skill loading."""

from src.aion.skills.registry import get_skill_registry


class TestSkillGroups:

    def test_groups_loaded(self):
        r = get_skill_registry()
        groups = r.list_groups()
        assert len(groups) >= 1
        archimate = next(g for g in groups if g.name == "archimate")
        assert archimate.enabled is True
        assert len(archimate.skills) == 3

    def test_group_members_have_correct_fields(self):
        r = get_skill_registry()
        entries = {e.name: e for e in r.list_skills()}

        gen = entries["archimate-generator"]
        assert gen.group == "archimate"
        assert gen.type == "skill"
        assert gen.load_order == 1

        shared = entries["archimate-shared"]
        assert shared.group == "archimate"
        assert shared.type == "references"
        assert shared.load_order == 3

    def test_ungrouped_skills_have_empty_group(self):
        r = get_skill_registry()
        entries = {e.name: e for e in r.list_skills()}
        assert entries["ainstein-identity"].group == ""

    def test_references_skill_loads_content(self):
        r = get_skill_registry()
        content = r.get_skill_content(active_tags=["archimate"])
        assert len(content) > 0
        assert "ArchiMate" in content
        assert "Input concept" in content

    def test_load_order_generator_before_references(self):
        r = get_skill_registry()
        content = r.get_skill_content(active_tags=["archimate"])
        gen_pos = content.index("ArchiMate")
        map_pos = content.index("Input concept")
        assert gen_pos < map_pos, (
            f"Generator content (pos {gen_pos}) should appear before "
            f"references content (pos {map_pos})"
        )
