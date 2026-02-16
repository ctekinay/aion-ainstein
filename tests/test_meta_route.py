"""Tests for the meta route: system self-description short-circuit."""

import json
import pytest
from src.meta_route import build_meta_response
from src.config import settings


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
