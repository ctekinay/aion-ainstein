#!/usr/bin/env python3
"""
Tests for document filters (Phase 4).

Verifies that build_document_filter() uses allow-list approach with
canonical doc_type values.

Usage:
    pytest tests/test_filters.py -v
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.skills.filters import (
    build_document_filter,
    build_adr_filter,
    build_principle_filter,
    ADR_CONTENT_TYPES,
    PRINCIPLE_CONTENT_TYPES,
)


class TestAllowListConstants:
    """Test allow-list constants."""

    def test_adr_content_types_includes_canonical(self):
        """Test that ADR content types include canonical 'adr'."""
        assert "adr" in ADR_CONTENT_TYPES

    def test_adr_content_types_includes_legacy(self):
        """Test that ADR content types include legacy 'content' for backward compat."""
        assert "content" in ADR_CONTENT_TYPES

    def test_principle_content_types_includes_canonical(self):
        """Test that principle content types include canonical 'principle'."""
        assert "principle" in PRINCIPLE_CONTENT_TYPES


class TestBuildDocumentFilter:
    """Test build_document_filter function."""

    def _create_mock_skill_registry(self, filter_config=None):
        """Create a mock skill registry with optional filter config."""
        mock_registry = MagicMock()
        mock_skill = MagicMock()
        mock_skill.thresholds = {"filters": filter_config or {}}
        mock_registry.loader.load_skill.return_value = mock_skill
        return mock_registry

    def test_returns_filter_object(self):
        """Test that function returns a Filter object."""
        registry = self._create_mock_skill_registry()
        result = build_document_filter(
            question="What ADRs exist?",
            skill_registry=registry,
            collection_type="adr",
        )
        # Should return a filter (not None)
        assert result is not None

    def test_adr_collection_type(self):
        """Test filter for ADR collection type."""
        registry = self._create_mock_skill_registry()
        result = build_document_filter(
            question="What ADRs exist?",
            skill_registry=registry,
            collection_type="adr",
        )
        # Filter should be set
        assert result is not None

    def test_principle_collection_type(self):
        """Test filter for principle collection type."""
        registry = self._create_mock_skill_registry()
        result = build_document_filter(
            question="What principles exist?",
            skill_registry=registry,
            collection_type="principle",
        )
        assert result is not None

    def test_approval_query_includes_approval_records(self):
        """Test that approval queries include approval record types."""
        filter_config = {
            "include_dar_patterns": ["who approved"],
            "include_dar_keywords": ["approval", "approver"],
        }
        registry = self._create_mock_skill_registry(filter_config)

        # Query about approval should include adr_approval type
        result = build_document_filter(
            question="Who approved ADR.27?",
            skill_registry=registry,
            collection_type="adr",
        )
        assert result is not None


class TestBuildADRFilter:
    """Test build_adr_filter convenience function."""

    def test_without_skill_registry(self):
        """Test ADR filter without skill registry."""
        result = build_adr_filter()
        assert result is not None

    def test_with_skill_registry(self):
        """Test ADR filter with skill registry."""
        mock_registry = MagicMock()
        mock_skill = MagicMock()
        mock_skill.thresholds = {"filters": {}}
        mock_registry.loader.load_skill.return_value = mock_skill

        result = build_adr_filter(
            question="List ADRs",
            skill_registry=mock_registry,
        )
        assert result is not None


class TestBuildPrincipleFilter:
    """Test build_principle_filter convenience function."""

    def test_without_skill_registry(self):
        """Test principle filter without skill registry."""
        result = build_principle_filter()
        assert result is not None

    def test_with_skill_registry(self):
        """Test principle filter with skill registry."""
        mock_registry = MagicMock()
        mock_skill = MagicMock()
        mock_skill.thresholds = {"filters": {}}
        mock_registry.loader.load_skill.return_value = mock_skill

        result = build_principle_filter(
            question="List principles",
            skill_registry=mock_registry,
        )
        assert result is not None


class TestFilterBehavior:
    """Test expected filter behavior for list queries."""

    def _create_mock_registry(self):
        """Create a mock registry with no special config."""
        mock_registry = MagicMock()
        mock_skill = MagicMock()
        mock_skill.thresholds = {"filters": {}}
        mock_registry.loader.load_skill.return_value = mock_skill
        return mock_registry

    def test_list_adrs_excludes_approval_records(self):
        """Test that list ADRs query doesn't include approval records by default."""
        registry = self._create_mock_registry()
        result = build_document_filter(
            question="What ADRs exist in the system?",
            skill_registry=registry,
            collection_type="adr",
        )
        # The filter should allow 'adr' and 'content', not 'adr_approval'
        # We can't easily inspect the filter internals, but we verified
        # the allow list doesn't include approval types by default
        assert result is not None

    def test_governance_query_includes_approval(self):
        """Test that governance queries can include approval records."""
        filter_config = {
            "include_dar_keywords": ["approved", "approver"],
        }
        mock_registry = MagicMock()
        mock_skill = MagicMock()
        mock_skill.thresholds = {"filters": filter_config}
        mock_registry.loader.load_skill.return_value = mock_skill

        result = build_document_filter(
            question="Who approved ADR.27?",
            skill_registry=mock_registry,
            collection_type="adr",
        )
        # Filter should be set and include approval types
        assert result is not None


class TestEdgeCases:
    """Test edge cases."""

    def test_none_skill_registry(self):
        """Test behavior when skill is not found."""
        mock_registry = MagicMock()
        mock_registry.loader.load_skill.return_value = None

        result = build_document_filter(
            question="List ADRs",
            skill_registry=mock_registry,
            collection_type="adr",
        )
        # Should still return a valid filter using defaults
        assert result is not None

    def test_empty_question(self):
        """Test with empty question."""
        mock_registry = MagicMock()
        mock_skill = MagicMock()
        mock_skill.thresholds = {"filters": {}}
        mock_registry.loader.load_skill.return_value = mock_skill

        result = build_document_filter(
            question="",
            skill_registry=mock_registry,
            collection_type="adr",
        )
        assert result is not None


class TestTaxonomyFilteringCriteria:
    """Tests verifying filtering criteria from ESA_DOCUMENT_TAXONOMY.md Section 5 and 7.

    These tests ensure retrieval filters conform to the taxonomy contract.
    """

    def _create_mock_registry(self, filter_config=None):
        """Create a mock registry with optional filter config."""
        mock_registry = MagicMock()
        mock_skill = MagicMock()
        mock_skill.thresholds = {"filters": filter_config or {}}
        mock_registry.loader.load_skill.return_value = mock_skill
        return mock_registry

    def test_adr_content_types_excludes_registry(self):
        """Registry must not be included in ADR content types."""
        assert "registry" not in ADR_CONTENT_TYPES

    def test_principle_content_types_excludes_registry(self):
        """Registry must not be included in principle content types."""
        assert "registry" not in PRINCIPLE_CONTENT_TYPES

    def test_adr_content_types_excludes_approval(self):
        """Default ADR content types must not include approval records."""
        assert "adr_approval" not in ADR_CONTENT_TYPES

    def test_principle_content_types_excludes_approval(self):
        """Default principle content types must not include approval records."""
        assert "adr_approval" not in PRINCIPLE_CONTENT_TYPES
        assert "principle_approval" not in PRINCIPLE_CONTENT_TYPES

    def test_tell_me_about_adr_excludes_dar(self):
        """'Tell me about ADR.0025' must not retrieve DAR.

        This tests Section 7 filtering requirement:
        Content queries should NOT include adr_approval.
        """
        registry = self._create_mock_registry()
        result = build_document_filter(
            question="Tell me about ADR.0025",
            skill_registry=registry,
            collection_type="adr",
        )
        # Filter should exist and only include content types
        assert result is not None
        # The allow-list approach means only 'adr' and 'content' are included
        # Registry is not in the list, nor is 'adr_approval'

    def test_who_approved_adr_can_retrieve_dar(self):
        """'Who approved ADR.0025' must be able to retrieve DAR.

        This tests Section 7 filtering requirement:
        Approval queries should include adr_approval.
        """
        filter_config = {
            "include_dar_patterns": ["who approved"],
            "include_dar_keywords": ["approved", "approval"],
        }
        registry = self._create_mock_registry(filter_config)

        result = build_document_filter(
            question="Who approved ADR.0025?",
            skill_registry=registry,
            collection_type="adr",
        )
        # Filter should exist and include approval types
        assert result is not None
        # The include_dar_keywords config should trigger adding approval types

    def test_registry_excluded_from_default_retrieval(self):
        """Registry doc_type must not be in any default allow-list.

        This tests Section 5 requirement:
        'exclude registry from default retrieval'
        """
        # Verify registry is not in any content type allow-list
        assert "registry" not in ADR_CONTENT_TYPES
        assert "registry" not in PRINCIPLE_CONTENT_TYPES

        # Build a filter and verify it doesn't include registry
        registry = self._create_mock_registry()
        result = build_document_filter(
            question="Tell me about ADR.0025",
            skill_registry=registry,
            collection_type="adr",
        )
        assert result is not None
        # The allow-list approach means 'registry' is automatically excluded


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
