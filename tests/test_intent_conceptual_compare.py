"""Tests for PR X: conceptual compare intent detection and response.

Verifies that:
1. "difference between ADR and PCP" routes to semantic compare, not list
2. "ADR vs PCP" and "compare" variants are detected
3. Queries with only one doc type do NOT trigger compare
4. The deterministic response contains definitions for both types
"""

import pytest

from src.elysia_agents import (
    is_conceptual_compare_query,
    build_conceptual_compare_response,
)


class TestConceptualCompareDetection:
    """is_conceptual_compare_query() correctly identifies comparison queries."""

    # --- Should detect as compare ---

    @pytest.mark.parametrize("query", [
        "What's the difference between an ADR and a PCP?",
        "What is the difference between ADR and PCP?",
        "difference between ADRs and DARs",
        "ADR vs PCP",
        "ADR vs. PCP",
        "compare ADRs and DARs",
        "comparison of principles and policies",
        "ADR versus PCP",
        "How are ADRs different from PCPs?",
        "So, what's the difference between an ADR and a PCP?",
    ])
    def test_compare_detected(self, query):
        assert is_conceptual_compare_query(query), f"'{query}' should be a compare query"

    # --- Should NOT detect as compare ---

    @pytest.mark.parametrize("query", [
        "list ADRs",
        "What ADRs exist?",
        "Tell me about ADR.0025",
        "What is an ADR?",
        "What is CIM?",
        "compare the weather in two cities",
        "difference between Java and Python",
        "ADR vs the world",
        # Single doc-type only
        "What's the difference between ADR and something?",
    ])
    def test_compare_not_detected(self, query):
        assert not is_conceptual_compare_query(query), f"'{query}' should NOT be a compare query"


class TestCompareResponse:
    """build_conceptual_compare_response() produces correct content."""

    def test_adr_vs_pcp_contains_both_definitions(self):
        response = build_conceptual_compare_response(
            "What's the difference between an ADR and a PCP?"
        )
        assert "ADR" in response
        assert "PCP" in response
        assert "decision" in response.lower()
        assert "principle" in response.lower()

    def test_adr_vs_dar_contains_both_definitions(self):
        response = build_conceptual_compare_response(
            "difference between ADRs and DARs"
        )
        assert "ADR" in response
        assert "DAR" in response

    def test_response_does_not_list_documents(self):
        """Compare response must NOT contain list output."""
        response = build_conceptual_compare_response(
            "What's the difference between an ADR and a PCP?"
        )
        assert "Showing all" not in response
        assert "ADR.00" not in response
        # Should not have 10+ lines (guard against list replay)
        lines = [l for l in response.strip().split("\n") if l.strip()]
        assert len(lines) < 15, "Response looks like a list, not a comparison"

    def test_response_offers_followup(self):
        response = build_conceptual_compare_response(
            "ADR vs PCP"
        )
        assert "list" in response.lower() or "examples" in response.lower()

    def test_three_way_compare(self):
        """Comparing 3 types should include all three."""
        response = build_conceptual_compare_response(
            "compare ADRs, DARs, and principles"
        )
        assert "ADR" in response
        assert "DAR" in response
        assert "Principle" in response or "PCP" in response
