#!/usr/bin/env python3
"""
Tests for ambiguity-safe query routing (Phase 4 Gap C).

These tests verify:
1. Obvious list queries route to deterministic list path
2. Specific document queries route to semantic/detail path
3. Ambiguous queries are handled safely (not misrouted)
4. Confidence mechanism works correctly

Usage:
    pytest tests/test_query_routing.py -v
"""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.elysia_agents import is_list_query, detect_list_query, ListQueryResult


class TestObviousListQueries:
    """Test that obvious list queries route to list path."""

    @pytest.mark.parametrize("query", [
        "List ADRs",
        "list all adrs",
        "List all ADRs",
        "Show all ADRs",
        "What ADRs exist?",
        "What ADRs do we have?",
        "Which ADRs are available?",
        "Enumerate all architecture decisions",
        "How many ADRs exist?",
        "List principles",
        "Show all principles",
        "What principles do we have?",
    ])
    def test_obvious_list_queries_route_to_list(self, query):
        """Obvious list queries should route to list path."""
        result = detect_list_query(query)

        assert result.is_list is True, f"'{query}' should be detected as list query, got: {result}"
        assert result.confidence in ("high", "medium"), f"'{query}' should have high/medium confidence, got: {result}"

    @pytest.mark.parametrize("query", [
        "List ADRs",
        "What ADRs exist?",
        "Show all ADRs",
    ])
    def test_is_list_query_backward_compat(self, query):
        """Test backward compatibility with is_list_query function."""
        assert is_list_query(query) is True


class TestSpecificDocumentQueries:
    """Test that specific document queries do NOT route to list path."""

    @pytest.mark.parametrize("query", [
        "ADR.0031",
        "ADR 0031",
        "ADR-0031",
        "ADR.31",
        "ADR 31",
        "What is ADR.0031?",
        "Tell me about ADR 31",
        "Explain ADR.0031",
        "What does ADR.0030 say?",
        "Show me the details of ADR 31",
        "PCP.0010",
        "Principle 10",
    ])
    def test_specific_document_routes_to_semantic(self, query):
        """Specific document queries should NOT route to list path."""
        result = detect_list_query(query)

        assert result.is_list is False, f"'{query}' should NOT be detected as list query, got: {result}"

    @pytest.mark.parametrize("query", [
        "ADR.0031",
        "Tell me about ADR 31",
    ])
    def test_is_list_query_returns_false_for_specific(self, query):
        """is_list_query should return False for specific documents."""
        assert is_list_query(query) is False


class TestBorderlineQueries:
    """Test borderline/ambiguous queries that could be misrouted."""

    @pytest.mark.parametrize("query,expected_is_list", [
        # These should NOT go to list route (they reference specific docs)
        ("List ADR.0031", False),
        ("List ADR 31", False),
        ("List ADR.0031 details", False),

        # These should NOT go to list route (they ask about specific topics)
        ("Show ADR decisions about TLS", False),
        ("List ADR status and consequences", False),
        ("What does the ADR about caching say?", False),

        # These SHOULD go to list route (they ask what exists)
        ("List all architecture decisions", True),
        ("What decisions have been made?", True),
        ("Show me all the ADRs", True),
    ])
    def test_borderline_queries_route_correctly(self, query, expected_is_list):
        """Borderline queries should route to correct path."""
        result = detect_list_query(query)

        assert result.is_list == expected_is_list, \
            f"'{query}' should have is_list={expected_is_list}, got: {result}"


class TestConfidenceLevels:
    """Test confidence mechanism for query routing."""

    def test_high_confidence_list_query(self):
        """Strong list indicators should give high confidence."""
        result = detect_list_query("List all ADRs")

        assert result.is_list is True
        assert result.confidence == "high"
        assert result.reason == "strong_list_indicator"

    def test_high_confidence_specific_query(self):
        """Specific document reference should give high confidence NOT list."""
        result = detect_list_query("ADR.0031")

        assert result.is_list is False
        assert result.confidence == "high"
        assert result.reason == "specific_document_reference"

    def test_medium_confidence_list_query(self):
        """Weaker list indicators may give medium confidence."""
        result = detect_list_query("What ADRs do we have?")

        assert result.is_list is True
        assert result.confidence in ("high", "medium")

    def test_list_with_topic_gives_not_list(self):
        """List keyword + topic filter should NOT route to list."""
        result = detect_list_query("List ADR decisions about TLS")

        assert result.is_list is False
        assert result.reason == "list_with_topic_filter"


class TestListQueryResultClass:
    """Test ListQueryResult class behavior."""

    def test_bool_conversion_true(self):
        """ListQueryResult should convert to True when is_list=True."""
        result = ListQueryResult(is_list=True, confidence="high", reason="test")
        assert bool(result) is True

    def test_bool_conversion_false(self):
        """ListQueryResult should convert to False when is_list=False."""
        result = ListQueryResult(is_list=False, confidence="high", reason="test")
        assert bool(result) is False

    def test_repr(self):
        """ListQueryResult should have useful repr."""
        result = ListQueryResult(is_list=True, confidence="high", reason="test")
        repr_str = repr(result)

        assert "is_list=True" in repr_str
        assert "confidence='high'" in repr_str
        assert "reason='test'" in repr_str


class TestPatternPriority:
    """Test that pattern priority is correct (specific > list)."""

    def test_specific_pattern_takes_priority(self):
        """Specific document pattern should take priority over list keywords."""
        # "List" is a list indicator, but "ADR.0031" is specific
        result = detect_list_query("List ADR.0031")

        assert result.is_list is False
        assert result.reason == "specific_document_reference"

    def test_list_keyword_without_specific(self):
        """List keyword should work when no specific doc referenced."""
        result = detect_list_query("List all architecture decisions")

        assert result.is_list is True

    @pytest.mark.parametrize("query", [
        "ADR.0031",
        "adr.0031",
        "ADR 0031",
        "adr 0031",
        "ADR-0031",
        "adr-0031",
        "ADR.31",
        "adr.31",
    ])
    def test_adr_number_patterns(self, query):
        """Various ADR number formats should be detected as specific."""
        result = detect_list_query(query)

        assert result.is_list is False
        assert result.reason == "specific_document_reference"


class TestSemanticQueryPatterns:
    """Test that semantic/content queries are not misrouted."""

    @pytest.mark.parametrize("query", [
        "Tell me about the caching strategy",
        "What does the ADR say about authentication?",
        "Explain the decision about using GraphQL",
        "Details of the TLS implementation decision",
        "Show me the reasoning behind ADR.0027",
    ])
    def test_semantic_queries_not_list(self, query):
        """Semantic content queries should not route to list path."""
        result = detect_list_query(query)

        assert result.is_list is False, f"'{query}' should NOT be list query, got: {result}"


class TestAcceptanceCriteria:
    """Tests verifying specific acceptance criteria from Gap C."""

    def test_list_adrs_routes_to_list(self):
        """'List ADRs' -> list route"""
        assert is_list_query("List ADRs") is True

    def test_adr_0031_routes_to_semantic(self):
        """'ADR.0031' -> semantic/detail route"""
        assert is_list_query("ADR.0031") is False

    def test_list_adr_0031_routes_to_semantic(self):
        """'List ADR.0031' -> should NOT go to list route; it's a detail request"""
        assert is_list_query("List ADR.0031") is False

    def test_show_adr_decisions_about_tls_routes_to_semantic(self):
        """'Show ADR decisions about TLS' -> semantic route"""
        assert is_list_query("Show ADR decisions about TLS") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
