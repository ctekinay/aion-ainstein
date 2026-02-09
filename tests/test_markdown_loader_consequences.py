"""Regression tests for MarkdownLoader consequences extraction.

Ensures the ADR_CONSEQUENCES_PATTERN correctly handles:
- ### Consequences (level 3 headings, used by most ADRs)
- ## Consequences (level 2 headings)
- #### subsections inside Consequences (must NOT stop at them)
- Heading variant aliases (e.g., "Consequences and Trade-offs")
"""

import re

import pytest


def _get_pattern():
    """Get the ADR_CONSEQUENCES_PATTERN from MarkdownLoader."""
    from src.loaders.markdown_loader import MarkdownLoader
    return MarkdownLoader.ADR_CONSEQUENCES_PATTERN


# =============================================================================
# Core regression: ### heading with #### subsections
# =============================================================================

class TestConsequencesSubsectionCapture:
    """Regression: consequences must include #### subsection content."""

    FIXTURE = """\
---
title: Test ADR
---

## Context and Problem Statement

Some context here.

## Decision Outcome

The decision was made.

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

> [!NOTE]
> MFFBAS provides standardized guidelines.

## More Information

References here.
"""

    def test_consequences_is_nonempty(self):
        pattern = _get_pattern()
        match = pattern.search(self.FIXTURE)
        assert match is not None, "Pattern did not match ### Consequences"
        assert len(match.group(1).strip()) > 0

    def test_contains_text_before_subsections(self):
        pattern = _get_pattern()
        match = pattern.search(self.FIXTURE)
        consequences = match.group(1).strip()
        assert "Supporting guidelines are" in consequences

    def test_contains_governance_subsection(self):
        pattern = _get_pattern()
        match = pattern.search(self.FIXTURE)
        consequences = match.group(1).strip()
        assert "Governance" in consequences
        assert "System Operator owns the rules" in consequences

    def test_contains_transparency_subsection(self):
        pattern = _get_pattern()
        match = pattern.search(self.FIXTURE)
        consequences = match.group(1).strip()
        assert "Transparency" in consequences
        assert "Must publish interface documentation" in consequences

    def test_contains_testing_subsection(self):
        pattern = _get_pattern()
        match = pattern.search(self.FIXTURE)
        consequences = match.group(1).strip()
        assert "Testing" in consequences
        assert "Provide non-production environments" in consequences

    def test_contains_note_block(self):
        pattern = _get_pattern()
        match = pattern.search(self.FIXTURE)
        consequences = match.group(1).strip()
        assert "MFFBAS" in consequences

    def test_stops_before_more_information(self):
        """Must NOT capture content from ## More Information."""
        pattern = _get_pattern()
        match = pattern.search(self.FIXTURE)
        consequences = match.group(1).strip()
        assert "References here" not in consequences


# =============================================================================
# Level 2 heading: ## Consequences
# =============================================================================

class TestConsequencesLevel2:
    """## Consequences (used by some ADRs like 0028) must also match."""

    FIXTURE = """\
## Context and Problem Statement

Context here.

## Decision Outcome

Decision here.

## Consequences

**Pros:**

- Improved error handling
- Transparent records

**Cons:**

- Increased complexity

## Links

Some links.
"""

    def test_matches_level2(self):
        pattern = _get_pattern()
        match = pattern.search(self.FIXTURE)
        assert match is not None, "Pattern did not match ## Consequences"

    def test_captures_full_content(self):
        pattern = _get_pattern()
        match = pattern.search(self.FIXTURE)
        consequences = match.group(1).strip()
        assert "Improved error handling" in consequences
        assert "Increased complexity" in consequences

    def test_stops_at_next_level2(self):
        pattern = _get_pattern()
        match = pattern.search(self.FIXTURE)
        consequences = match.group(1).strip()
        assert "Some links" not in consequences


# =============================================================================
# Heading variants
# =============================================================================

class TestConsequencesHeadingVariants:
    """Pattern must match heading aliases."""

    @pytest.mark.parametrize("heading", [
        "## Consequences",
        "### Consequences",
        "#### Consequences",
        "## Consequences and Trade-offs",
        "### Consequences & Trade-offs",
    ])
    def test_heading_variant_matches(self, heading):
        content = f"""\
## Context

Context.

{heading}

Some consequence text.

## More Information

Refs.
"""
        pattern = _get_pattern()
        match = pattern.search(content)
        assert match is not None, f"Pattern did not match: {heading}"
        assert "Some consequence text" in match.group(1).strip()


# =============================================================================
# Integration: real ADR.0025
# =============================================================================

class TestRealAdr0025:
    """Integration test with actual ADR.0025 file."""

    def test_consequences_from_real_file(self, project_root):
        from pathlib import Path
        adr_path = (
            project_root / "data" / "esa-main-artifacts" / "doc" / "decisions"
            / "0025-unify-demand-response-interfaces-via-open-standards.md"
        )
        if not adr_path.exists():
            pytest.skip("ADR.0025 file not found")

        content = adr_path.read_text()
        pattern = _get_pattern()
        match = pattern.search(content)

        assert match is not None, "No consequences match in ADR.0025"
        consequences = match.group(1).strip()

        assert len(consequences) > 300, (
            f"Consequences too short ({len(consequences)} chars)"
        )
        assert "Supporting guidelines are" in consequences
        assert "Governance" in consequences
        assert "System Operator" in consequences
        assert "Testing" in consequences
        assert "MFFBAS" in consequences
