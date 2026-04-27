"""Tests for Persona intent classification and parsing."""

import json

from aion.persona import Persona, PlanStep


class TestParseResponse:
    """Tests for Persona._parse_response() github_refs parsing."""

    def setup_method(self):
        self.persona = Persona()

    def test_github_refs_from_json(self):
        raw = json.dumps({
            "intent": "generation",
            "content": "Build an ArchiMate model from OpenSTEF repos",
            "skill_tags": ["archimate"],
            "doc_refs": [],
            "github_refs": ["OpenSTEF/openstef", "OpenSTEF/openstef-dbc"],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["intent"] == "generation"
        assert parsed["github_refs"] == ["OpenSTEF/openstef", "OpenSTEF/openstef-dbc"]
        assert parsed["skill_tags"] == ["archimate"]
        assert parsed["doc_refs"] == []

    def test_github_refs_missing_key_defaults_empty(self):
        raw = json.dumps({
            "intent": "retrieval",
            "content": "What does ADR.29 decide?",
            "skill_tags": [],
            "doc_refs": ["ADR.29"],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["intent"] == "retrieval"
        assert parsed["github_refs"] == []
        assert parsed["doc_refs"] == ["ADR.29"]

    def test_github_refs_malformed_string_defaults_empty(self):
        raw = json.dumps({
            "intent": "generation",
            "content": "Build model",
            "skill_tags": ["archimate"],
            "doc_refs": [],
            "github_refs": "OpenSTEF/openstef",  # string instead of list
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["github_refs"] == []

    def test_github_refs_with_whitespace_stripped(self):
        raw = json.dumps({
            "intent": "generation",
            "content": "Build model",
            "skill_tags": ["archimate"],
            "doc_refs": [],
            "github_refs": [" OpenSTEF/openstef ", "  OpenSTEF/openstef-dbc"],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["github_refs"] == ["OpenSTEF/openstef", "OpenSTEF/openstef-dbc"]

    def test_github_refs_empty_on_line_fallback(self):
        """Line-based fallback (non-JSON) should leave github_refs empty."""
        raw = "retrieval\nWhat does ADR.29 decide?"
        parsed = self.persona._parse_response(raw)
        assert parsed["intent"] == "retrieval"
        assert parsed["github_refs"] == []

    def test_github_refs_empty_on_empty_input(self):
        parsed = self.persona._parse_response("")
        assert parsed["intent"] == "retrieval"
        assert parsed["github_refs"] == []

    def test_github_refs_filters_empty_strings(self):
        raw = json.dumps({
            "intent": "generation",
            "content": "Build model",
            "skill_tags": [],
            "doc_refs": [],
            "github_refs": ["OpenSTEF/openstef", "", None, "OpenSTEF/openstef-dbc"],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["github_refs"] == ["OpenSTEF/openstef", "OpenSTEF/openstef-dbc"]


class TestParseResponsePlannerFields:
    """Tests for Persona._parse_response() complexity and synthesis_instruction fields."""

    def setup_method(self):
        self.persona = Persona()

    def test_planner_fields_present_and_valid(self):
        raw = json.dumps({
            "intent": "retrieval",
            "content": "Compare pasted assessment with knowledge base results",
            "skill_tags": [],
            "doc_refs": [],
            "github_refs": [],
            "complexity": "multi-step",
            "synthesis_instruction": "Compare the user's pasted assessment with the retrieved knowledge base results.",
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["complexity"] == "multi-step"
        assert parsed["synthesis_instruction"] == "Compare the user's pasted assessment with the retrieved knowledge base results."

    def test_planner_fields_absent_default_to_simple_and_none(self):
        """Fields missing from JSON → safe defaults, no KeyError."""
        raw = json.dumps({
            "intent": "retrieval",
            "content": "What does ADR.21 say?",
            "skill_tags": [],
            "doc_refs": ["ADR.21"],
            "github_refs": [],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["complexity"] == "simple"
        assert parsed["synthesis_instruction"] is None

    def test_invalid_complexity_value_coerced_to_simple(self):
        """Unknown complexity value → coerced to 'simple', not propagated."""
        raw = json.dumps({
            "intent": "retrieval",
            "content": "What does ADR.21 say?",
            "skill_tags": [],
            "doc_refs": [],
            "github_refs": [],
            "complexity": "parallel",  # not a valid value
            "synthesis_instruction": None,
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["complexity"] == "simple"

    def test_synthesis_instruction_none_in_json_returns_none(self):
        """Explicit null synthesis_instruction → None, not empty string."""
        raw = json.dumps({
            "intent": "retrieval",
            "content": "What does ADR.21 say?",
            "skill_tags": [],
            "doc_refs": [],
            "github_refs": [],
            "complexity": "simple",
            "synthesis_instruction": None,
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["complexity"] == "simple"
        assert parsed["synthesis_instruction"] is None

    def test_planner_fields_absent_on_line_fallback(self):
        """Line-based fallback (non-JSON) → planner fields use safe defaults."""
        raw = "retrieval\nWhat does ADR.21 say?"
        parsed = self.persona._parse_response(raw)
        assert parsed["complexity"] == "simple"
        assert parsed["synthesis_instruction"] is None


class TestParseResponseStepsField:
    """Tests for Persona._parse_response() steps field extraction."""

    def setup_method(self):
        self.persona = Persona()

    def test_steps_extracted_with_valid_queries(self):
        raw = json.dumps({
            "intent": "retrieval",
            "content": "Compare PCP.10 with ADR.29",
            "skill_tags": [],
            "doc_refs": ["PCP.10", "ADR.29"],
            "github_refs": [],
            "complexity": "multi-step",
            "synthesis_instruction": "Compare PCP.10 and ADR.29.",
            "steps": [
                {"query": "Principle PCP.10 statement", "skill_tags": [], "doc_refs": ["PCP.10"]},
                {"query": "ADR.29 decision and rationale", "skill_tags": [], "doc_refs": ["ADR.29"]},
            ],
        })
        parsed = self.persona._parse_response(raw)
        assert len(parsed["steps"]) == 2
        assert parsed["steps"][0].query == "Principle PCP.10 statement"
        assert parsed["steps"][0].doc_refs == ["PCP.10"]
        assert parsed["steps"][1].query == "ADR.29 decision and rationale"

    def test_steps_absent_defaults_empty(self):
        """No steps key in JSON → steps defaults to []."""
        raw = json.dumps({
            "intent": "retrieval",
            "content": "What does ADR.21 say?",
            "skill_tags": [],
            "doc_refs": [],
            "github_refs": [],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["steps"] == []

    def test_steps_capped_at_3(self):
        """More than 3 steps in JSON → only first 3 parsed."""
        raw = json.dumps({
            "intent": "retrieval",
            "content": "Multi-query",
            "skill_tags": [],
            "doc_refs": [],
            "github_refs": [],
            "complexity": "multi-step",
            "synthesis_instruction": None,
            "steps": [
                {"query": "Step 1", "skill_tags": [], "doc_refs": []},
                {"query": "Step 2", "skill_tags": [], "doc_refs": []},
                {"query": "Step 3", "skill_tags": [], "doc_refs": []},
                {"query": "Step 4", "skill_tags": [], "doc_refs": []},
                {"query": "Step 5", "skill_tags": [], "doc_refs": []},
            ],
        })
        parsed = self.persona._parse_response(raw)
        assert len(parsed["steps"]) == 3
        assert parsed["steps"][2].query == "Step 3"

    def test_steps_invalid_entries_skipped(self):
        """Steps with missing or non-string query are skipped."""
        raw = json.dumps({
            "intent": "retrieval",
            "content": "Query",
            "skill_tags": [],
            "doc_refs": [],
            "github_refs": [],
            "complexity": "multi-step",
            "synthesis_instruction": None,
            "steps": [
                {"query": "Valid step", "skill_tags": [], "doc_refs": []},
                {"skill_tags": []},          # missing query key
                {"query": "", "doc_refs": []},  # empty query string
                {"query": 42},               # non-string query
            ],
        })
        parsed = self.persona._parse_response(raw)
        assert len(parsed["steps"]) == 1
        assert parsed["steps"][0].query == "Valid step"

    def test_steps_query_whitespace_stripped(self):
        raw = json.dumps({
            "intent": "retrieval",
            "content": "Query",
            "skill_tags": [],
            "doc_refs": [],
            "github_refs": [],
            "complexity": "multi-step",
            "synthesis_instruction": None,
            "steps": [
                {"query": "  PCP.10 principles  ", "skill_tags": [], "doc_refs": []},
            ],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["steps"][0].query == "PCP.10 principles"

    def test_steps_returns_planstep_instances(self):
        """Parsed steps are PlanStep dataclass instances."""
        raw = json.dumps({
            "intent": "retrieval",
            "content": "Query",
            "skill_tags": [],
            "doc_refs": [],
            "github_refs": [],
            "complexity": "multi-step",
            "synthesis_instruction": None,
            "steps": [
                {"query": "test step", "skill_tags": ["archimate"], "doc_refs": ["ADR.1"]},
            ],
        })
        parsed = self.persona._parse_response(raw)
        step = parsed["steps"][0]
        assert isinstance(step, PlanStep)
        assert step.skill_tags == ["archimate"]
        assert step.doc_refs == ["ADR.1"]

    def test_steps_empty_on_line_fallback(self):
        """Line-based fallback (non-JSON) → steps defaults to []."""
        raw = "retrieval\nWhat does ADR.21 say?"
        parsed = self.persona._parse_response(raw)
        assert parsed["steps"] == []

    def test_steps_empty_on_empty_input(self):
        parsed = self.persona._parse_response("")
        assert parsed["steps"] == []


class TestComplexityGuardrails:
    """Tests for code-level complexity guardrails in _parse_response."""

    def setup_method(self):
        self.persona = Persona()

    def test_listing_intent_forces_listing_complexity(self):
        """intent=listing + complexity=simple → complexity overridden to listing."""
        raw = json.dumps({
            "intent": "listing",
            "content": "List all ADRs",
            "complexity": "simple",
            "doc_refs": [],
            "github_refs": [],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["complexity"] == "listing"

    def test_listing_intent_preserves_listing_complexity(self):
        """intent=listing + complexity=listing → no change needed."""
        raw = json.dumps({
            "intent": "listing",
            "content": "List all ADRs",
            "complexity": "listing",
            "doc_refs": [],
            "github_refs": [],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["complexity"] == "listing"

    def test_steps_populated_forces_multi_step(self):
        """Steps populated + complexity=simple → forced to multi-step."""
        raw = json.dumps({
            "intent": "retrieval",
            "content": "Compare ADR.27 and ADR.29",
            "complexity": "simple",
            "doc_refs": ["ADR.27", "ADR.29"],
            "github_refs": [],
            "steps": [
                {"query": "ADR.27 details", "skill_tags": [], "doc_refs": ["ADR.27"]},
                {"query": "ADR.29 details", "skill_tags": [], "doc_refs": ["ADR.29"]},
            ],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["complexity"] == "multi-step"
        assert len(parsed["steps"]) == 2

    def test_multi_step_with_steps_unchanged(self):
        """multi-step + populated steps → no override needed."""
        raw = json.dumps({
            "intent": "retrieval",
            "content": "Compare ADR.27 and ADR.29",
            "complexity": "multi-step",
            "doc_refs": ["ADR.27", "ADR.29"],
            "github_refs": [],
            "steps": [
                {"query": "ADR.27 details", "skill_tags": [], "doc_refs": ["ADR.27"]},
                {"query": "ADR.29 details", "skill_tags": [], "doc_refs": ["ADR.29"]},
            ],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["complexity"] == "multi-step"

    def test_multi_step_no_steps_preserves_complexity_and_warns(self, capsys):
        """multi-step + no steps → complexity unchanged, warning logged."""
        raw = json.dumps({
            "intent": "retrieval",
            "content": "Complex question",
            "complexity": "multi-step",
            "doc_refs": [],
            "github_refs": [],
            "steps": [],
        })
        parsed = self.persona._parse_response(raw)
        assert parsed["complexity"] == "multi-step"
        assert parsed["steps"] == []
        captured = capsys.readouterr().out
        assert "persona_complexity_mismatch" in captured
