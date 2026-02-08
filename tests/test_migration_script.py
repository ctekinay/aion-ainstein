#!/usr/bin/env python3
"""
Tests for migration script (Phase 3).

Tests the migration logic without requiring a live Weaviate connection.

Usage:
    pytest tests/test_migration_script.py -v
"""

import pytest
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src/scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from src.doc_type_classifier import DocType, classify_adr_document


class TestMigrationLogic:
    """Test migration logic that doesn't require Weaviate."""

    def test_classify_adr_for_migration(self):
        """Test that classifier works for migration use case."""
        # Real ADR
        result = classify_adr_document(
            file_path="/decisions/0027-use-tls.md",
            title="ADR.27: Use TLS for API Communications",
            content="## Context\n\nWe need to secure our APIs..."
        )
        assert result.doc_type == DocType.ADR

    def test_classify_dar_for_migration(self):
        """Test that DAR is classified correctly."""
        result = classify_adr_document(
            file_path="/decisions/0021D-approval.md",
            title="Approval Record",
            content="..."
        )
        assert result.doc_type == DocType.ADR_APPROVAL

    def test_classify_index_for_migration(self):
        """Test that index files are classified correctly."""
        result = classify_adr_document(
            file_path="/decisions/index.md",
            title="Decision Records",
            content="..."
        )
        assert result.doc_type == DocType.INDEX

    def test_classify_template_for_migration(self):
        """Test that templates are classified correctly."""
        result = classify_adr_document(
            file_path="/decisions/0000-template.md",
            title="ADR Template",
            content="{short title}..."
        )
        assert result.doc_type == DocType.TEMPLATE


class TestMigrationStats:
    """Test MigrationStats dataclass."""

    def test_stats_creation(self):
        """Test creating MigrationStats."""
        # Import from scripts module
        from scripts.migrate_doc_type import MigrationStats

        stats = MigrationStats(
            collection="ArchitecturalDecision",
            total_objects=126,
            null_before=126,
            null_after=0,
            updated=126,
            skipped=0,
            errors=0,
            type_counts=Counter({DocType.ADR: 18, DocType.ADR_APPROVAL: 20}),
        )

        assert stats.collection == "ArchitecturalDecision"
        assert stats.total_objects == 126
        assert stats.null_before == 126
        assert stats.null_after == 0


class TestCollectionTypeMapping:
    """Test collection type mapping."""

    def test_adr_collection_mapping(self):
        """Test ADR collection maps to 'adr' type."""
        from scripts.migrate_doc_type import get_collection_type

        assert get_collection_type("ArchitecturalDecision") == "adr"
        assert get_collection_type("ArchitecturalDecision_OpenAI") == "adr"

    def test_principle_collection_mapping(self):
        """Test Principle collection maps to 'principle' type."""
        from scripts.migrate_doc_type import get_collection_type

        assert get_collection_type("Principle") == "principle"
        assert get_collection_type("Principle_OpenAI") == "principle"

    def test_unknown_collection_mapping(self):
        """Test unknown collection maps to 'unknown' type."""
        from scripts.migrate_doc_type import get_collection_type

        assert get_collection_type("UnknownCollection") == "unknown"


class TestExpectedADRClassification:
    """Test expected ADR file classification results.

    These tests validate the expected outcomes for the migration.
    """

    @pytest.mark.parametrize("file_path,expected_type", [
        # Regular ADRs (should be 18 of these)
        ("/decisions/0001-initial-setup.md", DocType.ADR),
        ("/decisions/0027-use-tls.md", DocType.ADR),
        ("/decisions/0030-some-decision.md", DocType.ADR),
        ("/decisions/0031-another-decision.md", DocType.ADR),

        # Approval records (DAR)
        ("/decisions/0021D-approval.md", DocType.ADR_APPROVAL),
        ("/decisions/0030D-approval-record.md", DocType.ADR_APPROVAL),

        # Index files
        ("/decisions/index.md", DocType.INDEX),
        ("/decisions/readme.md", DocType.INDEX),

        # Templates
        ("/decisions/0000-template.md", DocType.TEMPLATE),
        ("/decisions/adr-template.md", DocType.TEMPLATE),
    ])
    def test_expected_classification(self, file_path, expected_type):
        """Test that files are classified as expected for migration."""
        result = classify_adr_document(file_path)
        assert result.doc_type == expected_type, (
            f"Expected {expected_type} for {file_path}, got {result.doc_type}"
        )


class TestMigrationIntegration:
    """Integration tests with mocked Weaviate."""

    def test_migrate_collection_with_mock(self):
        """Test migrate_collection with mocked Weaviate client."""
        from scripts.migrate_doc_type import migrate_collection

        # Create mock client and collection
        mock_client = MagicMock()
        mock_collection = MagicMock()

        # Mock collection existence
        mock_client.collections.exists.return_value = True
        mock_client.collections.get.return_value = mock_collection

        # Mock aggregate for total count
        mock_aggregate = MagicMock()
        mock_aggregate.total_count = 3
        mock_collection.aggregate.over_all.return_value = mock_aggregate

        # Mock fetch_objects to return test data
        mock_obj1 = MagicMock()
        mock_obj1.uuid = "uuid-1"
        mock_obj1.properties = {
            "file_path": "/decisions/0027-use-tls.md",
            "title": "Use TLS",
            "content": "Context...",
            "doc_type": None,
        }

        mock_obj2 = MagicMock()
        mock_obj2.uuid = "uuid-2"
        mock_obj2.properties = {
            "file_path": "/decisions/0021D-approval.md",
            "title": "Approval",
            "content": "...",
            "doc_type": None,
        }

        mock_obj3 = MagicMock()
        mock_obj3.uuid = "uuid-3"
        mock_obj3.properties = {
            "file_path": "/decisions/index.md",
            "title": "Index",
            "content": "...",
            "doc_type": None,
        }

        mock_results = MagicMock()
        mock_results.objects = [mock_obj1, mock_obj2, mock_obj3]

        # First call returns objects, second call returns empty
        mock_collection.query.fetch_objects.side_effect = [
            mock_results,
            MagicMock(objects=[]),  # For pagination end
            MagicMock(objects=[]),  # For null count verification
        ]

        # Run migration in dry-run mode
        stats = migrate_collection(mock_client, "ArchitecturalDecision", dry_run=True)

        # Verify stats
        assert stats.total_objects == 3
        assert stats.null_before == 3
        assert stats.updated == 3  # All would be updated
        assert stats.skipped == 0
        assert stats.errors == 0

        # Verify type counts
        assert stats.type_counts[DocType.ADR] == 1
        assert stats.type_counts[DocType.ADR_APPROVAL] == 1
        assert stats.type_counts[DocType.INDEX] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
