#!/usr/bin/env python3
"""
Tests for document type classifier (Phase 2).

Acceptance criteria:
- Classifier returns deterministic doc_type for all filename patterns
- ADR.0027-use-tls.md -> adr
- 0021D-approval.md -> adr_approval
- template.md -> template
- index.md, readme.md -> index

Usage:
    pytest tests/test_doc_type_classifier.py -v
"""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.doc_type_classifier import (
    DocType,
    ClassificationResult,
    classify_adr_document,
    classify_principle_document,
    classify_document,
    doc_type_from_legacy,
    DAR_FILENAME_PATTERN,
)


class TestDocTypeConstants:
    """Test DocType constants and helper methods."""

    def test_all_types_returns_list(self):
        """Test that all_types returns expected types."""
        types = DocType.all_types()
        assert isinstance(types, list)
        assert DocType.ADR in types
        assert DocType.ADR_APPROVAL in types
        assert DocType.TEMPLATE in types
        assert DocType.INDEX in types
        assert DocType.UNKNOWN in types

    def test_content_types_excludes_metadata(self):
        """Test that content_types excludes non-content documents."""
        content = DocType.content_types()
        assert DocType.ADR in content
        assert DocType.PRINCIPLE in content
        assert DocType.ADR_APPROVAL not in content
        assert DocType.TEMPLATE not in content
        assert DocType.INDEX not in content

    def test_excluded_types_has_expected_types(self):
        """Test that excluded_types contains metadata documents."""
        excluded = DocType.excluded_types()
        assert DocType.ADR_APPROVAL in excluded
        assert DocType.TEMPLATE in excluded
        assert DocType.INDEX in excluded
        assert DocType.ADR not in excluded


class TestDARPattern:
    """Test DAR filename pattern recognition."""

    @pytest.mark.parametrize("filename,expected", [
        ("0021D-approval.md", True),
        ("0021d-approval.md", True),
        ("0001D-something.md", True),
        ("9999D-test.md", True),
        ("0021-approval.md", False),  # No 'D' suffix
        ("021D-approval.md", False),   # Only 3 digits
        ("00021D-approval.md", False), # 5 digits
        ("ADR-0021.md", False),        # Wrong format
        ("index.md", False),
    ])
    def test_dar_pattern_matching(self, filename, expected):
        """Test DAR filename pattern matches correctly."""
        result = bool(DAR_FILENAME_PATTERN.match(filename.lower()))
        assert result == expected, f"Pattern match failed for {filename}"


class TestADRClassification:
    """Test ADR document classification."""

    # =========================================================================
    # Filename-based classification (highest priority)
    # =========================================================================

    @pytest.mark.parametrize("filename,expected_type", [
        # Actual ADRs
        ("0027-use-tls.md", DocType.ADR),
        ("0030-some-decision.md", DocType.ADR),
        ("0031-another-decision.md", DocType.ADR),
        ("0001-initial-setup.md", DocType.ADR),

        # Decision Approval Records
        ("0021D-approval.md", DocType.ADR_APPROVAL),
        ("0021d-approval.md", DocType.ADR_APPROVAL),
        ("0030D-approval-record.md", DocType.ADR_APPROVAL),

        # Index files
        ("index.md", DocType.INDEX),
        ("readme.md", DocType.INDEX),
        ("overview.md", DocType.INDEX),
        ("_index.md", DocType.INDEX),

        # Template files
        ("template.md", DocType.TEMPLATE),
        ("adr-template.md", DocType.TEMPLATE),
        ("decision-template.md", DocType.TEMPLATE),
        ("0000-template.md", DocType.TEMPLATE),
    ])
    def test_filename_classification(self, filename, expected_type):
        """Test classification by filename pattern."""
        result = classify_adr_document(f"/path/to/{filename}")
        assert result.doc_type == expected_type, (
            f"Expected {expected_type} for {filename}, got {result.doc_type}. "
            f"Reason: {result.reason}"
        )

    def test_adr_0027_classifies_as_adr(self):
        """ADR.0027 (use-tls) must classify as 'adr'."""
        result = classify_adr_document("0027-use-tls.md")
        assert result.doc_type == DocType.ADR
        assert result.confidence == "default"

    def test_0021d_classifies_as_adr_approval(self):
        """0021D-approval.md must classify as 'adr_approval'."""
        result = classify_adr_document("0021D-approval.md")
        assert result.doc_type == DocType.ADR_APPROVAL
        assert result.confidence == "filename"

    # =========================================================================
    # Title-based classification
    # =========================================================================

    def test_template_in_title(self):
        """Title containing 'template' should classify as template."""
        result = classify_adr_document(
            "0000-adr.md",
            title="ADR Template for New Decisions"
        )
        assert result.doc_type == DocType.TEMPLATE
        assert result.confidence == "title"

    def test_index_like_title(self):
        """Title indicating index document should classify as index."""
        result = classify_adr_document(
            "decisions.md",
            title="Decision Approval Record List"
        )
        assert result.doc_type == DocType.INDEX
        assert result.confidence == "title"

    # =========================================================================
    # Content-based classification
    # =========================================================================

    def test_template_content_indicators(self):
        """Content with template placeholders should classify as template."""
        template_content = """
        # {short title}

        ## Context and Problem Statement

        {problem statement}

        ## Decision Outcome

        {decision outcome}
        """
        result = classify_adr_document(
            "0000-new-adr.md",
            content=template_content
        )
        assert result.doc_type == DocType.TEMPLATE
        assert result.confidence == "content"

    def test_jinja_template_content(self):
        """Content with Jinja templates should classify as template."""
        result = classify_adr_document(
            "0000-test.md",
            content="Hello {{ name }}, this is a template"
        )
        assert result.doc_type == DocType.TEMPLATE
        assert result.confidence == "content"

    # =========================================================================
    # Default classification
    # =========================================================================

    def test_normal_adr_classifies_as_adr(self):
        """Normal ADR without special patterns classifies as adr."""
        result = classify_adr_document(
            "0027-use-tls-for-api.md",
            title="ADR.27: Use TLS for all API Communications",
            content="## Context\n\nWe need to secure our APIs..."
        )
        assert result.doc_type == DocType.ADR
        assert result.confidence == "default"


class TestPrincipleClassification:
    """Test principle document classification."""

    @pytest.mark.parametrize("filename,expected_type", [
        # Actual principles
        ("0010-data-quality.md", DocType.PRINCIPLE),
        ("0001-api-first.md", DocType.PRINCIPLE),

        # Approval records
        ("0010D-approval.md", DocType.ADR_APPROVAL),

        # Index files
        ("index.md", DocType.INDEX),
        ("readme.md", DocType.INDEX),

        # Templates
        ("principle-template.md", DocType.TEMPLATE),
        ("template.md", DocType.TEMPLATE),
    ])
    def test_principle_filename_classification(self, filename, expected_type):
        """Test principle classification by filename."""
        result = classify_principle_document(f"/principles/{filename}")
        assert result.doc_type == expected_type


class TestUnifiedClassifier:
    """Test the unified classify_document function."""

    def test_adr_collection_type(self):
        """Test classification with adr collection type."""
        result = classify_document(
            "0027-use-tls.md",
            collection_type="adr"
        )
        assert result.doc_type == DocType.ADR

    def test_principle_collection_type(self):
        """Test classification with principle collection type."""
        result = classify_document(
            "0010-quality.md",
            collection_type="principle"
        )
        assert result.doc_type == DocType.PRINCIPLE

    def test_architecturaldecision_collection_type(self):
        """Test classification with full collection name."""
        result = classify_document(
            "0027-use-tls.md",
            collection_type="ArchitecturalDecision"
        )
        assert result.doc_type == DocType.ADR

    def test_unknown_collection_type(self):
        """Test classification with unknown collection type."""
        result = classify_document(
            "document.md",
            collection_type="policy"
        )
        assert result.doc_type == DocType.UNKNOWN


class TestLegacyConversion:
    """Test conversion from legacy doc_type values."""

    @pytest.mark.parametrize("legacy,canonical", [
        ("content", DocType.ADR),
        ("decision_approval_record", DocType.ADR_APPROVAL),
        ("template", DocType.TEMPLATE),
        ("index", DocType.INDEX),
        # Pass-through for already canonical
        ("adr", DocType.ADR),
        ("adr_approval", DocType.ADR_APPROVAL),
        ("principle", DocType.PRINCIPLE),
        # Unknown values
        ("unknown_type", DocType.UNKNOWN),
        ("", DocType.UNKNOWN),
    ])
    def test_legacy_conversion(self, legacy, canonical):
        """Test legacy doc_type conversion to canonical."""
        result = doc_type_from_legacy(legacy)
        assert result == canonical


class TestClassificationResult:
    """Test ClassificationResult dataclass."""

    def test_result_has_all_fields(self):
        """Test that result has doc_type, confidence, and reason."""
        result = classify_adr_document("0027-use-tls.md")
        assert hasattr(result, "doc_type")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reason")
        assert result.doc_type is not None
        assert result.confidence in ("filename", "title", "content", "default")
        assert len(result.reason) > 0


class TestEdgeCases:
    """Test edge cases and potential issues."""

    def test_path_object_input(self):
        """Test that Path objects work as input."""
        result = classify_adr_document(Path("/docs/decisions/0027-use-tls.md"))
        assert result.doc_type == DocType.ADR

    def test_empty_title_and_content(self):
        """Test classification with no title or content."""
        result = classify_adr_document("0027-decision.md", title="", content="")
        assert result.doc_type == DocType.ADR

    def test_case_insensitive_dar_pattern(self):
        """Test that DAR pattern is case-insensitive."""
        result1 = classify_adr_document("0021D-approval.md")
        result2 = classify_adr_document("0021d-approval.md")
        assert result1.doc_type == result2.doc_type == DocType.ADR_APPROVAL

    def test_mixed_case_index(self):
        """Test that index detection is case-insensitive."""
        result = classify_adr_document("INDEX.md")
        assert result.doc_type == DocType.INDEX

    def test_full_path_extraction(self):
        """Test that only filename is used from full path."""
        result = classify_adr_document("/long/path/to/decisions/0027-tls.md")
        assert result.doc_type == DocType.ADR

        result2 = classify_adr_document("/templates/0021D-approval.md")
        assert result2.doc_type == DocType.ADR_APPROVAL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
