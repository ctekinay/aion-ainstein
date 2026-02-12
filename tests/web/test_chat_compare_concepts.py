"""Web chat regression: concept comparison queries must return definitions, not list dumps.

Key assertion: "What's the difference between an ADR and a PCP?" must:
  - Contain definitions for BOTH types
  - NOT call list_all_adrs
  - NOT produce a numbered list of documents

NOTE: These tests validate the intent_router and handle_compare_concepts offline.
They do NOT require a running web server or Weaviate instance.
"""

import re
import pytest

from src.intent_router import (
    heuristic_classify,
    handle_compare_concepts,
    Intent,
    EntityScope,
)


class TestCompareConceptsConversation:
    """Validate concept comparison routing and response quality."""

    def test_difference_adr_pcp_intent(self):
        """'What's the difference between an ADR and a PCP?' → COMPARE_CONCEPTS."""
        d = heuristic_classify("So, what's the difference between an ADR and a PCP?")
        assert d.intent == Intent.COMPARE_CONCEPTS
        assert d.intent != Intent.LIST

    def test_difference_adr_pcp_response_contains_both_definitions(self):
        """Response must contain definitions for both ADR and PCP."""
        response = handle_compare_concepts(
            "So, what's the difference between an ADR and a PCP?"
        )
        # Must mention ADR
        assert "ADR" in response
        assert "decision" in response.lower()

        # Must mention PCP/Principle
        assert "PCP" in response or "Principle" in response
        assert "principle" in response.lower() or "guiding" in response.lower()

    def test_difference_adr_pcp_response_not_list_dump(self):
        """Response must NOT look like a list of specific ADR documents."""
        response = handle_compare_concepts(
            "So, what's the difference between an ADR and a PCP?"
        )
        # Must NOT have: "1. ADR.0012 - Use CIM..." style list items
        numbered_adr_lines = re.findall(
            r"^\s*\d+\.\s+\*?\*?ADR\.\d{4}", response, re.MULTILINE
        )
        assert len(numbered_adr_lines) == 0, (
            f"Response contains numbered ADR list items: {numbered_adr_lines}"
        )

        # Must NOT have: "- ADR.0012" bullet list
        bullet_adr_lines = re.findall(
            r"^-\s+\*?\*?ADR\.\d{4}", response, re.MULTILINE
        )
        assert len(bullet_adr_lines) == 0, (
            f"Response contains bullet ADR list items: {bullet_adr_lines}"
        )

    def test_difference_adr_dar_response(self):
        """ADR vs DAR comparison should define both types."""
        response = handle_compare_concepts("What's the difference between ADR and DAR?")
        assert "ADR" in response
        assert "DAR" in response
        assert "approval" in response.lower()
        assert "decision" in response.lower()

    def test_what_is_a_dar_gives_definition(self):
        """'What is a DAR?' should route to COMPARE_CONCEPTS and give definition."""
        d = heuristic_classify("What is a DAR?")
        assert d.intent == Intent.COMPARE_CONCEPTS

        response = handle_compare_concepts("What is a DAR?")
        assert "DAR" in response
        assert "approval" in response.lower()

    def test_all_three_types_compared(self):
        """Comparing ADR + PCP + DAR should include all three."""
        response = handle_compare_concepts(
            "Compare ADRs, PCPs, and DARs"
        )
        assert "ADR" in response
        assert "PCP" in response or "Principle" in response
        assert "DAR" in response


class TestConceptComparisonNegatives:
    """Negative tests to prevent regressions."""

    def test_list_adrs_is_not_compare(self):
        """'List all ADRs' must route to LIST, not COMPARE_CONCEPTS."""
        d = heuristic_classify("List all ADRs")
        assert d.intent == Intent.LIST
        assert d.intent != Intent.COMPARE_CONCEPTS

    def test_show_me_dars_is_not_compare(self):
        """'Show me DARs' must route to LIST, not COMPARE_CONCEPTS."""
        d = heuristic_classify("Show me DARs")
        assert d.intent == Intent.LIST

    def test_who_approved_is_not_compare(self):
        """'Who approved ADR.0025?' must route to LOOKUP_APPROVAL."""
        d = heuristic_classify("Who approved ADR.0025?")
        assert d.intent == Intent.LOOKUP_APPROVAL
        assert d.intent != Intent.COMPARE_CONCEPTS
