"""Tests for HTML skill support in the generation pipeline."""

from aion.generation import GenerationPipeline
from aion.skills.registry import SkillRegistryEntry


def _make_skill(name="archimate-generator", content_type=""):
    return SkillRegistryEntry(
        name=name, path=f"{name}/SKILL.md",
        description="test skill", content_type=content_type,
    )


class TestBuildResponseHtml:

    def test_archimate_skill_shows_archi_import_message(self):
        skill = _make_skill("archimate-generator")
        result = GenerationPipeline._build_response(
            '<model xmlns="..."></model>',
            validation_result=None, skill_entry=skill,
        )
        assert "Archi" in result
        assert "explorer" not in result.lower()

    def test_html_skill_shows_explorer_message(self):
        skill = _make_skill("repo-architecture-explorer", content_type="text/html")
        result = GenerationPipeline._build_response(
            "<html><body>explorer</body></html>",
            validation_result=None, skill_entry=skill,
        )
        assert "interactive explorer" in result.lower()
        assert "Archi" not in result

    def test_html_skill_does_not_inline_html_content(self):
        skill = _make_skill("repo-architecture-explorer", content_type="text/html")
        html = "<html><body><h1>Explorer</h1></body></html>"
        result = GenerationPipeline._build_response(
            html, validation_result=None, skill_entry=skill,
        )
        assert "<h1>Explorer</h1>" not in result

    def test_html_skill_inlines_content_when_generation_failed(self):
        skill = _make_skill("repo-architecture-explorer", content_type="text/html")
        result = GenerationPipeline._build_response(
            "Sorry, I could not generate the explorer.",
            validation_result=None, skill_entry=skill,
        )
        assert "Sorry, I could not generate the explorer." in result

    def test_archimate_skill_does_not_inline_xml(self):
        skill = _make_skill("archimate-generator")
        result = GenerationPipeline._build_response(
            '<model xmlns="..."><elements/></model>',
            validation_result=None, skill_entry=skill,
        )
        assert "<elements/>" not in result

    def test_no_skill_entry_falls_back_to_archimate_behavior(self):
        result = GenerationPipeline._build_response(
            "some raw text", validation_result=None, skill_entry=None,
        )
        assert "some raw text" in result
        assert "Archi" in result
