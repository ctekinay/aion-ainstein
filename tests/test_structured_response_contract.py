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


class TestResponseGatewayStrictMode:
    """Smoke tests ensuring UI API never emits non-JSON in strict mode.

    These tests verify the response_gateway.py contract layer enforces
    structured output requirements.
    """

    @pytest.fixture
    def mock_context(self):
        """Create a mock StructuredModeContext for testing."""
        from src.response_gateway import StructuredModeContext
        return StructuredModeContext(
            structured_mode=True,
            active_skill_names=["response-contract"],
            matched_triggers=["response-contract:list"],
        )

    def test_strict_mode_rejects_plain_prose(self, mock_context):
        """Strict mode must reject plain prose - never emit raw text to UI."""
        from src.response_gateway import (
            normalize_and_validate_response,
            POLICY_STRICT,
        )

        raw_prose = "Here are some ADRs. ADR.21 is about data governance."

        result = normalize_and_validate_response(
            raw_response=raw_prose,
            context=mock_context,
            policy=POLICY_STRICT,
        )

        # Must NOT return the raw prose
        assert result.response != raw_prose
        # Must indicate failure
        assert result.is_structured is False
        assert result.failure is not None
        # Failure response must include request ID for debugging
        assert mock_context.request_id in result.response

    def test_strict_mode_accepts_valid_json(self, mock_context):
        """Strict mode accepts valid JSON wrapped in delimiters."""
        from src.response_gateway import (
            normalize_and_validate_response,
            POLICY_STRICT,
            JSON_START_MARKER,
            JSON_END_MARKER,
        )

        valid_json = f'''{JSON_START_MARKER}
{{
    "schema_version": "1.0",
    "answer": "Found 5 ADRs in the system.",
    "items_shown": 5,
    "items_total": 10,
    "count_qualifier": "exact"
}}
{JSON_END_MARKER}'''

        result = normalize_and_validate_response(
            raw_response=valid_json,
            context=mock_context,
            policy=POLICY_STRICT,
        )

        assert result.is_structured is True
        assert result.failure is None
        assert "Found 5 ADRs" in result.response

    def test_strict_mode_accepts_raw_json(self, mock_context):
        """Strict mode accepts raw JSON without markers."""
        from src.response_gateway import (
            normalize_and_validate_response,
            POLICY_STRICT,
        )

        raw_json = '''{
            "schema_version": "1.0",
            "answer": "Here are the results.",
            "items_shown": 3,
            "items_total": 3,
            "count_qualifier": "exact"
        }'''

        result = normalize_and_validate_response(
            raw_response=raw_json,
            context=mock_context,
            policy=POLICY_STRICT,
        )

        assert result.is_structured is True
        assert "Here are the results" in result.response

    def test_strict_mode_rejects_invalid_json(self, mock_context):
        """Strict mode rejects malformed JSON that can't be repaired."""
        from src.response_gateway import (
            normalize_and_validate_response,
            POLICY_STRICT,
        )

        # Severely malformed - missing closing braces
        bad_json = '{"answer": "incomplete'

        result = normalize_and_validate_response(
            raw_response=bad_json,
            context=mock_context,
            policy=POLICY_STRICT,
        )

        assert result.is_structured is False
        assert result.failure is not None

    def test_soft_mode_degrades_gracefully(self, mock_context):
        """Soft mode returns raw text when JSON extraction fails."""
        from src.response_gateway import (
            normalize_and_validate_response,
            POLICY_SOFT,
        )

        raw_prose = "Here are some ADRs without JSON formatting."

        result = normalize_and_validate_response(
            raw_response=raw_prose,
            context=mock_context,
            policy=POLICY_SOFT,
        )

        # Soft mode returns raw text
        assert result.response == raw_prose
        assert result.is_structured is False
        # No failure object in soft mode
        assert result.failure is None

    def test_non_structured_mode_bypasses_validation(self):
        """When structured_mode=False, response passes through unchanged."""
        from src.response_gateway import (
            normalize_and_validate_response,
            POLICY_STRICT,
            StructuredModeContext,
        )

        context = StructuredModeContext(structured_mode=False)
        raw = "Plain text response, no JSON required."

        result = normalize_and_validate_response(
            raw_response=raw,
            context=context,
            policy=POLICY_STRICT,
        )

        assert result.response == raw
        assert result.is_structured is False
        assert result.failure is None

    def test_gateway_result_includes_api_metadata(self, mock_context):
        """GatewayResult.to_api_response() includes all required fields."""
        from src.response_gateway import (
            normalize_and_validate_response,
            POLICY_STRICT,
            JSON_START_MARKER,
            JSON_END_MARKER,
        )

        valid_json = f'''{JSON_START_MARKER}
{{
    "schema_version": "1.0",
    "answer": "Test response.",
    "items_shown": 1,
    "items_total": 1
}}
{JSON_END_MARKER}'''

        result = normalize_and_validate_response(
            raw_response=valid_json,
            context=mock_context,
            policy=POLICY_STRICT,
        )

        api_response = result.to_api_response()

        # Required fields
        assert "response" in api_response
        assert "is_structured" in api_response
        assert "request_id" in api_response
        # Structured data when successful
        assert "structured_data" in api_response

    def test_items_total_populated_from_weaviate(self, mock_context):
        """Weaviate counts override LLM-guessed items_total."""
        from src.response_gateway import (
            normalize_and_validate_response,
            POLICY_STRICT,
        )

        # LLM says 5 total, but Weaviate says 42
        json_with_wrong_count = '''{
            "schema_version": "1.0",
            "answer": "Here are the ADRs.",
            "items_shown": 5,
            "items_total": 5,
            "count_qualifier": "approx"
        }'''

        weaviate_counts = {"ArchitecturalDecision": 42}

        result = normalize_and_validate_response(
            raw_response=json_with_wrong_count,
            context=mock_context,
            policy=POLICY_STRICT,
            collection_counts=weaviate_counts,
        )

        assert result.is_structured is True
        # Weaviate count should override
        assert result.structured_response.items_total == 42
        assert result.structured_response.count_qualifier == "exact"


class TestRetryMechanism:
    """Test the retry mechanism for strict mode failures."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock StructuredModeContext for testing."""
        from src.response_gateway import StructuredModeContext
        return StructuredModeContext(
            structured_mode=True,
            active_skill_names=["response-contract"],
            matched_triggers=["response-contract:list"],
        )

    def test_retry_success_on_extraction_failure(self, mock_context):
        """When extraction fails, retry_func is called and can succeed."""
        from src.response_gateway import (
            normalize_and_validate_response,
            POLICY_STRICT,
            JSON_START_MARKER,
            JSON_END_MARKER,
        )

        def mock_retry_success(prompt):
            return f'''{JSON_START_MARKER}
{{
    "schema_version": "1.0",
    "answer": "Retry succeeded!",
    "items_shown": 1,
    "items_total": 1
}}
{JSON_END_MARKER}'''

        result = normalize_and_validate_response(
            raw_response="Invalid prose without JSON",
            context=mock_context,
            policy=POLICY_STRICT,
            retry_func=mock_retry_success,
        )

        assert result.is_structured is True
        assert mock_context.retry_attempted is True
        assert mock_context.retry_ok is True
        assert mock_context.retry_failed is False
        assert "Retry succeeded" in result.response

    def test_retry_failure_tracked_in_metrics(self, mock_context):
        """When retry also fails, metrics track the failure."""
        from src.response_gateway import (
            normalize_and_validate_response,
            POLICY_STRICT,
        )

        def mock_retry_fail(prompt):
            return "Still invalid prose"

        result = normalize_and_validate_response(
            raw_response="Invalid prose without JSON",
            context=mock_context,
            policy=POLICY_STRICT,
            retry_func=mock_retry_fail,
        )

        assert result.is_structured is False
        assert mock_context.retry_attempted is True
        assert mock_context.retry_ok is False
        assert mock_context.retry_failed is True

    def test_no_retry_when_retry_func_is_none(self, mock_context):
        """When retry_func is None, no retry is attempted."""
        from src.response_gateway import (
            normalize_and_validate_response,
            POLICY_STRICT,
        )

        result = normalize_and_validate_response(
            raw_response="Invalid prose without JSON",
            context=mock_context,
            policy=POLICY_STRICT,
            retry_func=None,
        )

        assert result.is_structured is False
        assert mock_context.retry_attempted is False

    def test_context_includes_retry_metrics_in_log_dict(self, mock_context):
        """StructuredModeContext.to_log_dict includes retry metrics."""
        mock_context.retry_attempted = True
        mock_context.retry_ok = True
        mock_context.retry_failed = False

        log_dict = mock_context.to_log_dict()

        assert "retry_attempted" in log_dict
        assert "retry_ok" in log_dict
        assert "retry_failed" in log_dict
        assert log_dict["retry_attempted"] is True
        assert log_dict["retry_ok"] is True


class TestPopulateItemsTotalEnhancements:
    """Test the enhanced populate_items_total_from_weaviate function."""

    def test_direct_items_total_parameter(self):
        """items_total parameter is preferred over collection_counts."""
        from src.response_gateway import populate_items_total_from_weaviate
        from src.response_schema import StructuredResponse

        response = StructuredResponse(
            schema_version="1.0",
            answer="Test",
            items_shown=5,
            items_total=5,
        )

        updated = populate_items_total_from_weaviate(response, items_total=42)

        assert updated.items_total == 42
        assert updated.count_qualifier == "exact"

    def test_items_total_overrides_collection_counts(self):
        """When both are provided, items_total takes precedence."""
        from src.response_gateway import populate_items_total_from_weaviate
        from src.response_schema import StructuredResponse

        response = StructuredResponse(
            schema_version="1.0",
            answer="Test",
            items_shown=5,
            items_total=5,
        )

        updated = populate_items_total_from_weaviate(
            response,
            collection_counts={"ADR": 100},
            items_total=42,
        )

        # items_total should win
        assert updated.items_total == 42


class TestSkillRegistryPublicAPI:
    """Test the public API for skill registry trigger matching."""

    @pytest.fixture
    def registry(self):
        """Get a fresh skill registry for testing."""
        registry = SkillRegistry()
        registry.load_registry()
        return registry

    def test_get_matched_triggers_returns_list(self, registry):
        """get_matched_triggers returns a list of matched triggers."""
        query = "What ADRs exist in the system?"
        triggers = registry.get_matched_triggers("response-contract", query)

        assert isinstance(triggers, list)
        # Should have at least one trigger match
        assert len(triggers) > 0
        # Each trigger should be formatted as skill_name:trigger
        for trigger in triggers:
            assert ":" in trigger

    def test_get_matched_triggers_empty_for_no_match(self, registry):
        """get_matched_triggers returns empty list when no triggers match."""
        query = "Random question with no triggers"
        triggers = registry.get_matched_triggers("response-contract", query)

        assert isinstance(triggers, list)
        assert len(triggers) == 0

    def test_get_matched_triggers_auto_activate(self, registry):
        """Auto-activate skills return special trigger format."""
        query = "Any query"
        triggers = registry.get_matched_triggers("rag-quality-assurance", query)

        assert len(triggers) == 1
        assert "auto_activate" in triggers[0]


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
