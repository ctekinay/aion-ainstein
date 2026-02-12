"""Tests for definitional doc-type queries.

Verifies that:
1. "What is a DAR?" routes to definition, not listing
2. "What is an ADR?" routes to definition, not listing
3. "list DARs" still routes to listing (not definition)
4. The definitional response contains the correct type description
"""

import pytest

from src.elysia_agents import (
    is_definitional_doc_type_query,
    build_definitional_response,
    _extract_definitional_doc_type,
)


class TestDefinitionalDetection:
    """is_definitional_doc_type_query() correctly identifies definitional queries."""

    # --- Should detect as definitional ---

    @pytest.mark.parametrize("query", [
        "What is a DAR?",
        "What is an ADR?",
        "What is a PCP?",
        "What is a principle?",
        "What is a policy?",
        "What are ADRs?",
        "What are DARs?",
        "Define DAR",
        "Define ADR",
        "What does DAR mean?",
        "What does ADR mean?",
        "What is a DAR? Do you know?",
    ])
    def test_definitional_detected(self, query):
        assert is_definitional_doc_type_query(query), f"'{query}' should be definitional"

    # --- Should NOT detect as definitional ---

    @pytest.mark.parametrize("query", [
        "list DARs",
        "list ADRs",
        "What DARs exist?",
        "show me the ADRs",
        "how about DARs?",
        # Compare queries are handled separately
        "What's the difference between an ADR and a PCP?",
        # Not a doc-type question
        "What is CIM?",
        "What is TLS?",
        "What is love?",
    ])
    def test_definitional_not_detected(self, query):
        assert not is_definitional_doc_type_query(query), f"'{query}' should NOT be definitional"


class TestDocTypeExtraction:
    """_extract_definitional_doc_type() extracts the correct type."""

    @pytest.mark.parametrize("query,expected", [
        ("What is a DAR?", "dar"),
        ("What is an ADR?", "adr"),
        ("What is a PCP?", "pcp"),
        ("What is a principle?", "principle"),
        ("What is a policy?", "policy"),
        ("Define DAR", "dar"),
        ("What does ADR mean?", "adr"),
    ])
    def test_extraction(self, query, expected):
        assert _extract_definitional_doc_type(query) == expected


class TestDefinitionalResponse:
    """build_definitional_response() produces correct content."""

    def test_dar_definition(self):
        response = build_definitional_response("What is a DAR?")
        assert "DAR" in response
        assert "Decision Approval Record" in response
        assert "approved" in response.lower() or "approval" in response.lower()

    def test_adr_definition(self):
        response = build_definitional_response("What is an ADR?")
        assert "ADR" in response
        assert "Architecture Decision Record" in response

    def test_pcp_definition(self):
        response = build_definitional_response("What is a PCP?")
        assert "PCP" in response
        assert "Principle" in response

    def test_response_does_not_list(self):
        """Definitional response must NOT contain a document list."""
        response = build_definitional_response("What is a DAR?")
        assert "ADR.0000D" not in response
        assert "Showing all" not in response
        lines = [l for l in response.strip().split("\n") if l.strip()]
        assert len(lines) < 10

    def test_response_offers_listing(self):
        """Response should offer to list the doc type."""
        response = build_definitional_response("What is a DAR?")
        assert "list" in response.lower()
