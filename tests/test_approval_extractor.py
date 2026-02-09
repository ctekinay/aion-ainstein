"""Tests for deterministic approval extraction from DAR documents.

This module tests the approval_extractor module which parses markdown tables
in DAR files to reliably extract approver information.

Regression tests ensure:
1. "Who approved ADR.0025?" returns Robert-Jan Peters and Laurent van Groningen
2. "Who approved PCP.0010?" returns approvers from PCP.10D
3. Markdown table parsing handles various formats correctly
4. Multiple approval sections are correctly aggregated
"""

import pytest
from pathlib import Path

from src.approval_extractor import (
    parse_markdown_table,
    extract_approvers_from_table,
    extract_metadata_from_table,
    parse_dar_content,
    is_specific_approval_query,
    extract_document_number,
    build_approval_response,
    Approver,
    ApprovalSection,
    ApprovalRecord,
)


# =============================================================================
# Sample DAR Content for Testing
# =============================================================================

ADR_0025D_CONTENT = """---
# Configuration for the Jekyll template "Just the Docs"
#@prefix dct: <http://purl.org/dc/terms>
nav_order: ADR.25D
dct:
  identifier: urn:uuid:f2a3b4c5-d6e7-4f8a-9b0c-1d2e3f4a5b6c
  title: Unify demand response interfaces via open standards
---

# Decision Approval Record List

## 2. ESA approval on improved descriptions

| Name                  | Value                                                |
|-----------------------|------------------------------------------------------|
| Version of ADR        | v1.2.0 (2026-01-30)                                  |
| Decision              | Accepted                                             |
| Decision date         | 2026-01-30                                           |
| Driver (Decision owner)        | System Operations - Energy System Architecture Group |
| Remarks               |  No changes in results, but clarity on intent        |


**Approvers**

| Name | Email | Role | Comments |
|------|-------|------|----------|
| Robert-Jan Peters | robert-jan.peters@alliander.com | Energy System Architect | |
| Laurent van Groningen | laurent.van.groningen@alliander.com | Energy System Architect | |

---


## 1. Creation and ESA Approval of ADR.25

| Name                  | Value                                                |
|-----------------------|------------------------------------------------------|
| Version of ADR        | v1.0.0 (2025-10-20)                                  |
| Decision              | Accepted                                             |
| Decision date         | 2025-10-20                                           |
| Driver (Decision owner)        | System Operations - Energy System Architecture Group |
| Remarks               |                                                      |


**Approvers**

| Name | Email | Role | Comments |
|------|-------|------|----------|
| Robert-Jan Peters | robert-jan.peters@alliander.com | Energy System Architect | |
| Laurent van Groningen | laurent.van.groningen@alliander.com | Energy System Architect | |
"""

PCP_0010D_CONTENT = """---
# Configuration for the Jekyll template "Just the Docs"
#@prefix dct: <http://purl.org/dc/terms>
nav_order: PCP.10D
dct:
  identifier: urn:uuid:1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d
  title: Eventual Consistency by Design
---

# Principle Approval Record List

## 2. Using PCP.10 in collaboration GridScaleX & GaaS development with Siemens

| Name                  | Value                                                |
|-----------------------|------------------------------------------------------|
| Version of principle  | v1.0.0 (2025-10-24)                                  |
| Decision              | Supported                                            |
| Decision date         | 2025-11-19                                           |
| Driver (Decision owner)        | Alliander-Siemens collaboration (Jodocus) architecture group |
| Remarks               |  |


**Approvers**
| Name | Email | Role | Comments |
|------|-------|------|----------|
| Laurent van Groningen | laurent.van.groningen@alliander.com | Energy System Architect  |          |
| Christian Heuer       | heuer.christian@siemens.com         | R&D Lead & Architecture Siemens Grid Software |          |


**Additional Notes**
Decision is to fully support the principle as presented during decision date.

---
## 1. Creation and ESA Approval of PCP.10

| Name                  | Value                                                |
|-----------------------|------------------------------------------------------|
| Version of principle  | v1.0.0 (2025-10-24)                                  |
| Decision              | Accepted                                             |
| Decision date         | 2025-10-30                                           |
| Driver (Decision owner)        | System Operations - Energy System Architecture Group |
| Remarks               | Scope: SO and al data-integrations = minimally chain Beter Benutten Net |

**Approvers**
| Name | Email | Role | Comments |
|------|-------|------|----------|
| Laurent van Groningen | laurent.van.groningen@alliander.com | Energy System Architect  |          |
| Cagri Tekinay         | cagri.tekinay@alliander.com         | Energy System Architect  |          |
"""


# =============================================================================
# Query Detection Tests
# =============================================================================

class TestQueryDetection:
    """Tests for approval query detection and document number extraction."""

    @pytest.mark.parametrize("question,expected", [
        ("Who approved ADR.0025?", True),
        ("Who approved ADR 25?", True),
        ("Who approved ADR-0025?", True),
        ("Who approved PCP.0010?", True),
        ("Who approved principle 10?", True),
        ("Tell me about ADR.0025", False),  # Not an approval query
        ("List all approval records", False),  # List query, not specific
        ("What is the status of ADR.0025?", False),  # Not approval
        ("Who approved the TLS decision?", False),  # No specific number
    ])
    def test_is_specific_approval_query(self, question: str, expected: bool):
        """Test detection of specific approval queries."""
        assert is_specific_approval_query(question) == expected

    @pytest.mark.parametrize("question,expected_type,expected_number", [
        ("Who approved ADR.0025?", "adr", "0025"),
        ("Who approved ADR 25?", "adr", "0025"),
        ("Who approved ADR-25?", "adr", "0025"),
        ("Tell me about ADR.0031", "adr", "0031"),
        ("Who approved PCP.0010?", "principle", "0010"),
        ("Who approved principle 10?", "principle", "0010"),
        ("What about ADR.1?", "adr", "0001"),
        ("No document here", None, None),
    ])
    def test_extract_document_number(self, question: str, expected_type, expected_number):
        """Test document number extraction from queries."""
        doc_type, doc_number = extract_document_number(question)
        assert doc_type == expected_type
        assert doc_number == expected_number


# =============================================================================
# Markdown Table Parsing Tests
# =============================================================================

class TestMarkdownTableParsing:
    """Tests for markdown table parsing."""

    def test_parse_simple_approvers_table(self):
        """Test parsing a simple approvers table."""
        lines = [
            "| Name | Email | Role | Comments |",
            "|------|-------|------|----------|",
            "| John Doe | john@example.com | Architect | Looks good |",
            "| Jane Smith | jane@example.com | Manager | |",
        ]
        rows, end_idx = parse_markdown_table(lines, 0)

        assert len(rows) == 2
        assert rows[0]["name"] == "John Doe"
        assert rows[0]["email"] == "john@example.com"
        assert rows[0]["role"] == "Architect"
        assert rows[0]["comments"] == "Looks good"
        assert rows[1]["name"] == "Jane Smith"
        assert rows[1]["comments"] == ""
        assert end_idx == 4

    def test_parse_metadata_table(self):
        """Test parsing a Name/Value metadata table."""
        lines = [
            "| Name                  | Value                                                |",
            "|-----------------------|------------------------------------------------------|",
            "| Version of ADR        | v1.2.0 (2026-01-30)                                  |",
            "| Decision              | Accepted                                             |",
            "| Decision date         | 2026-01-30                                           |",
        ]
        rows, end_idx = parse_markdown_table(lines, 0)

        assert len(rows) == 3
        metadata = extract_metadata_from_table(rows)
        assert "v1.2.0" in metadata.get("version", "")
        assert metadata.get("decision") == "Accepted"
        assert metadata.get("decision_date") == "2026-01-30"


# =============================================================================
# DAR Content Parsing Tests
# =============================================================================

class TestDARParsing:
    """Tests for full DAR document parsing."""

    def test_parse_adr_0025d_content(self):
        """Test parsing ADR.0025D approval record - regression test."""
        record = parse_dar_content(
            ADR_0025D_CONTENT,
            doc_id="ADR.0025",
            title="Unify demand response interfaces via open standards",
            file_path="0025D-unify-demand-response-interfaces-via-open-standards.md",
        )

        assert record.document_id == "ADR.0025"
        assert len(record.sections) >= 1

        # Get all unique approvers
        all_approvers = record.get_all_approvers()
        approver_names = [a.name for a in all_approvers]

        # CRITICAL REGRESSION TEST: These approvers MUST be found
        assert "Robert-Jan Peters" in approver_names, (
            "Robert-Jan Peters must be in approvers for ADR.0025"
        )
        assert "Laurent van Groningen" in approver_names, (
            "Laurent van Groningen must be in approvers for ADR.0025"
        )

        # Verify emails are extracted
        approver_emails = [a.email for a in all_approvers]
        assert "robert-jan.peters@alliander.com" in approver_emails
        assert "laurent.van.groningen@alliander.com" in approver_emails

    def test_parse_pcp_0010d_content(self):
        """Test parsing PCP.0010D approval record - regression test."""
        record = parse_dar_content(
            PCP_0010D_CONTENT,
            doc_id="PCP.0010",
            title="Eventual Consistency by Design",
            file_path="0010D-eventual-consistency-by-design.md",
        )

        assert record.document_id == "PCP.0010"
        assert len(record.sections) >= 1

        # Get all unique approvers
        all_approvers = record.get_all_approvers()
        approver_names = [a.name for a in all_approvers]

        # CRITICAL REGRESSION TEST: These approvers MUST be found
        assert "Laurent van Groningen" in approver_names, (
            "Laurent van Groningen must be in approvers for PCP.0010"
        )
        assert "Christian Heuer" in approver_names, (
            "Christian Heuer must be in approvers for PCP.0010"
        )
        assert "Cagri Tekinay" in approver_names, (
            "Cagri Tekinay must be in approvers for PCP.0010"
        )

    def test_format_approvers_answer_adr0025(self):
        """Test formatted answer contains required approvers."""
        record = parse_dar_content(
            ADR_0025D_CONTENT,
            doc_id="ADR.0025",
            title="Unify demand response interfaces via open standards",
            file_path="0025D-unify-demand-response-interfaces-via-open-standards.md",
        )

        answer = record.format_approvers_answer()

        # Answer must mention both approvers
        assert "Robert-Jan Peters" in answer
        assert "Laurent van Groningen" in answer
        assert "ADR.0025" in answer

    def test_format_approvers_answer_pcp0010(self):
        """Test formatted answer contains required approvers for PCP.0010."""
        record = parse_dar_content(
            PCP_0010D_CONTENT,
            doc_id="PCP.0010",
            title="Eventual Consistency by Design",
            file_path="0010D-eventual-consistency-by-design.md",
        )

        answer = record.format_approvers_answer()

        # Answer must mention all approvers
        assert "Laurent van Groningen" in answer
        assert "Christian Heuer" in answer
        assert "Cagri Tekinay" in answer
        assert "PCP.0010" in answer


# =============================================================================
# Response Building Tests
# =============================================================================

class TestResponseBuilding:
    """Tests for structured response building."""

    def test_build_approval_response_schema(self):
        """Test that response follows schema contract."""
        record = parse_dar_content(
            ADR_0025D_CONTENT,
            doc_id="ADR.0025",
            title="Test ADR",
            file_path="0025D-test.md",
        )

        response = build_approval_response(record)

        # Check required schema fields
        assert "schema_version" in response
        assert response["schema_version"] == "1.0"
        assert "answer" in response
        assert "items_shown" in response
        assert "items_total" in response
        assert "sources" in response
        assert "approval_record" in response

        # Check approvers are in the answer
        assert "Robert-Jan Peters" in response["answer"]
        assert "Laurent van Groningen" in response["answer"]

        # Check counts match
        assert response["items_shown"] == response["items_total"]
        assert response["items_shown"] >= 2  # At least 2 unique approvers


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_content(self):
        """Test parsing empty content."""
        record = parse_dar_content("", doc_id="ADR.0001")
        assert record.document_id == "ADR.0001"
        assert len(record.sections) == 0
        assert len(record.get_all_approvers()) == 0

    def test_no_approvers_table(self):
        """Test content with no approvers table."""
        content = """
# Some Document

This document has no approvers table.

| Column1 | Column2 |
|---------|---------|
| Value1  | Value2  |
"""
        record = parse_dar_content(content, doc_id="ADR.0001")
        assert len(record.get_all_approvers()) == 0

    def test_malformed_table(self):
        """Test handling of malformed table."""
        content = """
**Approvers**

| Name | Email |
|------|
| John | john@example.com |
"""
        # Should not crash, may extract partial data
        record = parse_dar_content(content, doc_id="ADR.0001")
        # Just verify it doesn't crash
        assert record is not None

    def test_duplicate_approvers_across_sections(self):
        """Test that duplicate approvers are deduplicated."""
        record = parse_dar_content(
            ADR_0025D_CONTENT,
            doc_id="ADR.0025",
        )

        # ADR 0025D has the same approvers in two sections
        # get_all_approvers() should deduplicate them
        all_approvers = record.get_all_approvers()
        names = [a.name for a in all_approvers]

        # Each name should appear only once
        assert names.count("Robert-Jan Peters") == 1
        assert names.count("Laurent van Groningen") == 1


# =============================================================================
# Integration Test Markers
# =============================================================================

@pytest.mark.integration
class TestWeaviateIntegration:
    """Integration tests requiring Weaviate connection.

    These tests are skipped by default. Run with:
        pytest -m integration tests/test_approval_extractor.py
    """

    @pytest.fixture
    def weaviate_client(self):
        """Get Weaviate client if available."""
        try:
            from src.weaviate.client import get_client
            client = get_client()
            yield client
            client.close()
        except Exception:
            pytest.skip("Weaviate not available")

    def test_get_approval_record_adr0025(self, weaviate_client):
        """Integration test: fetch ADR.0025 approvers from Weaviate."""
        from src.approval_extractor import get_approval_record_from_weaviate

        record = get_approval_record_from_weaviate(
            weaviate_client,
            doc_type="adr",
            doc_number="0025",
        )

        if record is None:
            pytest.skip("ADR.0025D not found in Weaviate")

        approvers = record.get_all_approvers()
        names = [a.name for a in approvers]

        assert "Robert-Jan Peters" in names
        assert "Laurent van Groningen" in names

    def test_get_approval_record_pcp0010(self, weaviate_client):
        """Integration test: fetch PCP.0010 approvers from Weaviate."""
        from src.approval_extractor import get_approval_record_from_weaviate

        record = get_approval_record_from_weaviate(
            weaviate_client,
            doc_type="principle",
            doc_number="0010",
        )

        if record is None:
            pytest.skip("PCP.0010D not found in Weaviate")

        approvers = record.get_all_approvers()
        names = [a.name for a in approvers]

        assert "Laurent van Groningen" in names
        assert "Christian Heuer" in names or "Cagri Tekinay" in names


# =============================================================================
# Content Query Detection Tests (Non-Approval)
# =============================================================================

class TestSpecificContentQueryDetection:
    """Tests for is_specific_content_query() function."""

    def test_tell_me_about_adr_is_content_query(self):
        """'Tell me about ADR.0025' should be detected as content query."""
        from src.approval_extractor import is_specific_content_query
        assert is_specific_content_query("Tell me about ADR.0025") is True

    def test_what_is_adr_is_content_query(self):
        """'What is ADR 25?' should be detected as content query."""
        from src.approval_extractor import is_specific_content_query
        assert is_specific_content_query("What is ADR 25?") is True

    def test_explain_adr_is_content_query(self):
        """'Explain ADR.0025' should be detected as content query."""
        from src.approval_extractor import is_specific_content_query
        assert is_specific_content_query("Explain ADR.0025") is True

    def test_details_of_pcp_is_content_query(self):
        """'Details of PCP.0010' should be detected as content query."""
        from src.approval_extractor import is_specific_content_query
        assert is_specific_content_query("Details of PCP.0010") is True

    def test_approval_query_is_not_content_query(self):
        """'Who approved ADR.0025?' should NOT be detected as content query."""
        from src.approval_extractor import is_specific_content_query
        assert is_specific_content_query("Who approved ADR.0025?") is False

    def test_dar_reference_is_not_content_query(self):
        """'Tell me about ADR.0025D' should NOT be detected as content query."""
        from src.approval_extractor import is_specific_content_query
        assert is_specific_content_query("Tell me about ADR.0025D") is False

    def test_list_query_is_not_content_query(self):
        """'List all ADRs' should NOT be detected as content query."""
        from src.approval_extractor import is_specific_content_query
        assert is_specific_content_query("List all ADRs") is False

    def test_generic_question_is_not_content_query(self):
        """'What is the weather?' should NOT be detected as content query."""
        from src.approval_extractor import is_specific_content_query
        assert is_specific_content_query("What is the weather?") is False


class TestSpecificDARQueryDetection:
    """Tests for is_specific_dar_query() function."""

    def test_adr_with_d_suffix_is_dar_query(self):
        """'Tell me about ADR.0025D' should be detected as DAR query."""
        from src.approval_extractor import is_specific_dar_query
        assert is_specific_dar_query("Tell me about ADR.0025D") is True

    def test_pcp_with_d_suffix_is_dar_query(self):
        """'What's in PCP.0010D?' should be detected as DAR query."""
        from src.approval_extractor import is_specific_dar_query
        assert is_specific_dar_query("What's in PCP.0010D?") is True

    def test_lowercase_d_is_dar_query(self):
        """'Show me ADR.0025d' should be detected as DAR query."""
        from src.approval_extractor import is_specific_dar_query
        assert is_specific_dar_query("Show me ADR.0025d") is True

    def test_adr_without_d_is_not_dar_query(self):
        """'Tell me about ADR.0025' should NOT be detected as DAR query."""
        from src.approval_extractor import is_specific_dar_query
        assert is_specific_dar_query("Tell me about ADR.0025") is False

    def test_pcp_without_d_is_not_dar_query(self):
        """'Explain PCP.0010' should NOT be detected as DAR query."""
        from src.approval_extractor import is_specific_dar_query
        assert is_specific_dar_query("Explain PCP.0010") is False


class TestDocumentReferenceExtraction:
    """Tests for extract_document_reference() function."""

    def test_adr_content_reference(self):
        """ADR.0025 should return (adr, 0025, False)."""
        from src.approval_extractor import extract_document_reference
        doc_type, doc_number, is_dar = extract_document_reference("Tell me about ADR.0025")
        assert doc_type == "adr"
        assert doc_number == "0025"
        assert is_dar is False

    def test_adr_dar_reference(self):
        """ADR.0025D should return (adr, 0025, True)."""
        from src.approval_extractor import extract_document_reference
        doc_type, doc_number, is_dar = extract_document_reference("Tell me about ADR.0025D")
        assert doc_type == "adr"
        assert doc_number == "0025"
        assert is_dar is True

    def test_pcp_content_reference(self):
        """PCP.0010 should return (principle, 0010, False)."""
        from src.approval_extractor import extract_document_reference
        doc_type, doc_number, is_dar = extract_document_reference("What is PCP.0010?")
        assert doc_type == "principle"
        assert doc_number == "0010"
        assert is_dar is False

    def test_pcp_dar_reference(self):
        """PCP.0010D should return (principle, 0010, True)."""
        from src.approval_extractor import extract_document_reference
        doc_type, doc_number, is_dar = extract_document_reference("Show me PCP.0010D")
        assert doc_type == "principle"
        assert doc_number == "0010"
        assert is_dar is True

    def test_no_reference(self):
        """Generic question should return (None, None, False)."""
        from src.approval_extractor import extract_document_reference
        doc_type, doc_number, is_dar = extract_document_reference("What is the weather?")
        assert doc_type is None
        assert doc_number is None
        assert is_dar is False


class TestADRContentParsing:
    """Tests for parse_adr_content() function."""

    def test_parse_adr_sections(self):
        """Should extract context, decision, and consequences sections."""
        from src.approval_extractor import parse_adr_content

        content = """# ADR 0025: Test Decision

## Context

This is the context section.
It spans multiple lines.

## Decision

We decided to do this thing.

## Consequences

These are the consequences.
"""
        parsed = parse_adr_content(content)

        assert "context section" in parsed["context"]
        assert "decided to do this" in parsed["decision"]
        assert "consequences" in parsed["consequences"].lower()

    def test_parse_empty_content(self):
        """Empty content should return empty sections."""
        from src.approval_extractor import parse_adr_content

        parsed = parse_adr_content("")
        assert parsed["context"] == ""
        assert parsed["decision"] == ""
        assert parsed["consequences"] == ""


class TestContentRecordFormatting:
    """Tests for ContentRecord.format_summary() method."""

    def test_format_with_all_sections(self):
        """Should format all sections nicely."""
        from src.approval_extractor import ContentRecord

        record = ContentRecord(
            document_id="ADR.0025",
            document_title="Test Decision",
            file_path="/path/to/0025-test.md",
            content="Full content here",
            context="This is context",
            decision="This is the decision",
            consequences="These are consequences",
            status="Accepted",
        )

        summary = record.format_summary()

        assert "ADR.0025" in summary
        assert "Test Decision" in summary
        assert "Status" in summary
        assert "Context" in summary
        assert "Decision" in summary
        assert "Consequences" in summary

    def test_format_without_sections(self):
        """Should use content as fallback when no sections."""
        from src.approval_extractor import ContentRecord

        record = ContentRecord(
            document_id="ADR.0025",
            document_title="Test Decision",
            file_path="/path/to/0025-test.md",
            content="This is the full content without sections.",
        )

        summary = record.format_summary()

        assert "ADR.0025" in summary
        assert "full content without sections" in summary


# =============================================================================
# Integration Tests for Content/DAR Retrieval
# =============================================================================

@pytest.mark.integration
class TestContentRetrievalIntegration:
    """Integration tests for content and DAR retrieval from Weaviate."""

    @pytest.fixture
    def weaviate_client(self):
        """Get Weaviate client if available."""
        try:
            from src.weaviate.client import get_client
            client = get_client()
            yield client
            client.close()
        except Exception:
            pytest.skip("Weaviate not available")

    def test_get_content_record_adr0025(self, weaviate_client):
        """Integration test: fetch ADR.0025 content from Weaviate (not DAR)."""
        from src.approval_extractor import get_content_record_from_weaviate

        record = get_content_record_from_weaviate(
            weaviate_client,
            doc_type="adr",
            doc_number="0025",
        )

        if record is None:
            pytest.skip("ADR.0025 content not found in Weaviate")

        # Should be content doc, not DAR
        assert "D" not in record.document_id or record.document_id == "ADR.0025"
        assert record.file_path
        assert "0025D" not in record.file_path  # Should NOT be the DAR file
        assert record.content

    def test_get_content_record_pcp0010(self, weaviate_client):
        """Integration test: fetch PCP.0010 content from Weaviate (not DAR)."""
        from src.approval_extractor import get_content_record_from_weaviate

        record = get_content_record_from_weaviate(
            weaviate_client,
            doc_type="principle",
            doc_number="0010",
        )

        if record is None:
            pytest.skip("PCP.0010 content not found in Weaviate")

        # Should be content doc, not DAR
        assert "D" not in record.document_id or record.document_id == "PCP.0010"
        assert record.file_path
        assert "0010D" not in record.file_path  # Should NOT be the DAR file
        assert record.content

    def test_get_dar_record_adr0025(self, weaviate_client):
        """Integration test: fetch ADR.0025D (DAR) explicitly from Weaviate."""
        from src.approval_extractor import get_dar_record_from_weaviate

        record = get_dar_record_from_weaviate(
            weaviate_client,
            doc_type="adr",
            doc_number="0025",
        )

        if record is None:
            pytest.skip("ADR.0025D not found in Weaviate")

        # Should be DAR doc
        assert "D" in record.document_id  # ADR.0025D
        assert record.file_path
        assert "0025D" in record.file_path or "0025d" in record.file_path.lower()
        assert record.content

    def test_get_dar_record_pcp0010(self, weaviate_client):
        """Integration test: fetch PCP.0010D (DAR) explicitly from Weaviate."""
        from src.approval_extractor import get_dar_record_from_weaviate

        record = get_dar_record_from_weaviate(
            weaviate_client,
            doc_type="principle",
            doc_number="0010",
        )

        if record is None:
            pytest.skip("PCP.0010D not found in Weaviate")

        # Should be DAR doc
        assert "D" in record.document_id  # PCP.0010D
        assert record.file_path
        assert "0010D" in record.file_path or "0010d" in record.file_path.lower()
        assert record.content

    def test_content_excludes_dar(self, weaviate_client):
        """Content retrieval for ADR.0025 should never return the DAR file."""
        from src.approval_extractor import get_content_record_from_weaviate

        record = get_content_record_from_weaviate(
            weaviate_client,
            doc_type="adr",
            doc_number="0025",
        )

        if record is None:
            pytest.skip("ADR.0025 not found in Weaviate")

        # The file path should match the content pattern, not DAR
        # Content: 0025-some-title.md
        # DAR: 0025D-some-title.md
        import re
        file_name = record.file_path.split("/")[-1].lower()

        # Should be content file pattern (NNNN-*.md), not DAR (NNNND-*.md)
        assert re.match(r'0025-', file_name), f"Expected content file, got: {file_name}"
