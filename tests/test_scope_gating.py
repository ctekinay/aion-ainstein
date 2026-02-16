"""Tests for ESA cue detection and terminology gating.

Verifies that:
1. General-purpose questions (no ESA cues) are detected as out-of-scope
2. ESA-relevant questions are correctly detected as in-scope
3. is_terminology_query() no longer fires for non-ESA "what is X" questions
"""

import pytest

from src.elysia_agents import (
    _has_esa_cues,
    is_terminology_query,
)


class TestEsaCueDetection:
    """_has_esa_cues() correctly identifies ESA-relevant queries."""

    # --- Should have ESA cues ---

    @pytest.mark.parametrize("query", [
        "What ADRs exist?",
        "list all ADRs",
        "Tell me about ADR.0025",
        "Who approved PCP.0020?",
        "What is CIM?",
        "What is IEC 61970?",
        "list DARs",
        "What principles exist?",
        "Show me the data governance policies",
        "What is Alliander's energy system architecture?",
        "Explain the ESA knowledge base",
        "What is AInstein?",
        "list approval records",
        "What is demandable capacity?",
        "architecture decision about TLS",
        # CamelCase CIM/IEC class names (12+ chars via PascalCase, or AC/DC prefix)
        "What is ACLineSegment?",
        "Describe PowerTransformer",
        "What does DCSwitch represent?",
        "Explain TopologicalNode",
    ])
    def test_esa_cues_present(self, query):
        assert _has_esa_cues(query), f"'{query}' should have ESA cues"

    # --- Should NOT have ESA cues ---

    @pytest.mark.parametrize("query", [
        "list your favorite actors",
        "What is love?",
        "How do I make pasta?",
        "Who won the world cup?",
        "Tell me a joke",
        "What is the meaning of life?",
        "list all movies from 2023",
        "How does machine learning work?",
        "What is Python?",
        "Show me the weather forecast",
        # CamelCase that is NOT ESA (short/common words)
        "What is JavaScript?",
        "How does GitHub work?",
    ])
    def test_no_esa_cues(self, query):
        assert not _has_esa_cues(query), f"'{query}' should NOT have ESA cues"


class TestTerminologyGating:
    """is_terminology_query() should only fire for ESA-scoped terms."""

    # --- Should be terminology queries ---

    @pytest.mark.parametrize("query", [
        "What is CIM?",
        "What is IEC 61970?",
        "Define demandable capacity",
        "What does SKOS mean?",
        "vocabulary lookup for grid topology",
        "What is ACLineSegment?",
        "What is PowerTransformer?",
        "What is TopologicalNode?",
    ])
    def test_esa_terminology_detected(self, query):
        assert is_terminology_query(query), f"'{query}' should be terminology"

    # --- Should NOT be terminology queries ---

    @pytest.mark.parametrize("query", [
        "What is love?",
        "What is Python?",
        "What is machine learning?",
        "Define happiness",
        "What does TLS mean?",
        "list your favorite actors",
    ])
    def test_non_esa_not_terminology(self, query):
        assert not is_terminology_query(query), f"'{query}' should NOT be terminology"
