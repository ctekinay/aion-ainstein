"""Tests for DAR (Decision Approval Record) table extraction and direct-doc route.

Acceptance criteria:
1. parse_dar_content extracts approvers from real DAR files with formatting
   oddities (reverse-numbered sections, leading whitespace, empty cells,
   HTML comments between metadata and approvers).
2. Multi-section DARs (e.g., ADR.0025D with two approval rounds) produce
   the correct number of sections and approvers.
3. Section headers without a number prefix (e.g., ADR.0031D) still parse.
4. build_dar_content_response for ADR.0025D includes "Decision Approval
   Record List" in full_text, while build_content_response for ADR.0025
   (non-DAR) never does.
"""

import pytest


# =============================================================================
# 1. DAR table parsing: multi-section with formatting oddities (ADR.0025D)
# =============================================================================

@pytest.mark.repo_data
class TestDarExtractionAdr0025D:
    """ADR.0025D has two reverse-numbered sections, leading whitespace in
    Remarks, empty Comments cells, and HTML comments between tables."""

    def _parse(self, project_root):
        from src.approval_extractor import parse_dar_content

        dar_path = (
            project_root / "data" / "esa-main-artifacts" / "doc" / "decisions"
            / "0025D-unify-demand-response-interfaces-via-open-standards.md"
        )
        if not dar_path.exists():
            pytest.skip("ADR.0025D file not found")

        content = dar_path.read_text()
        return parse_dar_content(content, "ADR.0025D", "Unify DR interfaces", str(dar_path))

    def test_extracts_two_sections(self, project_root):
        """Multi-section DAR must produce two ApprovalSections."""
        record = self._parse(project_root)
        assert len(record.sections) == 2

    def test_section_titles_preserved(self, project_root):
        """Section titles should match the heading text (after ## N.)."""
        record = self._parse(project_root)
        titles = [s.section_title for s in record.sections]
        assert any("ESA approval on improved descriptions" in t for t in titles)
        assert any("Creation and ESA Approval" in t for t in titles)

    def test_metadata_extracted(self, project_root):
        """Metadata (decision, decision_date, driver) must be populated."""
        record = self._parse(project_root)
        for section in record.sections:
            assert section.decision == "Accepted"
            assert section.decision_date  # non-empty
            assert "Energy System Architecture" in section.driver

    def test_remarks_with_leading_whitespace(self, project_root):
        """Remarks with leading whitespace must be trimmed."""
        record = self._parse(project_root)
        # Section "## 2." has non-empty remarks
        section_2 = next(
            (s for s in record.sections if "improved descriptions" in s.section_title),
            None,
        )
        assert section_2 is not None
        if section_2.remarks:
            assert not section_2.remarks.startswith(" "), (
                f"Remarks not trimmed: '{section_2.remarks[:20]}...'"
            )

    def test_approvers_extracted_per_section(self, project_root):
        """Each section must have at least 2 approvers."""
        record = self._parse(project_root)
        for section in record.sections:
            assert len(section.approvers) >= 2, (
                f"Section '{section.section_title}' has {len(section.approvers)} approvers"
            )

    def test_approver_fields_populated(self, project_root):
        """Approver name, email, and role must be non-empty."""
        record = self._parse(project_root)
        all_approvers = record.get_all_approvers()
        for approver in all_approvers:
            assert approver.name, "Approver name is empty"
            assert approver.email, "Approver email is empty"
            assert approver.role, "Approver role is empty"

    def test_known_approvers_present(self, project_root):
        """Robert-Jan Peters and Laurent van Groningen must appear."""
        record = self._parse(project_root)
        names = [a.name for a in record.get_all_approvers()]
        assert any("Robert-Jan" in n for n in names)
        assert any("Laurent" in n for n in names)

    def test_empty_comments_dont_break_parsing(self, project_root):
        """Empty Comments cells (| |) must not cause failures."""
        record = self._parse(project_root)
        # If we got here with approvers, empty cells were handled
        assert record.get_all_approvers()


# =============================================================================
# 2. DAR without number prefix in section header (ADR.0031D)
# =============================================================================

@pytest.mark.repo_data
class TestDarExtractionAdr0031D:
    """ADR.0031D has '## Creation and ESA Approval of ADR.31' (no '1.' prefix)."""

    def test_section_without_number_prefix(self, project_root):
        from src.approval_extractor import parse_dar_content

        dar_path = (
            project_root / "data" / "esa-main-artifacts" / "doc" / "decisions"
            / "0031D-use-an-alliander-owned-domain-for-customer-facing-services.md"
        )
        if not dar_path.exists():
            pytest.skip("ADR.0031D file not found")

        content = dar_path.read_text()
        record = parse_dar_content(content, "ADR.0031D")

        # Must still extract at least one section with approvers
        assert len(record.sections) >= 1
        assert record.get_all_approvers(), "No approvers extracted"

        # Verify known approver
        names = [a.name for a in record.get_all_approvers()]
        assert any("Robert-Jan" in n for n in names)

        # Metadata must still be extracted
        section = record.sections[0]
        assert section.decision == "Accepted"
        assert section.decision_date


# =============================================================================
# 3. Smoke test: ADR.0025D direct-doc DAR route vs ADR.0025 non-DAR
# =============================================================================

@pytest.mark.repo_data
class TestDarVsNonDarDirectDoc:
    """Ensure DAR and non-DAR direct-doc routes produce the right content."""

    def test_dar_full_text_includes_dar_header(self, project_root):
        """ADR.0025D full_text must include 'Decision Approval Record List'."""
        from src.approval_extractor import ContentRecord, build_dar_content_response

        dar_path = (
            project_root / "data" / "esa-main-artifacts" / "doc" / "decisions"
            / "0025D-unify-demand-response-interfaces-via-open-standards.md"
        )
        if not dar_path.exists():
            pytest.skip("ADR.0025D file not found")

        content = dar_path.read_text()
        record = ContentRecord(
            document_id="ADR.0025D",
            document_title="Unify DR interfaces (DAR)",
            file_path=str(dar_path),
            content=content,
        )

        response = build_dar_content_response(record, max_chars=12000)

        assert "Decision Approval Record List" in response["full_text"]
        assert "Accepted" in response["answer"]
        assert len(response["full_text"]) > 200

    def test_non_dar_answer_excludes_dar_content(self, project_root):
        """ADR.0025 (non-DAR) answer must NOT contain DAR-specific content."""
        from src.approval_extractor import (
            ContentRecord, build_content_response, parse_adr_content,
        )

        adr_path = (
            project_root / "data" / "esa-main-artifacts" / "doc" / "decisions"
            / "0025-unify-demand-response-interfaces-via-open-standards.md"
        )
        if not adr_path.exists():
            pytest.skip("ADR.0025 file not found")

        content = adr_path.read_text()
        sections = parse_adr_content(content)

        record = ContentRecord(
            document_id="ADR.0025",
            document_title="Unify DR interfaces",
            file_path=str(adr_path),
            content=content,
            context=sections["context"],
            decision=sections["decision"],
            consequences=sections["consequences"],
            status=sections["status"],
        )

        response = build_content_response(record, max_chars=12000)

        # Non-DAR must never contain DAR-specific markers
        assert "Decision Approval Record List" not in response["answer"]
        assert "Decision Approval Record" not in response["answer"]

        # But must contain the actual ADR content
        assert "Governance" in response["answer"]
        assert "Consequences" in response["answer"]
