#!/usr/bin/env python3
"""
Tests for SKOSMOS terminology verification (Phase 5 Gap A).

These tests verify:
1. Local vocabulary index loading from TTL files
2. Term lookup with local-first resolution
3. Terminology query detection
4. Abstention logic (only abstain when term cannot be verified)
5. Integration with elysia_agents routing

Usage:
    pytest tests/test_skosmos_verification.py -v
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.weaviate.skosmos_client import (
    SKOSMOSClient,
    LocalVocabularyIndex,
    TermDefinition,
    TermLookupResult,
    get_skosmos_client,
    reset_skosmos_client,
)
from src.elysia_agents import (
    is_terminology_query,
    verify_terminology_in_query,
)
from src.observability import metrics


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def vocab_index():
    """Create a fresh LocalVocabularyIndex for testing."""
    return LocalVocabularyIndex()


@pytest.fixture
def skosmos_client_local():
    """Create a SKOSMOS client in local-only mode for testing."""
    data_path = Path(__file__).parent.parent / "data" / "esa-skosmos"
    return SKOSMOSClient(
        mode="local",
        data_path=data_path,
        lazy_load=False,
    )


@pytest.fixture
def skosmos_client_hybrid():
    """Create a SKOSMOS client in hybrid mode for testing."""
    data_path = Path(__file__).parent.parent / "data" / "esa-skosmos"
    return SKOSMOSClient(
        mode="hybrid",
        data_path=data_path,
        api_url=None,  # No API for unit tests
        lazy_load=False,
    )


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics before each test."""
    metrics.reset_all()
    yield
    metrics.reset_all()


@pytest.fixture(autouse=True)
def reset_client():
    """Reset the global SKOSMOS client singleton."""
    reset_skosmos_client()
    yield
    reset_skosmos_client()


# =============================================================================
# LocalVocabularyIndex Tests
# =============================================================================

class TestLocalVocabularyIndex:
    """Test the local vocabulary index loading and lookup."""

    def test_load_ttl_files(self, vocab_index):
        """Test that TTL files are loaded successfully."""
        data_path = Path(__file__).parent.parent / "data" / "esa-skosmos"
        vocab_index.load(data_path)

        assert vocab_index.is_loaded is True
        assert vocab_index.term_count > 0
        assert len(vocab_index.vocabularies) > 0

    def test_lookup_known_term(self, vocab_index):
        """Test lookup of a known IEC term."""
        data_path = Path(__file__).parent.parent / "data" / "esa-skosmos"
        vocab_index.load(data_path)

        result = vocab_index.lookup("ACLineSegment")

        assert result is not None
        assert result.pref_label.lower() == "aclinesegment"
        assert result.definition != ""

    def test_lookup_case_insensitive(self, vocab_index):
        """Test that lookup is case-insensitive."""
        data_path = Path(__file__).parent.parent / "data" / "esa-skosmos"
        vocab_index.load(data_path)

        result_upper = vocab_index.lookup("ACLINESEGMENT")
        result_lower = vocab_index.lookup("aclinesegment")
        result_mixed = vocab_index.lookup("ACLineSegment")

        assert result_upper is not None
        assert result_lower is not None
        assert result_mixed is not None
        # All should return the same term
        assert result_upper.pref_label == result_lower.pref_label

    def test_lookup_unknown_term(self, vocab_index):
        """Test lookup of an unknown term returns None."""
        data_path = Path(__file__).parent.parent / "data" / "esa-skosmos"
        vocab_index.load(data_path)

        result = vocab_index.lookup("CompletelyMadeUpTerm12345")

        assert result is None

    def test_search_partial_match(self, vocab_index):
        """Test search with partial term matching."""
        data_path = Path(__file__).parent.parent / "data" / "esa-skosmos"
        vocab_index.load(data_path)

        results = vocab_index.search("power", limit=5)

        assert len(results) > 0
        # All results should contain "power" in the key
        for term_def in results:
            assert "power" in term_def.pref_label.lower()

    def test_not_loaded_returns_none(self, vocab_index):
        """Test that lookup returns None when index not loaded."""
        result = vocab_index.lookup("ACLineSegment")

        assert result is None
        assert vocab_index.is_loaded is False


# =============================================================================
# SKOSMOSClient Tests
# =============================================================================

class TestSKOSMOSClient:
    """Test the SKOSMOS client with local-first resolution."""

    def test_lookup_found_local(self, skosmos_client_local):
        """Test successful local lookup."""
        result = skosmos_client_local.lookup_term("ACLineSegment")

        assert result.found is True
        assert result.source == "local"
        assert result.should_abstain is False
        assert result.label != ""
        assert result.definition_text != ""

    def test_lookup_not_found_local_mode(self, skosmos_client_local):
        """Test lookup miss in local-only mode triggers abstention."""
        result = skosmos_client_local.lookup_term("CompletelyMadeUpTerm12345")

        assert result.found is False
        assert result.should_abstain is True
        assert "not found" in result.abstain_reason.lower()

    def test_lookup_hybrid_local_hit(self, skosmos_client_hybrid):
        """Test hybrid mode uses local hit (no API call needed)."""
        result = skosmos_client_hybrid.lookup_term("ACLineSegment")

        assert result.found is True
        assert result.source == "local"
        assert result.should_abstain is False

    def test_lookup_hybrid_local_miss_no_api(self, skosmos_client_hybrid):
        """Test hybrid mode with local miss and no API configured."""
        result = skosmos_client_hybrid.lookup_term("CompletelyMadeUpTerm12345")

        assert result.found is False
        assert result.should_abstain is True
        # Should mention both local and API
        assert "not found" in result.abstain_reason.lower()

    def test_latency_tracked(self, skosmos_client_local):
        """Test that lookup latency is tracked."""
        result = skosmos_client_local.lookup_term("ACLineSegment")

        assert result.latency_ms > 0

    def test_get_stats(self, skosmos_client_local):
        """Test getting client statistics."""
        stats = skosmos_client_local.get_stats()

        assert stats["mode"] == "local"
        assert stats["local_loaded"] is True
        assert stats["local_term_count"] > 0
        assert isinstance(stats["local_vocabularies"], list)
        assert len(stats["local_vocabularies"]) > 0


class TestTermExtractionAndVerification:
    """Test technical term extraction from queries."""

    def test_extract_camel_case_terms(self, skosmos_client_local):
        """Test extraction of CamelCase terms."""
        terms = skosmos_client_local._extract_technical_terms(
            "What is an ACLineSegment and how does PowerTransformer work?"
        )

        assert "ACLineSegment" in terms
        assert "PowerTransformer" in terms

    def test_extract_acronyms(self, skosmos_client_local):
        """Test extraction of acronyms."""
        terms = skosmos_client_local._extract_technical_terms(
            "Explain the CIM model and CGMES standards"
        )

        assert "CIM" in terms
        assert "CGMES" in terms

    def test_extract_iec_standards(self, skosmos_client_local):
        """Test extraction of IEC standard references."""
        terms = skosmos_client_local._extract_technical_terms(
            "This follows IEC61970 and IEC 61968 standards"
        )

        assert any("IEC" in t for t in terms)

    def test_verify_query_terms(self, skosmos_client_local):
        """Test verification of all terms in a query."""
        results = skosmos_client_local.verify_query_terms(
            "What is an ACLineSegment?"
        )

        assert len(results) > 0
        # ACLineSegment should be found
        found_terms = [r for r in results if r.found]
        assert len(found_terms) > 0


# =============================================================================
# Terminology Query Detection Tests
# =============================================================================

class TestTerminologyQueryDetection:
    """Test terminology query detection patterns."""

    @pytest.mark.parametrize("query", [
        "What is ACLineSegment?",
        "What is an ACLineSegment?",
        "what is a PowerTransformer",
        "Define CIM",
        "define CGMES",
        "Definition of ACLineSegment",
        "What does CIMXML mean?",
        "Explain the term CIM",
        "Meaning of ACLineSegment",
    ])
    def test_terminology_queries_detected(self, query):
        """Test that terminology queries are correctly detected."""
        assert is_terminology_query(query) is True

    @pytest.mark.parametrize("query", [
        "List all ADRs",
        "What ADRs exist?",
        "Show me ADR.0031",
        "How do I implement authentication?",
        "Where is the caching configuration?",
        "Create a new principle",
    ])
    def test_non_terminology_queries_not_detected(self, query):
        """Test that non-terminology queries are not detected."""
        assert is_terminology_query(query) is False

    def test_vocabulary_keyword_triggers_detection(self):
        """Test that vocabulary-related keywords trigger detection."""
        assert is_terminology_query("What's in the CIM vocabulary?") is True
        assert is_terminology_query("Search the IEC concepts") is True
        assert is_terminology_query("SKOS definition lookup") is True

    @pytest.mark.parametrize("query", [
        "Why was CIM chosen as the default domain language?",
        "What is the architecture decision about using GraphQL?",
        "How should CIM be used in our platform?",
        "What was decided about IEC 61970?",
        "Why did we select CIM over other standards?",
        "What is the architecture decision on message exchange?",
    ])
    def test_decision_queries_not_treated_as_terminology(self, query):
        """Decision/reasoning queries must not be stolen by vocab route.

        Regression: A3 ('Why was CIM chosen...') and N1 ('What is the
        architecture decision about GraphQL?') were misrouted to vocab
        because 'cim' was a vocab keyword and 'what is' matched a
        terminology pattern.
        """
        assert is_terminology_query(query) is False

    def test_pure_definition_with_vocab_keyword_still_works(self):
        """Pure definition queries with vocab keywords must still route to vocab."""
        assert is_terminology_query("Define CIM") is True
        assert is_terminology_query("Explain the term CIM") is True
        assert is_terminology_query("What is CIM?") is True
        assert is_terminology_query("What does IEC 61970 mean?") is True


# =============================================================================
# Abstention Logic Tests
# =============================================================================

class TestAbstentionLogic:
    """Test abstention logic for terminology verification."""

    def test_local_hit_no_abstain(self, skosmos_client_local):
        """Local hit should never trigger abstention."""
        result = skosmos_client_local.lookup_term("ACLineSegment")

        assert result.found is True
        assert result.should_abstain is False

    def test_local_miss_abstain_in_local_mode(self, skosmos_client_local):
        """Local miss should trigger abstention in local-only mode."""
        result = skosmos_client_local.lookup_term("FakeTermThatDoesNotExist")

        assert result.found is False
        assert result.should_abstain is True
        assert "not found" in result.abstain_reason.lower()

    def test_hybrid_local_hit_api_fail_no_abstain(self):
        """Hybrid mode: local hit + API fail should NOT abstain."""
        data_path = Path(__file__).parent.parent / "data" / "esa-skosmos"

        # Create client with API that will fail
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(
                return_value=MagicMock(
                    get=MagicMock(side_effect=Exception("API error"))
                )
            )

            client = SKOSMOSClient(
                mode="hybrid",
                data_path=data_path,
                api_url="http://fake-api.example.com",
                lazy_load=False,
            )

            # This term exists locally, so should not abstain
            result = client.lookup_term("ACLineSegment")

            assert result.found is True
            assert result.should_abstain is False
            assert result.source == "local"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegrationWithElysiaAgents:
    """Test integration with elysia_agents routing."""

    def test_verify_terminology_in_query_found(self):
        """Test verify_terminology_in_query with known term."""
        should_abstain, reason, results = verify_terminology_in_query(
            "What is an ACLineSegment?"
        )

        # Should not abstain since ACLineSegment exists
        assert should_abstain is False
        assert reason == ""
        # At least one result should be found
        assert any(r.found for r in results)

    def test_verify_terminology_in_query_not_found(self):
        """Test verify_terminology_in_query with unknown term."""
        should_abstain, reason, results = verify_terminology_in_query(
            "What is a CompletelyFakeTermXYZ123?"
        )

        # Should abstain since term doesn't exist
        assert should_abstain is True
        assert reason != ""
        assert "CompletelyFakeTermXYZ123" in reason or "not found" in reason.lower()


# =============================================================================
# Metrics Tests
# =============================================================================

class TestMetricsTracking:
    """Test that metrics are properly tracked."""

    def test_lookup_increments_total(self, skosmos_client_local):
        """Test that lookup increments total counter."""
        initial = metrics.get_counter("skosmos_lookup_total").get()

        skosmos_client_local.lookup_term("ACLineSegment")

        final = metrics.get_counter("skosmos_lookup_total").get()
        assert final > initial

    def test_hit_increments_hit_counter(self, skosmos_client_local):
        """Test that successful lookup increments hit counter."""
        initial = metrics.get_counter("skosmos_hit_total").get({"source": "local"})

        skosmos_client_local.lookup_term("ACLineSegment")

        final = metrics.get_counter("skosmos_hit_total").get({"source": "local"})
        assert final > initial

    def test_miss_increments_miss_counter(self, skosmos_client_local):
        """Test that failed lookup increments miss counter."""
        initial = metrics.get_counter("skosmos_miss_total").get()

        skosmos_client_local.lookup_term("CompletelyMadeUpTerm12345")

        final = metrics.get_counter("skosmos_miss_total").get()
        assert final > initial


# =============================================================================
# Term Lookup Result Tests
# =============================================================================

class TestTermLookupResult:
    """Test TermLookupResult class behavior."""

    def test_label_property(self):
        """Test label property convenience accessor."""
        term_def = TermDefinition(
            uri="http://example.com/term",
            pref_label="TestTerm",
            definition="A test definition",
        )
        result = TermLookupResult(
            found=True,
            term="TestTerm",
            definition=term_def,
            source="local",
        )

        assert result.label == "TestTerm"

    def test_definition_text_property(self):
        """Test definition_text property convenience accessor."""
        term_def = TermDefinition(
            uri="http://example.com/term",
            pref_label="TestTerm",
            definition="A test definition",
        )
        result = TermLookupResult(
            found=True,
            term="TestTerm",
            definition=term_def,
            source="local",
        )

        assert result.definition_text == "A test definition"

    def test_not_found_properties(self):
        """Test properties when term not found."""
        result = TermLookupResult(
            found=False,
            term="UnknownTerm",
            should_abstain=True,
            abstain_reason="Term not found",
        )

        assert result.label == ""
        assert result.definition_text == ""
        assert result.should_abstain is True


# =============================================================================
# Acceptance Criteria Tests (IR0003 Gap A)
# =============================================================================

class TestAcceptanceCriteria:
    """Tests verifying specific acceptance criteria from IR0003 Gap A."""

    def test_local_first_lookup(self, skosmos_client_hybrid):
        """Local lookup is the primary verification path."""
        result = skosmos_client_hybrid.lookup_term("ACLineSegment")

        assert result.found is True
        assert result.source == "local"

    def test_abstain_only_when_unverifiable(self, skosmos_client_hybrid):
        """ABSTAIN applies only when term cannot be verified."""
        # Known term should not trigger abstention
        known_result = skosmos_client_hybrid.lookup_term("ACLineSegment")
        assert known_result.should_abstain is False

        # Unknown term should trigger abstention
        unknown_result = skosmos_client_hybrid.lookup_term("CompletelyMadeUpTerm")
        assert unknown_result.should_abstain is True

    def test_latency_under_threshold(self, skosmos_client_local):
        """Local lookup should be fast (deterministic, low latency)."""
        result = skosmos_client_local.lookup_term("ACLineSegment")

        # Local lookup should be very fast (< 100ms)
        assert result.latency_ms < 100

    def test_testable_offline(self, skosmos_client_local):
        """Local-only client works without network (CI friendly)."""
        # No network calls should be made in local mode
        result = skosmos_client_local.lookup_term("ACLineSegment")

        assert result.found is True
        assert result.source == "local"


# =============================================================================
# Cross-Domain Query Detection Tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
