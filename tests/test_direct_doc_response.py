"""Tests for direct document response: parser fix, truncation bypass, and full_doc payload.

Acceptance criteria:
1. Direct doc route uses direct_doc_max_chars, not content_max_chars/summary_chars.
2. Direct doc route never includes DAR unless explicitly asked.
3. Normal RAG semantic search still uses the smaller truncation values.
4. parse_adr_content captures subsections (#### headings) within a section.
5. build_content_response returns both summary and full_text fields.
"""

from pathlib import Path

import pytest


# =============================================================================
# 1. Parser: heading-level aware section extraction
# =============================================================================

class TestParseAdrContent:
    """Test the heading-level aware ADR section parser."""

    def test_captures_subsections_in_consequences(self):
        """Consequences with #### subsections must be fully captured."""
        from src.approval_extractor import parse_adr_content

        content = """\
# ADR.0025

## Context

Some context here.

## Decision Outcome

The adoption of a unified interface.

### Consequences

Supporting guidelines are:

#### Governance & Coordination

Clear governance ownership

* System Operator owns the rules.
* Changes must follow a process.

#### Transparency & Requirements

Operational transparency

* Must publish interface documentation.

#### Testing & Development

Test environments

* Provide non-production environments.

## More Information

References here.
"""
        result = parse_adr_content(content)

        assert "Governance" in result["consequences"]
        assert "Transparency" in result["consequences"]
        assert "Testing" in result["consequences"]
        assert "* System Operator" in result["consequences"]
        assert "* Provide non-production" in result["consequences"]

    def test_stops_at_same_level_heading(self):
        """Parser should stop capturing when it hits a heading at the same level."""
        from src.approval_extractor import parse_adr_content

        content = """\
## Context

Context content here.

## Decision

Decision content here.

## Consequences

Consequence content here.

## Status

Accepted.
"""
        result = parse_adr_content(content)

        assert result["context"] == "Context content here."
        assert result["decision"] == "Decision content here."
        assert result["consequences"] == "Consequence content here."
        assert "Accepted" in result["status"]

    def test_ignores_headings_in_code_fences(self):
        """Headings inside code fences should not break section capture."""
        from src.approval_extractor import parse_adr_content

        content = """\
## Context

Here is some context with code:

```markdown
## This is not a real heading
### Neither is this
```

More context after the code block.

## Decision

The decision.
"""
        result = parse_adr_content(content)

        assert "More context after the code block." in result["context"]
        assert "## This is not a real heading" in result["context"]

    def test_real_adr_0025(self, project_root):
        """Integration test with actual ADR.0025 file."""
        from src.approval_extractor import parse_adr_content

        adr_path = project_root / "data" / "esa-main-artifacts" / "doc" / "decisions" / "0025-unify-demand-response-interfaces-via-open-standards.md"
        if not adr_path.exists():
            pytest.skip("ADR.0025 file not found")

        content = adr_path.read_text()
        result = parse_adr_content(content)

        # Must contain subsection titles and bullet content
        assert "Governance" in result["consequences"], "Missing Governance subsection"
        assert "* System Operator" in result["consequences"], "Missing bullet after Governance"
        assert "Testing" in result["consequences"], "Missing Testing subsection"
        assert len(result["consequences"]) > 300, (
            f"Consequences too short ({len(result['consequences'])} chars), "
            "subsections likely not captured"
        )


# =============================================================================
# 2. build_content_response: full_text field and direct_doc_max_chars
# =============================================================================

class TestBuildContentResponse:
    """Test that build_content_response returns structured full_doc payload."""

    def _make_record(self, content_len=5000):
        from src.approval_extractor import ContentRecord
        return ContentRecord(
            document_id="ADR.0025",
            document_title="Unified D/R Interface",
            file_path="doc/decisions/0025.md",
            content="x" * content_len,
            context="Some context",
            decision="Some decision",
            consequences="Some consequences with details",
            status="proposed",
        )

    def test_includes_full_text_field(self):
        """Response must include full_text field."""
        from src.approval_extractor import build_content_response

        record = self._make_record(5000)
        response = build_content_response(record, max_chars=12000)

        assert "full_text" in response
        assert len(response["full_text"]) == 5000

    def test_full_text_respects_max_chars(self):
        """full_text must be capped at max_chars."""
        from src.approval_extractor import build_content_response

        record = self._make_record(20000)
        response = build_content_response(record, max_chars=12000)

        assert len(response["full_text"]) == 12003  # 12000 + "..."
        assert response["full_text"].endswith("...")

    def test_answer_contains_structured_sections(self):
        """answer field must contain context/decision/consequences."""
        from src.approval_extractor import build_content_response

        record = self._make_record()
        response = build_content_response(record)

        assert "**Context:**" in response["answer"]
        assert "**Decision:**" in response["answer"]
        assert "**Consequences:**" in response["answer"]

    def test_includes_content_record(self):
        """Response must include content_record dict."""
        from src.approval_extractor import build_content_response

        record = self._make_record()
        response = build_content_response(record)

        assert "content_record" in response
        assert response["content_record"]["document_id"] == "ADR.0025"


# =============================================================================
# 3. build_dar_content_response: full_text and max_chars
# =============================================================================

class TestBuildDarContentResponse:
    """Test DAR content response includes full_text."""

    def test_includes_full_text_field(self):
        from src.approval_extractor import ContentRecord, build_dar_content_response

        record = ContentRecord(
            document_id="ADR.0025D",
            document_title="DAR for ADR.0025",
            file_path="doc/decisions/0025D.md",
            content="DAR content " * 500,
        )
        response = build_dar_content_response(record, max_chars=12000)

        assert "full_text" in response
        assert len(response["full_text"]) <= 12003

    def test_full_text_capped(self):
        from src.approval_extractor import ContentRecord, build_dar_content_response

        record = ContentRecord(
            document_id="ADR.0025D",
            document_title="DAR for ADR.0025",
            file_path="doc/decisions/0025D.md",
            content="x" * 20000,
        )
        response = build_dar_content_response(record, max_chars=5000)

        assert len(response["full_text"]) == 5003  # 5000 + "..."


# =============================================================================
# 4. Threshold configuration
# =============================================================================

class TestThresholdConfig:
    """Test that direct_doc_max_chars is properly loaded from config."""

    def test_default_in_loader(self, tmp_path):
        """Loader fallback must include direct_doc_max_chars."""
        from src.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)

        # get_thresholds returns {} for unknown skill, triggering fallback
        truncation = loader.get_truncation("nonexistent-skill")
        assert "direct_doc_max_chars" in truncation
        assert truncation["direct_doc_max_chars"] == 12000

    def test_consequences_max_chars_default(self, tmp_path):
        """Loader fallback must include consequences_max_chars."""
        from src.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)

        truncation = loader.get_truncation("nonexistent-skill")
        assert "consequences_max_chars" in truncation
        assert truncation["consequences_max_chars"] == 4000
