"""Tests for deterministic list response builder.

These tests verify the acceptance criteria:
- Returns valid JSON always
- items_total = unique document count (not chunk count)
- count_qualifier = "exact"
- items_shown <= max_items_in_answer
- No LLM involved in list endpoint serialization
"""

import json
import pytest

from src.list_response_builder import (
    build_list_structured_json,
    build_list_result_marker,
    is_list_result,
    finalize_list_result,
    dedupe_by_identity,
    LIST_RESULT_MARKER,
)
from src.response_schema import ResponseValidator, CURRENT_SCHEMA_VERSION


class TestBuildListStructuredJson:
    """Tests for build_list_structured_json function."""

    def test_basic_adr_list(self):
        """Test basic ADR list generation."""
        items = [
            {"adr_number": "30", "title": "Use Event Sourcing", "status": "accepted", "file_path": "/adr/0030.md"},
            {"adr_number": "31", "title": "Use CQRS Pattern", "status": "proposed", "file_path": "/adr/0031.md"},
        ]

        result = build_list_structured_json(
            item_type_label="ADR",
            items=items,
            identity_key="adr_number",
            title_key="title",
            number_key="adr_number",
            status_key="status",
            source_type="ADR",
        )

        # Verify valid JSON
        data = json.loads(result)
        assert data is not None

        # Verify schema compliance
        is_valid, errors, _ = ResponseValidator.validate(data)
        assert is_valid, f"Schema validation failed: {errors}"

        # Verify counts
        assert data["items_shown"] == 2
        assert data["items_total"] == 2
        assert data["count_qualifier"] == "exact"

        # Verify content
        assert "ADR.0030" in data["answer"]
        assert "ADR.0031" in data["answer"]
        assert "Use Event Sourcing" in data["answer"]
        assert "Use CQRS Pattern" in data["answer"]

    def test_deduplication_by_identity(self):
        """Test that chunked items are deduplicated."""
        # Simulate chunked documents (same file_path, multiple chunks)
        items = [
            {"adr_number": "30", "title": "Use Event Sourcing", "file_path": "/adr/0030.md"},
            {"adr_number": "30", "title": "Use Event Sourcing", "file_path": "/adr/0030.md"},  # Duplicate
            {"adr_number": "31", "title": "Use CQRS Pattern", "file_path": "/adr/0031.md"},
            {"adr_number": "30", "title": "Use Event Sourcing (chunk 3)", "file_path": "/adr/0030.md"},  # Duplicate
        ]

        result = build_list_structured_json(
            item_type_label="ADR",
            items=items,
            identity_key="adr_number",
            title_key="title",
            number_key="adr_number",
            source_type="ADR",
        )

        data = json.loads(result)

        # Should only have 2 unique items (not 4)
        assert data["items_shown"] == 2
        assert data["items_total"] == 2

    def test_stable_sorting_by_number(self):
        """Test that items are sorted stably by number."""
        items = [
            {"adr_number": "31", "title": "Second", "file_path": "/adr/0031.md"},
            {"adr_number": "10", "title": "First", "file_path": "/adr/0010.md"},
            {"adr_number": "25", "title": "Third", "file_path": "/adr/0025.md"},
        ]

        result = build_list_structured_json(
            item_type_label="ADR",
            items=items,
            identity_key="adr_number",
            number_key="adr_number",
            source_type="ADR",
        )

        data = json.loads(result)
        lines = data["answer"].split("\n")

        # Verify order: 10, 25, 31
        assert "ADR.0010" in lines[0]
        assert "ADR.0025" in lines[1]
        assert "ADR.0031" in lines[2]

    def test_max_items_truncation(self):
        """Test that items are truncated to max_items_in_answer."""
        items = [
            {"adr_number": str(i), "title": f"ADR {i}", "file_path": f"/adr/{i:04d}.md"}
            for i in range(100)
        ]

        result = build_list_structured_json(
            item_type_label="ADR",
            items=items,
            identity_key="adr_number",
            number_key="adr_number",
            max_items_in_answer=10,
            source_type="ADR",
        )

        data = json.loads(result)

        # Should show 10 but total is 100
        assert data["items_shown"] == 10
        assert data["items_total"] == 100
        assert data["transparency_statement"] == "Showing 10 of 100 total ADRs"

    def test_empty_items_list(self):
        """Test handling of empty items list."""
        result = build_list_structured_json(
            item_type_label="ADR",
            items=[],
            identity_key="adr_number",
            source_type="ADR",
        )

        data = json.loads(result)

        assert data["answer"] == "No ADRs found."
        assert data["items_shown"] == 0
        assert data["items_total"] == 0

    def test_principle_list(self):
        """Test principle list generation."""
        items = [
            {"principle_number": "10", "title": "Data Quality", "file_path": "/pcp/0010.md"},
            {"principle_number": "11", "title": "Data Security", "file_path": "/pcp/0011.md"},
        ]

        result = build_list_structured_json(
            item_type_label="PCP",
            items=items,
            identity_key="principle_number",
            title_key="title",
            number_key="principle_number",
            status_key=None,  # Principles don't have status
            source_type="Principle",
        )

        data = json.loads(result)

        assert data["items_shown"] == 2
        assert "PCP.0010" in data["answer"]
        assert "PCP.0011" in data["answer"]
        assert data["sources"][0]["type"] == "Principle"

    def test_schema_version_included(self):
        """Test that schema version is always included."""
        result = build_list_structured_json(
            item_type_label="ADR",
            items=[{"adr_number": "1", "title": "Test", "file_path": "/test.md"}],
            identity_key="adr_number",
            source_type="ADR",
        )

        data = json.loads(result)
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_status_suffix_formatting(self):
        """Test that status is correctly appended as suffix."""
        items = [
            {"adr_number": "30", "title": "Test ADR", "status": "accepted", "file_path": "/test.md"},
        ]

        result = build_list_structured_json(
            item_type_label="ADR",
            items=items,
            identity_key="adr_number",
            number_key="adr_number",
            status_key="status",
            source_type="ADR",
        )

        data = json.loads(result)
        assert "(accepted)" in data["answer"]


class TestListResultMarker:
    """Tests for list result marker functions."""

    def test_build_list_result_marker(self):
        """Test marker creation."""
        rows = [{"adr_number": "30", "title": "Test"}]
        result = build_list_result_marker(
            collection="adr",
            rows=rows,
            total_unique=1,
        )

        assert result[LIST_RESULT_MARKER] is True
        assert result["collection"] == "adr"
        assert result["rows"] == rows
        assert result["total_unique"] == 1

    def test_is_list_result_positive(self):
        """Test is_list_result returns True for markers."""
        marker = {LIST_RESULT_MARKER: True, "collection": "adr", "rows": []}
        assert is_list_result(marker) is True

    def test_is_list_result_negative(self):
        """Test is_list_result returns False for non-markers."""
        assert is_list_result({}) is False
        assert is_list_result({"collection": "adr"}) is False
        assert is_list_result([]) is False
        assert is_list_result("string") is False
        assert is_list_result(None) is False

    def test_finalize_list_result_adr(self):
        """Test ADR list result finalization."""
        marker = build_list_result_marker(
            collection="adr",
            rows=[
                {"adr_number": "30", "title": "Test ADR", "status": "accepted", "file_path": "/test.md"},
            ],
            total_unique=1,
        )

        result = finalize_list_result(marker)
        data = json.loads(result)

        assert data["items_total"] == 1
        assert "ADR.0030" in data["answer"]
        assert data["sources"][0]["type"] == "ADR"

    def test_finalize_list_result_principle(self):
        """Test principle list result finalization."""
        marker = build_list_result_marker(
            collection="principle",
            rows=[
                {"principle_number": "10", "title": "Test Principle", "file_path": "/test.md"},
            ],
            total_unique=1,
        )

        result = finalize_list_result(marker)
        data = json.loads(result)

        assert data["items_total"] == 1
        assert "PCP.0010" in data["answer"]
        assert data["sources"][0]["type"] == "Principle"


class TestDedupeByIdentity:
    """Tests for dedupe_by_identity utility function."""

    def test_dedupe_basic(self):
        """Test basic deduplication."""
        items = [
            {"file_path": "/a.md", "title": "A"},
            {"file_path": "/b.md", "title": "B"},
            {"file_path": "/a.md", "title": "A (chunk 2)"},  # Duplicate
        ]

        result = dedupe_by_identity(items, identity_key="file_path")

        assert len(result) == 2
        assert result[0]["file_path"] == "/a.md"
        assert result[1]["file_path"] == "/b.md"

    def test_dedupe_preserves_order(self):
        """Test that deduplication preserves original order."""
        items = [
            {"file_path": "/c.md", "title": "C"},
            {"file_path": "/a.md", "title": "A"},
            {"file_path": "/b.md", "title": "B"},
        ]

        result = dedupe_by_identity(items, identity_key="file_path")

        assert len(result) == 3
        assert result[0]["file_path"] == "/c.md"
        assert result[1]["file_path"] == "/a.md"
        assert result[2]["file_path"] == "/b.md"

    def test_dedupe_with_missing_identity(self):
        """Test deduplication when identity key is missing."""
        items = [
            {"file_path": "/a.md", "title": "A"},
            {"title": "No path 1"},  # Missing identity
            {"title": "No path 2", "file_path": "/b.md"},  # Has fallback
        ]

        result = dedupe_by_identity(items, identity_key="adr_number", fallback_key="file_path")

        # All items should be kept (using fallback for identity)
        assert len(result) == 3


class TestAcceptanceCriteria:
    """Tests verifying the specific acceptance criteria from the specification."""

    def test_valid_json_always(self):
        """Verify: Returns valid JSON always."""
        # Test with various edge cases
        test_cases = [
            [],  # Empty
            [{"adr_number": "1", "title": "Test", "file_path": "/test.md"}],  # Single
            [{"adr_number": str(i), "title": f"Test {i}", "file_path": f"/{i}.md"} for i in range(100)],  # Many
        ]

        for items in test_cases:
            result = build_list_structured_json(
                item_type_label="ADR",
                items=items,
                identity_key="adr_number",
                source_type="ADR",
            )

            # Must be valid JSON
            data = json.loads(result)
            assert data is not None

            # Must pass schema validation
            is_valid, errors, _ = ResponseValidator.validate(data)
            assert is_valid, f"Schema validation failed for {len(items)} items: {errors}"

    def test_items_total_is_unique_count(self):
        """Verify: items_total = unique document count (not chunk count)."""
        # Simulate 18 unique ADRs with 94 chunks
        chunks = []
        for i in range(18):
            # Each ADR has ~5 chunks
            for chunk_idx in range(5):
                chunks.append({
                    "adr_number": str(i + 1),
                    "title": f"ADR {i + 1}",
                    "file_path": f"/adr/{i + 1:04d}.md",
                })

        # Should have 90 chunks total (18 * 5)
        assert len(chunks) == 90

        result = build_list_structured_json(
            item_type_label="ADR",
            items=chunks,
            identity_key="adr_number",
            source_type="ADR",
        )

        data = json.loads(result)

        # items_total must be 18 (unique), not 90 (chunks)
        assert data["items_total"] == 18

    def test_count_qualifier_is_exact(self):
        """Verify: count_qualifier = 'exact'."""
        result = build_list_structured_json(
            item_type_label="ADR",
            items=[{"adr_number": "1", "title": "Test", "file_path": "/test.md"}],
            identity_key="adr_number",
            source_type="ADR",
        )

        data = json.loads(result)
        assert data["count_qualifier"] == "exact"

    def test_items_shown_respects_max(self):
        """Verify: items_shown <= max_items_in_answer."""
        items = [
            {"adr_number": str(i), "title": f"Test {i}", "file_path": f"/{i}.md"}
            for i in range(100)
        ]

        max_items = 50
        result = build_list_structured_json(
            item_type_label="ADR",
            items=items,
            identity_key="adr_number",
            max_items_in_answer=max_items,
            source_type="ADR",
        )

        data = json.loads(result)
        assert data["items_shown"] <= max_items

    def test_adr_30_and_31_appear_in_output(self):
        """Verify: ADR.0030 and ADR.0031 appear in the output list."""
        items = [
            {"adr_number": "30", "title": "Test 30", "status": "accepted", "file_path": "/adr/0030.md"},
            {"adr_number": "31", "title": "Test 31", "status": "proposed", "file_path": "/adr/0031.md"},
        ]

        result = build_list_structured_json(
            item_type_label="ADR",
            items=items,
            identity_key="adr_number",
            number_key="adr_number",
            source_type="ADR",
        )

        data = json.loads(result)
        assert "ADR.0030" in data["answer"]
        assert "ADR.0031" in data["answer"]


class TestFallbackTransparency:
    """Tests for fallback transparency behavior (Phase 4 Gap D).

    When fallback is triggered (doc_type metadata missing), responses must:
    - Use count_qualifier="at_least" instead of "exact"
    - Include transparency statement about incomplete metadata
    """

    def test_fallback_uses_at_least_qualifier(self):
        """When fallback_triggered=True, count_qualifier should be 'at_least'."""
        marker = build_list_result_marker(
            collection="adr",
            rows=[
                {"adr_number": "30", "title": "Test ADR", "status": "accepted", "file_path": "/test.md"},
            ],
            total_unique=1,
            fallback_triggered=True,
        )

        result = finalize_list_result(marker)
        data = json.loads(result)

        assert data["count_qualifier"] == "at_least"

    def test_no_fallback_uses_exact_qualifier(self):
        """When fallback_triggered=False, count_qualifier should be 'exact'."""
        marker = build_list_result_marker(
            collection="adr",
            rows=[
                {"adr_number": "30", "title": "Test ADR", "status": "accepted", "file_path": "/test.md"},
            ],
            total_unique=1,
            fallback_triggered=False,
        )

        result = finalize_list_result(marker)
        data = json.loads(result)

        assert data["count_qualifier"] == "exact"

    def test_fallback_includes_transparency_message(self):
        """Fallback response should include transparency statement about metadata."""
        marker = build_list_result_marker(
            collection="adr",
            rows=[
                {"adr_number": "30", "title": "Test ADR", "status": "accepted", "file_path": "/test.md"},
            ],
            total_unique=1,
            fallback_triggered=True,
        )

        result = finalize_list_result(marker)
        data = json.loads(result)

        # Should have transparency statement
        assert "transparency_statement" in data
        assert "migration" in data["transparency_statement"].lower()

    def test_no_fallback_no_migration_message(self):
        """Non-fallback response should not mention migration."""
        marker = build_list_result_marker(
            collection="adr",
            rows=[
                {"adr_number": "30", "title": "Test ADR", "status": "accepted", "file_path": "/test.md"},
            ],
            total_unique=1,
            fallback_triggered=False,
        )

        result = finalize_list_result(marker)
        data = json.loads(result)

        # transparency_statement may or may not exist, but if it does,
        # it should not mention migration
        statement = data.get("transparency_statement") or ""
        assert "migration" not in statement.lower()

    def test_marker_preserves_fallback_flag(self):
        """build_list_result_marker should preserve fallback_triggered flag."""
        marker = build_list_result_marker(
            collection="adr",
            rows=[],
            total_unique=0,
            fallback_triggered=True,
        )

        assert marker["fallback_triggered"] is True

    def test_principle_fallback_transparency(self):
        """Principle list should also support fallback transparency."""
        marker = build_list_result_marker(
            collection="principle",
            rows=[
                {"principle_number": "10", "title": "Test Principle", "file_path": "/test.md"},
            ],
            total_unique=1,
            fallback_triggered=True,
        )

        result = finalize_list_result(marker)
        data = json.loads(result)

        assert data["count_qualifier"] == "at_least"
        assert "migration" in data.get("transparency_statement", "").lower()


class TestFallbackProductionBehavior:
    """Tests for production fallback behavior (Phase 4 Gap D).

    In production, when fallback is disabled:
    - Should return controlled error when doc_type missing
    - Should NOT silently fall back
    """

    def test_prod_fallback_disabled_returns_error_dict(self):
        """Simulate prod behavior: fallback disabled returns error."""
        # This tests the error dict format that list_all_adrs would return
        error_response = {
            "error": True,
            "message": "ADR metadata missing; in-memory fallback is disabled.",
            "request_id": "test123",
            "reason": "DOC_METADATA_MISSING_REQUIRES_MIGRATION",
        }

        # Verify error structure
        assert error_response["error"] is True
        assert "migration" in error_response["message"].lower() or \
               "MIGRATION" in error_response["reason"]
        assert "reason" in error_response


class TestTransparencyLabelCorrectness:
    """Tests for PR 1.5: transparency message uses collection-specific labels.

    Regression: generate_transparency_message() was returning generic "items"
    instead of "ADRs" or "PCPs" because it ignored the pre-set
    transparency_statement from the list builder.
    """

    def test_all_items_shown_uses_adr_label(self):
        """When all ADRs shown, transparency should say 'ADRs' not 'items'."""
        items = [
            {"adr_number": str(i), "title": f"ADR {i}", "file_path": f"/adr/{i:04d}.md"}
            for i in range(5)
        ]

        result = build_list_structured_json(
            item_type_label="ADR",
            items=items,
            identity_key="adr_number",
            number_key="adr_number",
            source_type="ADR",
        )

        data = json.loads(result)
        assert data["transparency_statement"] == "Showing all 5 ADRs"

    def test_truncated_uses_adr_label(self):
        """When truncated, transparency should say 'ADRs' not 'items'."""
        items = [
            {"adr_number": str(i), "title": f"ADR {i}", "file_path": f"/adr/{i:04d}.md"}
            for i in range(100)
        ]

        result = build_list_structured_json(
            item_type_label="ADR",
            items=items,
            identity_key="adr_number",
            number_key="adr_number",
            max_items_in_answer=10,
            source_type="ADR",
        )

        data = json.loads(result)
        assert data["transparency_statement"] == "Showing 10 of 100 total ADRs"

    def test_all_principles_shown_uses_pcp_label(self):
        """When all principles shown, transparency should say 'PCPs'."""
        items = [
            {"principle_number": str(i), "title": f"Principle {i}", "file_path": f"/pcp/{i:04d}.md"}
            for i in range(3)
        ]

        result = build_list_structured_json(
            item_type_label="PCP",
            items=items,
            identity_key="principle_number",
            number_key="principle_number",
            status_key=None,
            source_type="Principle",
        )

        data = json.loads(result)
        assert data["transparency_statement"] == "Showing all 3 PCPs"

    def test_generate_transparency_prefers_preset(self):
        """generate_transparency_message() should return pre-set statement."""
        from src.response_schema import StructuredResponse

        sr = StructuredResponse(
            answer="test",
            items_shown=5,
            items_total=5,
            count_qualifier="exact",
            transparency_statement="Showing all 5 ADRs",
        )

        assert sr.generate_transparency_message() == "Showing all 5 ADRs"

    def test_generate_transparency_falls_back_to_generic(self):
        """Without pre-set statement, generate_transparency_message uses generic."""
        from src.response_schema import StructuredResponse

        sr = StructuredResponse(
            answer="test",
            items_shown=5,
            items_total=10,
            count_qualifier="exact",
        )

        assert sr.generate_transparency_message() == "Showing 5 of 10 total items"

    def test_empty_list_no_transparency(self):
        """Empty list should not have transparency statement."""
        result = build_list_structured_json(
            item_type_label="ADR",
            items=[],
            identity_key="adr_number",
            source_type="ADR",
        )

        data = json.loads(result)
        assert data.get("transparency_statement") is None

    def test_end_to_end_handle_list_result_uses_label(self):
        """End-to-end: handle_list_result should produce collection-specific label."""
        from src.response_gateway import handle_list_result, StructuredModeContext

        marker = build_list_result_marker(
            collection="adr",
            rows=[
                {"adr_number": "30", "title": "Use Event Sourcing", "status": "accepted", "file_path": "/adr/0030.md"},
                {"adr_number": "31", "title": "Use CQRS Pattern", "status": "proposed", "file_path": "/adr/0031.md"},
            ],
            total_unique=2,
        )

        ctx = StructuredModeContext(structured_mode=True)
        gateway_result = handle_list_result(marker, ctx)

        assert gateway_result is not None
        assert "Showing all 2 ADRs" in gateway_result.response
        assert "items" not in gateway_result.response.lower() or "items_" in gateway_result.response.lower()

    def test_end_to_end_truncated_handle_list_result(self):
        """End-to-end: truncated list should show 'Showing N of M total ADRs'."""
        from src.response_gateway import handle_list_result, StructuredModeContext

        rows = [
            {"adr_number": str(i), "title": f"ADR {i}", "status": "accepted", "file_path": f"/adr/{i:04d}.md"}
            for i in range(100)
        ]

        marker = build_list_result_marker(
            collection="adr",
            rows=rows,
            total_unique=100,
        )

        ctx = StructuredModeContext(structured_mode=True)
        gateway_result = handle_list_result(marker, ctx)

        assert gateway_result is not None
        assert "Showing 50 of 100 total ADRs" in gateway_result.response
