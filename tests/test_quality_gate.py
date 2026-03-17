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
        assert "Related content exists" in trimmed

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
