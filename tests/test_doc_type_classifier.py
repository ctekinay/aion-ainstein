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

        # Template files (non-numbered only — numbered files are always ADR)
        ("template.md", DocType.TEMPLATE),
        ("adr-template.md", DocType.TEMPLATE),
        ("decision-template.md", DocType.TEMPLATE),
        # 0000-template.md is numbered → ADR (identity rule overrides template heuristic)
        ("0000-template.md", DocType.ADR),
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
        assert result.confidence == "filename"

    def test_0021d_classifies_as_adr_approval(self):
        """0021D-approval.md must classify as 'adr_approval'."""
        result = classify_adr_document("0021D-approval.md")
        assert result.doc_type == DocType.ADR_APPROVAL
        assert result.confidence == "filename"

    # =========================================================================
    # Title-based classification
    # =========================================================================

    def test_template_in_title_numbered_file(self):
        """Numbered file with 'template' in title should still be ADR (identity rule)."""
        result = classify_adr_document(
            "0000-adr.md",
            title="ADR Template for New Decisions"
        )
        assert result.doc_type == DocType.ADR
        assert result.confidence == "filename"

    def test_template_in_title_non_numbered_file(self):
        """Non-numbered file with 'template' in title should classify as template."""
        result = classify_adr_document(
            "adr-guide.md",
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

    def test_template_content_indicators_numbered_file(self):
        """Numbered file with template placeholders should still be ADR (identity rule)."""
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
        assert result.doc_type == DocType.ADR
        assert result.confidence == "filename"

    def test_template_content_indicators_non_numbered_file(self):
        """Non-numbered file with template placeholders should classify as template."""
        template_content = """
        # {short title}

        ## Context and Problem Statement

        {problem statement}
        """
        result = classify_adr_document(
            "adr-blank.md",
            content=template_content
        )
        assert result.doc_type == DocType.TEMPLATE
        assert result.confidence == "content"

    def test_jinja_template_content_numbered_file(self):
        """Numbered file with Jinja templates should still be ADR (identity rule)."""
        result = classify_adr_document(
            "0000-test.md",
            content="Hello {{ name }}, this is a template"
        )
        assert result.doc_type == DocType.ADR
        assert result.confidence == "filename"

    def test_jinja_template_content_non_numbered_file(self):
        """Non-numbered file with Jinja templates should classify as template."""
        result = classify_adr_document(
            "draft-adr.md",
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
        assert result.confidence == "filename"


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


class TestNumberedFileIdentityRule:
    """Regression tests: numbered files (NNNN-*.md) must ALWAYS be content.

    ADR.0000 and ADR.0001 were misclassified as 'template' because their
    content mentions the word 'template' in prose. The identity rule ensures
    that the filename pattern (NNNN-*.md) is authoritative and overrides
    any content-based heuristics.
    """

    @pytest.mark.parametrize("filename,title,content,expected_type", [
        # ADR.0000 — discusses MADR templates but is itself a real ADR
        (
            "0000-use-markdown-architectural-decision-records.md",
            "Use Markdown Architectural Decision Records",
            "We will use the MADR template format for all ADRs. "
            "The template provides a consistent structure.",
            DocType.ADR,
        ),
        # ADR.0001 — discusses conventions including template usage
        (
            "0001-adr-conventions.md",
            "What conventions to use in writing ADRs?",
            "Follow the template structure. Each ADR should use the template.",
            DocType.ADR,
        ),
        # A numbered file with placeholder tokens — still ADR by identity rule
        (
            "0099-placeholder-adr.md",
            "Placeholder ADR",
            "This ADR discusses {short title} patterns",
            DocType.ADR,
        ),
    ])
    def test_adr_numbered_file_always_content(self, filename, title, content, expected_type):
        """Numbered ADR files must be classified as ADR regardless of content."""
        result = classify_adr_document(filename, title=title, content=content)
        assert result.doc_type == expected_type, (
            f"Expected {expected_type} for {filename}, got {result.doc_type}. "
            f"Reason: {result.reason}"
        )
        assert result.confidence == "filename"

    @pytest.mark.parametrize("filename,title,content,expected_type", [
        # A numbered principle mentioning templates in content
        (
            "0010-data-quality-principle.md",
            "Data Quality",
            "This principle uses the template format for documentation.",
            DocType.PRINCIPLE,
        ),
        # A numbered principle with placeholder-like text
        (
            "0020-api-first.md",
            "API First Principle",
            "Refer to {title} for details.",
            DocType.PRINCIPLE,
        ),
    ])
    def test_principle_numbered_file_always_content(self, filename, title, content, expected_type):
        """Numbered principle files must be classified as PRINCIPLE regardless of content."""
        result = classify_principle_document(filename, title=title, content=content)
        assert result.doc_type == expected_type, (
            f"Expected {expected_type} for {filename}, got {result.doc_type}. "
            f"Reason: {result.reason}"
        )
        assert result.confidence == "filename"

    def test_non_numbered_template_still_detected(self):
        """Non-numbered files with template indicators should still be TEMPLATE."""
        result = classify_adr_document("adr-template.md")
        assert result.doc_type == DocType.TEMPLATE

        result2 = classify_principle_document("principle-template.md")
        assert result2.doc_type == DocType.TEMPLATE

    def test_dar_pattern_still_takes_priority(self):
        """DAR pattern (NNNND-*.md) should still take priority over content rule."""
        result = classify_adr_document("0000D-approval.md")
        assert result.doc_type == DocType.ADR_APPROVAL


class TestIngestionClassifiers:
    """Regression tests for the canonical classifiers used during ingestion.

    These call classify_adr_document / classify_principle_document from
    doc_type_classifier (now the single source of truth used by markdown_loader).
    """

    @pytest.mark.parametrize("filename,content,expected", [
        # ADR.0000 — discusses MADR templates but is a real ADR
        ("0000-use-markdown-architectural-decision-records.md",
         "We use MADR template format. The template provides structure.",
         DocType.ADR),
        # ADR.0001 — discusses conventions including the word "template"
        ("0001-adr-conventions.md",
         "Follow the template structure for each ADR.",
         DocType.ADR),
        # Regular numbered ADR
        ("0025-use-oauth.md",
         "We decided to use OAuth 2.0 for authentication.",
         DocType.ADR),
        # DAR still classified correctly
        ("0025D-approval.md",
         "Approved by DACI committee.",
         DocType.ADR_APPROVAL),
        # Non-numbered template file
        ("adr-template.md",
         "Fill in the template fields.",
         DocType.TEMPLATE),
    ])
    def test_adr_classifier_identity_rule(self, filename, content, expected):
        """ADR classifier respects numbered file identity rule."""
        result = classify_adr_document(Path(filename), title="", content=content)
        assert result.doc_type == expected, (
            f"Expected '{expected}' for {filename}, got '{result.doc_type}'"
        )

    @pytest.mark.parametrize("filename,content,expected", [
        # Numbered principle mentioning "template" in content
        ("0010-data-quality.md",
         "This principle follows the template format.",
         DocType.PRINCIPLE),
        # Numbered principle with placeholder-like text
        ("0020-api-first.md",
         "Refer to {title} for details about API design.",
         DocType.PRINCIPLE),
        # DAR still classified correctly
        ("0010D-approval.md",
         "Approved by governance board.",
         DocType.ADR_APPROVAL),
        # Non-numbered template file
        ("principle-template.md",
         "Fill in the principle fields.",
         DocType.TEMPLATE),
    ])
    def test_principle_classifier_identity_rule(self, filename, content, expected):
        """Principle classifier respects numbered file identity rule."""
        result = classify_principle_document(Path(filename), title="", content=content)
        assert result.doc_type == expected, (
            f"Expected '{expected}' for {filename}, got '{result.doc_type}'"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
