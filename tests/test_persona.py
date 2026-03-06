"""Tests for Persona intent classification and parsing."""

import json

import pytest

from src.aion.persona import Persona, PersonaResult


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
        intent, content, skill_tags, doc_refs, github_refs = self.persona._parse_response(raw)
        assert intent == "generation"
        assert github_refs == ["OpenSTEF/openstef", "OpenSTEF/openstef-dbc"]
        assert skill_tags == ["archimate"]
        assert doc_refs == []

    def test_github_refs_missing_key_defaults_empty(self):
        raw = json.dumps({
            "intent": "retrieval",
            "content": "What does ADR.29 decide?",
            "skill_tags": [],
            "doc_refs": ["ADR.29"],
        })
        intent, content, skill_tags, doc_refs, github_refs = self.persona._parse_response(raw)
        assert intent == "retrieval"
        assert github_refs == []
        assert doc_refs == ["ADR.29"]

    def test_github_refs_malformed_string_defaults_empty(self):
        raw = json.dumps({
            "intent": "generation",
            "content": "Build model",
            "skill_tags": ["archimate"],
            "doc_refs": [],
            "github_refs": "OpenSTEF/openstef",  # string instead of list
        })
        intent, content, skill_tags, doc_refs, github_refs = self.persona._parse_response(raw)
        assert github_refs == []

    def test_github_refs_with_whitespace_stripped(self):
        raw = json.dumps({
            "intent": "generation",
            "content": "Build model",
            "skill_tags": ["archimate"],
            "doc_refs": [],
            "github_refs": [" OpenSTEF/openstef ", "  OpenSTEF/openstef-dbc"],
        })
        intent, content, skill_tags, doc_refs, github_refs = self.persona._parse_response(raw)
        assert github_refs == ["OpenSTEF/openstef", "OpenSTEF/openstef-dbc"]

    def test_github_refs_empty_on_line_fallback(self):
        """Line-based fallback (non-JSON) should leave github_refs empty."""
        raw = "retrieval\nWhat does ADR.29 decide?"
        intent, content, skill_tags, doc_refs, github_refs = self.persona._parse_response(raw)
        assert intent == "retrieval"
        assert github_refs == []

    def test_github_refs_empty_on_empty_input(self):
        intent, content, skill_tags, doc_refs, github_refs = self.persona._parse_response("")
        assert intent == "retrieval"
        assert github_refs == []

    def test_github_refs_filters_empty_strings(self):
        raw = json.dumps({
            "intent": "generation",
            "content": "Build model",
            "skill_tags": [],
            "doc_refs": [],
            "github_refs": ["OpenSTEF/openstef", "", None, "OpenSTEF/openstef-dbc"],
        })
        intent, content, skill_tags, doc_refs, github_refs = self.persona._parse_response(raw)
        assert github_refs == ["OpenSTEF/openstef", "OpenSTEF/openstef-dbc"]
