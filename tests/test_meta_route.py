"""Tests for the meta route: system self-description short-circuit."""

import json
import pytest
from src.meta_route import is_meta_query, build_meta_response


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


class TestMetaResponse:
    """Tests that the meta response is correct and complete."""

    def test_plain_response_contains_pipeline(self):
        response = build_meta_response("Which skills did you use?")
        assert "AInstein" in response
        assert "skill" in response.lower()
        assert "retrieval" in response.lower() or "Retrieval" in response

    def test_plain_response_no_esa_content(self):
        """Meta response must NOT contain ESA corpus content."""
        response = build_meta_response("Explain your architecture")
        assert "IEC 61968" not in response
        assert "market participant" not in response
        assert "DACI" not in response

    def test_plain_response_explains_pipeline(self):
        response = build_meta_response("Show me the steps")
        assert "Intent classification" in response or "intent classification" in response
        assert "routing" in response.lower()
        assert "format" in response.lower()

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
