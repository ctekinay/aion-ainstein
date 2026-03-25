"""Unit tests for the post-generation quality gate.

Tests cover the deterministic, code-level components:
- Abstention overflow detection and truncation
- Citation extraction and recovery
- Token ceiling skip logic

LLM-dependent components (evaluation, condensation) are not tested here
as they require live model access.
"""

import asyncio

import pytest

from aion.agents.quality_gate import (
    ResponseQualityGate,
    _count_list_items,
    _estimate_tokens,
    _extract_citations,
)


class TestEstimateTokens:
    def test_empty(self):
        assert _estimate_tokens("") == 0

    def test_simple(self):
        assert _estimate_tokens("hello world") == 2

    def test_multiline(self):
        text = "Line one.\nLine two.\nLine three."
        assert _estimate_tokens(text) == 6


class TestExtractCitations:
    def test_adr_citations(self):
        text = "According to ADR.29 and ADR.12, the system should..."
        assert _extract_citations(text) == {"ADR.29", "ADR.12"}

    def test_pcp_citations(self):
        text = "PCP.10 says availability, PCP.22 says omnichannel"
        assert _extract_citations(text) == {"PCP.10", "PCP.22"}

    def test_mixed(self):
        text = "ADR.29 aligns with PCP.10 on this point."
        assert _extract_citations(text) == {"ADR.29", "PCP.10"}

    def test_no_citations(self):
        text = "This response has no document references."
        assert _extract_citations(text) == set()

    def test_duplicates(self):
        text = "ADR.29 is mentioned here. ADR.29 is also here."
        assert _extract_citations(text) == {"ADR.29"}


class TestAbstentionOverflow:
    """Test the _check_abstention_overflow heuristic."""

    def setup_method(self):
        self.gate = ResponseQualityGate()
        self.config = {
            "enabled": True,
            "item_threshold": 2,
            "negation_signals": [
                "contains no",
                "does not contain",
                "no budget",
                "no information",
                "does not specify",
            ],
        }

    def test_negation_with_many_items_triggers(self):
        response = (
            "ADR.29 contains no budget information.\n\n"
            "- Operational complexity (IdP management)\n"
            "- Dependency on Authorization Server\n"
            "- Migration effort\n"
            "- Key rotation overhead\n"
        )
        trimmed, meta = self.gate._check_abstention_overflow(response, self.config)
        assert meta["gate_fired"] is True
        assert meta["action"] == "abstention_trimmed"
        assert "4 items" in meta["reason"]
        assert "Operational complexity" in trimmed  # specific hint from truncated items

    def test_negation_with_few_items_passes(self):
        response = (
            "ADR.29 contains no budget information.\n\n"
            "- One related item\n"
        )
        _, meta = self.gate._check_abstention_overflow(response, self.config)
        assert meta["gate_fired"] is False

    def test_no_negation_passes(self):
        response = (
            "ADR.29 specifies OAuth 2.0 for authorization.\n\n"
            "- Point one\n"
            "- Point two\n"
            "- Point three\n"
            "- Point four\n"
        )
        _, meta = self.gate._check_abstention_overflow(response, self.config)
        assert meta["gate_fired"] is False

    def test_empty_response(self):
        _, meta = self.gate._check_abstention_overflow("", self.config)
        assert meta["gate_fired"] is False

    def test_negation_no_list(self):
        response = "ADR.29 contains no budget information. That's all."
        _, meta = self.gate._check_abstention_overflow(response, self.config)
        assert meta["gate_fired"] is False

    def test_threshold_boundary(self):
        """Exactly at threshold — should NOT trigger."""
        response = (
            "ADR.29 does not specify any budget.\n\n"
            "- Item one\n"
            "- Item two\n"
        )
        _, meta = self.gate._check_abstention_overflow(response, self.config)
        assert meta["gate_fired"] is False

    def test_threshold_exceeded(self):
        """One over threshold — should trigger."""
        response = (
            "ADR.29 does not specify any budget.\n\n"
            "- Item one\n"
            "- Item two\n"
            "- Item three\n"
        )
        trimmed, meta = self.gate._check_abstention_overflow(response, self.config)
        assert meta["gate_fired"] is True


class TestCountListItems:
    """Unit tests for the _count_list_items enumeration detector."""

    def test_bullet_dash(self):
        text = "Header\n- item 1\n- item 2\n- item 3"
        assert _count_list_items(text) == 3

    def test_bullet_asterisk(self):
        text = "* one\n* two\n* three\n* four\n* five"
        assert _count_list_items(text) == 5

    def test_bullet_unicode(self):
        text = "• alpha\n• beta\n• gamma"
        assert _count_list_items(text) == 3

    def test_numbered_dot(self):
        text = "1. First\n2. Second\n3. Third\n4. Fourth"
        assert _count_list_items(text) == 4

    def test_numbered_paren(self):
        text = "1) A\n2) B\n3) C"
        assert _count_list_items(text) == 3

    def test_doc_ids_adr(self):
        text = "ADR.00 — Use markdown\nADR.01 — Conventions\nADR.02 — DACI"
        assert _count_list_items(text) == 3

    def test_doc_ids_pcp(self):
        text = (
            "PCP.10 — Eventual consistency\n"
            "PCP.11 — Need to know\n"
            "PCP.12 — Business readiness\n"
            "PCP.13 — Cost tiering\n"
            "PCP.14 — Context preservation\n"
            "PCP.39 — Language governance\n"
        )
        assert _count_list_items(text) == 6

    def test_mixed_bullets_and_ids(self):
        text = (
            "BA principles:\n"
            "- PCP.21 — Operational Excellence\n"
            "- PCP.22 — Omnichannel\n"
            "DO principles:\n"
            "- PCP.31 — Data vastlegging\n"
        )
        # Each line matches both bullet AND doc ID, but re.findall returns
        # one match per line start, so count = 3 (one per bullet line)
        assert _count_list_items(text) >= 3

    def test_no_list_items(self):
        text = "This is a plain paragraph with no list structure whatsoever."
        assert _count_list_items(text) == 0

    def test_empty_string(self):
        assert _count_list_items("") == 0

    def test_indented_bullets(self):
        text = "  - sub item 1\n  - sub item 2\n  - sub item 3"
        assert _count_list_items(text) == 3

    def test_threshold_boundary_four(self):
        """4 items — below the gate threshold of 5."""
        text = "- a\n- b\n- c\n- d"
        assert _count_list_items(text) == 4

    def test_threshold_boundary_five(self):
        """5 items — at the gate threshold."""
        text = "- a\n- b\n- c\n- d\n- e"
        assert _count_list_items(text) == 5

    def test_dar_ids(self):
        """DAR-style IDs (ADR.XXD, PCP.XXD) should match the ADR/PCP prefix."""
        text = "ADR.00D — Approval\nADR.01D — Approval\nPCP.10D — Approval"
        assert _count_list_items(text) == 3


class TestEnumerationGuard:
    """Integration: gate skips condensation for enumeration responses."""

    def setup_method(self):
        self.gate = ResponseQualityGate()

    def test_simple_complexity_with_enumeration_skips(self):
        """A complexity='simple' response with 5+ list items bypasses the gate."""
        enumeration = (
            "Here are the ESA principles:\n\n"
            "PCP.10 — Eventual consistency by design\n"
            "PCP.11 — Data design need to know\n"
            "PCP.12 — Business driven data readiness\n"
            "PCP.13 — Cost efficient tiering\n"
            "PCP.14 — Decision context preservation\n"
            "PCP.15 — Derived data reproduction\n"
            "PCP.16 — Make uncertain explicit\n"
        )
        result, meta = asyncio.get_event_loop().run_until_complete(
            self.gate.evaluate(
                response=enumeration,
                query="List ESA principles",
                complexity="simple",
                event_queue=None,
                agent_label="test",
            )
        )
        assert meta["gate_fired"] is False
        assert "enumeration" in meta.get("reason", "")
        assert result == enumeration  # response preserved exactly

    def test_simple_complexity_without_enumeration_proceeds(self):
        """A complexity='simple' response with <5 list items goes to proportionality."""
        short_response = "ADR.29 specifies OAuth 2.0 for authentication."
        result, meta = asyncio.get_event_loop().run_until_complete(
            self.gate.evaluate(
                response=short_response,
                query="What does ADR.29 say?",
                complexity="simple",
                event_queue=None,
                agent_label="test",
            )
        )
        # Should NOT be skipped for enumeration — passes through to
        # token ceiling check (which skips because it's short)
        assert meta.get("reason", "") != "enumeration detected"

    def test_bullet_enumeration_skips(self):
        """Bullet-style enumerations also bypass the gate."""
        bullets = (
            "The following ADRs exist:\n\n"
            "- ADR.00 — Use markdown\n"
            "- ADR.01 — Conventions in writing\n"
            "- ADR.02 — DACI decision making\n"
            "- ADR.10 — Prioritize standards\n"
            "- ADR.11 — Standard for business functions\n"
            "- ADR.12 — CIM as default domain language\n"
        )
        result, meta = asyncio.get_event_loop().run_until_complete(
            self.gate.evaluate(
                response=bullets,
                query="List all ADRs",
                complexity="simple",
                event_queue=None,
                agent_label="test",
            )
        )
        assert meta["gate_fired"] is False
        assert "enumeration" in meta.get("reason", "")
        assert result == bullets


class TestGateEvaluateSkipPaths:
    """Test that the gate correctly skips in various scenarios."""

    def setup_method(self):
        self.gate = ResponseQualityGate()

    def test_skips_when_complexity_is_none(self):
        result, meta = asyncio.get_event_loop().run_until_complete(
            self.gate.evaluate(
                response="Some response",
                query="test",
                complexity=None,
                event_queue=None,
                agent_label="test",
            )
        )
        assert meta["action"] == "skipped"
        assert result == "Some response"

    def test_skips_when_not_simple(self):
        result, meta = asyncio.get_event_loop().run_until_complete(
            self.gate.evaluate(
                response="Some long response " * 100,
                query="test",
                complexity="multi-step",
                event_queue=None,
                agent_label="test",
            )
        )
        assert meta["action"] == "passed"
        assert meta["gate_fired"] is False


class TestCitationRecovery:
    """Test that citation extraction works for the recovery step."""

    def test_missing_citations_detected(self):
        original = "According to ADR.29 and PCP.10, the system should..."
        condensed = "The system should use OAuth 2.0. (ADR.29)"
        original_cites = _extract_citations(original)
        condensed_cites = _extract_citations(condensed)
        missing = original_cites - condensed_cites
        assert missing == {"PCP.10"}

    def test_no_missing_citations(self):
        original = "ADR.29 says X. PCP.10 says Y."
        condensed = "ADR.29 mandates X, while PCP.10 requires Y."
        missing = _extract_citations(original) - _extract_citations(condensed)
        assert missing == set()
