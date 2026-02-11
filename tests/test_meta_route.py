"""Tests for the meta route: system self-description short-circuit."""

import json
import pytest
from src.meta_route import is_meta_query, build_meta_response
from src.config import settings


class TestMetaIntentDetection:
    """Tests that meta questions are correctly detected and ESA questions are not."""

    # --- Should detect as meta ---

    def test_which_skills(self):
        assert is_meta_query("Which skills did you use to format this output?")

    def test_what_skills(self):
        assert is_meta_query("What skills have you used?")

    def test_show_steps(self):
        assert is_meta_query("Show me the sequential steps how you applied this skill")

    def test_when_skill_kicked_in(self):
        assert is_meta_query("When did the skill kick in?")

    def test_load_at_startup(self):
        assert is_meta_query("Do you load skills at startup?")

    def test_explain_own_architecture(self):
        assert is_meta_query("Explain your own architecture")

    def test_your_architecture(self):
        assert is_meta_query("Describe your architecture")

    def test_how_do_you_work(self):
        assert is_meta_query("How do you work?")

    def test_how_you_came_to_answer(self):
        assert is_meta_query("How did you come to this answer?")

    def test_functional_description_of_your_architecture(self):
        assert is_meta_query("Give me a functional description of your architecture")

    def test_prompt_preserved(self):
        assert is_meta_query("Do you mess up the original prompt with formatting?")

    def test_how_are_you_built(self):
        assert is_meta_query("How are you built?")

    def test_your_design(self):
        assert is_meta_query("Tell me about your design")

    # --- Should NOT detect as meta (ESA corpus questions) ---

    def test_not_meta_adr_reference(self):
        """ADR reference means ESA question, not meta."""
        assert not is_meta_query("Tell me about ADR.0025")

    def test_not_meta_pcp_reference(self):
        """PCP reference means ESA question, not meta."""
        assert not is_meta_query("Who approved PCP.0020?")

    def test_not_meta_iec_standard(self):
        """IEC standard reference means ESA question, not meta."""
        assert not is_meta_query("What is IEC 61970?")

    def test_not_meta_cim(self):
        """CIM reference means ESA question, not meta."""
        assert not is_meta_query("What is CIM?")

    def test_not_meta_alliander(self):
        """Alliander ESA question, not meta."""
        assert not is_meta_query("What is Alliander's energy system architecture?")

    def test_not_meta_general_question(self):
        """General domain question, not meta."""
        assert not is_meta_query("What security decisions exist?")

    def test_not_meta_list_adrs(self):
        """List query, not meta."""
        assert not is_meta_query("List all ADRs")

    def test_not_meta_vocabulary(self):
        """Vocabulary question, not meta."""
        assert not is_meta_query("What is Demandable Capacity?")


class TestIdentityDetection:
    """Tests that identity questions are detected as meta queries.

    Regression: "Who are you?" and "Are you Elysia?" were NOT caught by
    the meta route, causing the query to fall through to the Elysia Tree
    which answered from the internal framework's perspective.
    """

    def test_who_are_you(self):
        assert is_meta_query("Who are you?")

    def test_whats_your_name(self):
        assert is_meta_query("What's your name?")

    def test_what_is_your_name(self):
        assert is_meta_query("What is your name?")

    def test_are_you_elysia(self):
        assert is_meta_query("Are you Elysia?")

    def test_are_you_a_bot(self):
        assert is_meta_query("Are you a bot?")

    def test_are_you_an_ai(self):
        assert is_meta_query("Are you an AI?")

    def test_are_you_a_language_model(self):
        assert is_meta_query("Are you a language model?")

    def test_what_is_your_purpose(self):
        assert is_meta_query("What is your purpose?")

    def test_tell_me_about_yourself(self):
        assert is_meta_query("Tell me about yourself")

    def test_what_are_you(self):
        assert is_meta_query("What are you?")


class TestMetaResponse:
    """Tests that the meta response is correct and complete.

    At default disclosure level (0), responses are functional-only.
    Pipeline detail tests use monkeypatch to set level 1.
    """

    def test_plain_response_contains_ainstein(self):
        response = build_meta_response("Which skills did you use?")
        assert "AInstein" in response

    def test_plain_response_describes_capabilities(self):
        response = build_meta_response("Who are you?")
        assert "knowledge base" in response.lower()
        assert "ADR" in response or "Architecture Decision Records" in response

    def test_plain_response_no_esa_content(self):
        """Meta response must NOT contain ESA corpus content."""
        response = build_meta_response("Explain your architecture")
        assert "IEC 61968" not in response
        assert "market participant" not in response
        assert "DACI" not in response

    def test_plain_response_explains_pipeline_at_level1(self, monkeypatch):
        """Pipeline detail is available at disclosure level 1."""
        monkeypatch.setattr(settings, "ainstein_disclosure_level", 1)
        response = build_meta_response("Show me the steps")
        assert "Intent classification" in response or "intent classification" in response
        assert "routing" in response.lower()

    def test_structured_response_is_valid_json(self):
        response = build_meta_response("Which skills?", structured_mode=True)
        parsed = json.loads(response)
        assert parsed["schema_version"] == "1.0"
        assert "AInstein" in parsed["answer"]
        assert parsed["sources"] == []

    def test_structured_response_no_retrieval(self):
        response = build_meta_response("Your architecture", structured_mode=True)
        parsed = json.loads(response)
        assert "No ESA documents were retrieved" in parsed["transparency_statement"]


class TestDisclosureLevels:
    """Tests that meta responses respect the disclosure level setting.

    Level 0: functional description, no internal component names
    Level 1: RAG pipeline detail, still no internal names
    Level 2: full implementation detail (Elysia, Weaviate, etc.)
    """

    def test_level0_no_internals(self, monkeypatch):
        """Level 0 must not mention internal component names."""
        monkeypatch.setattr(settings, "ainstein_disclosure_level", 0)
        response = build_meta_response("How do you work?")
        assert "AInstein" in response
        assert "Weaviate" not in response
        assert "Elysia" not in response
        assert "DSPy" not in response
        assert "SKOSMOS" not in response
        assert "decision tree" not in response

    def test_level0_says_search_knowledge_base(self, monkeypatch):
        """Level 0 should describe capability in simple terms."""
        monkeypatch.setattr(settings, "ainstein_disclosure_level", 0)
        response = build_meta_response("Who are you?")
        assert "knowledge base" in response.lower()
        assert "AInstein" in response

    def test_level1_mentions_rag(self, monkeypatch):
        """Level 1 mentions RAG but not internal component names."""
        monkeypatch.setattr(settings, "ainstein_disclosure_level", 1)
        response = build_meta_response("How do you work?")
        assert "retrieval-augmented generation" in response
        assert "Weaviate" not in response
        assert "Elysia" not in response
        assert "DSPy" not in response

    def test_level2_full_detail(self, monkeypatch):
        """Level 2 includes full implementation details."""
        monkeypatch.setattr(settings, "ainstein_disclosure_level", 2)
        response = build_meta_response("How do you work?")
        assert "Weaviate" in response
        assert "SKOSMOS" in response

    def test_level0_identity_answer(self, monkeypatch):
        """Identity questions at level 0 identify as AInstein, not Elysia."""
        monkeypatch.setattr(settings, "ainstein_disclosure_level", 0)
        response = build_meta_response("Are you Elysia?")
        assert "AInstein" in response
        assert "Elysia" not in response

    def test_structured_mode_respects_level(self, monkeypatch):
        """Structured mode should also respect disclosure level."""
        monkeypatch.setattr(settings, "ainstein_disclosure_level", 0)
        response = build_meta_response("How do you work?", structured_mode=True)
        parsed = json.loads(response)
        assert "Weaviate" not in parsed["answer"]
        assert "Elysia" not in parsed["answer"]
