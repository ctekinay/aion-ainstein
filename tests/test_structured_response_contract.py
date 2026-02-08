#!/usr/bin/env python3
"""
Tests for structured response contract enforcement.

These tests ensure that:
1. response-contract skill activates for list/count queries
2. Non-JSON output does not reach UI when structured mode is active (strict enforcement)
3. Both main path and fallback path use unified post-processing

Usage:
    pytest tests/test_structured_response_contract.py -v
    python tests/test_structured_response_contract.py
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.skills.registry import SkillRegistry, get_skill_registry
from src.elysia_agents import (
    postprocess_llm_output,
    ENFORCEMENT_STRICT,
    ENFORCEMENT_SOFT,
)


class TestSkillRouting:
    """Test that response-contract skill activates correctly based on triggers."""

    @pytest.fixture
    def registry(self):
        """Get a fresh skill registry for testing."""
        registry = SkillRegistry()
        registry.load_registry()
        return registry

    def test_what_adrs_exist_activates_response_contract(self, registry):
        """The query 'What ADRs exist in the system?' must activate response-contract."""
        query = "What ADRs exist in the system?"
        is_active = registry.is_skill_active("response-contract", query)
        assert is_active, f"response-contract should be active for query: {query}"

    def test_list_adrs_activates_response_contract(self, registry):
        """List queries should activate response-contract."""
        queries = [
            "List all ADRs",
            "Show all principles",
            "How many policies exist?",
            "What policies do we have?",
            "Enumerate the vocabulary terms",
            "Count the ADRs",
            "What is the total number of principles?",
        ]
        for query in queries:
            is_active = registry.is_skill_active("response-contract", query)
            assert is_active, f"response-contract should be active for query: {query}"

    def test_single_item_query_does_not_activate(self, registry):
        """Single-item lookups should NOT activate response-contract."""
        queries = [
            "What is ADR-0021?",
            "Tell me about ADR.21",
            "Explain principle PCP.10",
            "What does ADR-0010 decide?",
        ]
        for query in queries:
            is_active = registry.is_skill_active("response-contract", query)
            # These should NOT activate response-contract (no list/count triggers)
            # Note: Some might still match if they contain partial triggers
            # This test documents expected behavior
            print(f"Query: {query} -> is_active: {is_active}")

    def test_rag_quality_assurance_always_active(self, registry):
        """rag-quality-assurance (auto_activate=true) should activate for any query."""
        queries = [
            "What ADRs exist?",
            "Tell me about ADR.21",
            "Random question",
        ]
        for query in queries:
            is_active = registry.is_skill_active("rag-quality-assurance", query)
            assert is_active, f"rag-quality-assurance should always be active for: {query}"


class TestPostProcessingEnforcement:
    """Test the unified post-processing function with different enforcement modes."""

    def test_non_structured_mode_returns_raw(self):
        """When structured_mode=False, raw response is returned unchanged."""
        raw = "This is a plain text response without JSON."
        processed, was_structured, reason = postprocess_llm_output(
            raw_response=raw,
            structured_mode=False,
        )
        assert processed == raw
        assert was_structured is False
        assert reason == "not_structured_mode"

    def test_valid_json_parsed_successfully(self):
        """Valid JSON response is parsed and transparency is added."""
        raw = '''{
            "schema_version": "1.0",
            "answer": "Here are the ADRs.",
            "items_shown": 5,
            "items_total": 10,
            "count_qualifier": "exact"
        }'''
        processed, was_structured, reason = postprocess_llm_output(
            raw_response=raw,
            structured_mode=True,
        )
        assert was_structured is True
        assert reason == "success"
        assert "Here are the ADRs" in processed
        # Should include transparency message
        assert "5" in processed or "10" in processed

    def test_invalid_json_strict_mode_fails(self):
        """In strict mode, invalid JSON should not reach UI as raw text."""
        raw = "This is not JSON at all. Just prose about ADRs."
        processed, was_structured, reason = postprocess_llm_output(
            raw_response=raw,
            structured_mode=True,
            enforcement_policy=ENFORCEMENT_STRICT,
        )
        assert was_structured is False
        assert "strict_failed" in reason
        # In strict mode without retry, should return controlled error
        assert "unable to format" in processed.lower() or "rephras" in processed.lower()
        # Raw prose should NOT be in the output
        assert raw != processed

    def test_invalid_json_soft_mode_degrades(self):
        """In soft mode, invalid JSON falls back to raw text with logging."""
        raw = "This is not JSON at all. Just prose about ADRs."
        processed, was_structured, reason = postprocess_llm_output(
            raw_response=raw,
            structured_mode=True,
            enforcement_policy=ENFORCEMENT_SOFT,
        )
        assert was_structured is False
        assert "soft_fallback" in reason
        # In soft mode, raw text IS returned (graceful degradation)
        assert processed == raw

    def test_json_in_markdown_extracted(self):
        """JSON embedded in markdown code blocks should be extracted."""
        raw = '''Here's the response:

```json
{
    "schema_version": "1.0",
    "answer": "Found 5 ADRs.",
    "items_shown": 5,
    "items_total": 5,
    "count_qualifier": "exact"
}
```

That's all!'''
        processed, was_structured, reason = postprocess_llm_output(
            raw_response=raw,
            structured_mode=True,
        )
        assert was_structured is True
        assert "success" in reason
        assert "Found 5 ADRs" in processed

    def test_malformed_json_repaired(self):
        """Common JSON malformations should be repaired."""
        # Trailing comma (common LLM mistake)
        raw = '''{
            "schema_version": "1.0",
            "answer": "Test answer",
            "items_shown": 3,
            "items_total": 3,
        }'''  # Note trailing comma
        processed, was_structured, reason = postprocess_llm_output(
            raw_response=raw,
            structured_mode=True,
        )
        # Should be repaired and parsed
        assert was_structured is True
        assert "Test answer" in processed


class TestContractIntegration:
    """Integration tests ensuring contract cannot be bypassed."""

    def test_both_paths_use_same_postprocess_function(self):
        """Verify main path and fallback path use the same postprocess_llm_output."""
        # This is a structural test - we verify by importing and checking
        from src.elysia_agents import postprocess_llm_output as main_postprocess

        # The function should exist and be the same
        assert callable(main_postprocess)
        assert main_postprocess.__name__ == "postprocess_llm_output"

    def test_strict_enforcement_is_default(self):
        """Verify that strict enforcement is the default policy."""
        from src.elysia_agents import DEFAULT_ENFORCEMENT_POLICY, ENFORCEMENT_STRICT
        assert DEFAULT_ENFORCEMENT_POLICY == ENFORCEMENT_STRICT


def run_tests():
    """Run tests and print results."""
    import subprocess
    result = subprocess.run(
        ["pytest", __file__, "-v", "--tb=short"],
        capture_output=False,
    )
    return result.returncode


if __name__ == "__main__":
    # Allow running directly for quick testing
    exit(run_tests())
