#!/usr/bin/env python3
"""
Tests for follow-up binding: "list them" should resolve to the last subject.

Regression: after "and how about DARs?", "list them" should list DARs
(not return random ADR content or abstain).
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chat_ui import resolve_followup, _detect_subject, _conversation_subjects


@pytest.fixture(autouse=True)
def clear_subjects():
    """Clear conversation subject state between tests."""
    _conversation_subjects.clear()
    yield
    _conversation_subjects.clear()


class TestSubjectDetection:
    """Test that document subjects are correctly detected from queries."""

    @pytest.mark.parametrize("query,expected", [
        ("and how about DARs?", "dars"),
        ("list dars", "dars"),
        ("show me the decision approval records", "dars"),
        ("what about approval records?", "dars"),
        ("list adrs", "adrs"),
        ("what ADRs exist?", "adrs"),
        ("tell me about architecture decisions", "adrs"),
        ("list principles", "principles"),
        ("what principles do we have?", "principles"),
        ("show policies", "policies"),
        ("what about the data governance policy?", "policies"),
    ])
    def test_subject_detected(self, query, expected):
        """Known subjects should be detected from queries."""
        assert _detect_subject(query) == expected

    @pytest.mark.parametrize("query", [
        "hello",
        "what is TLS?",
        "explain the caching strategy",
        "list them",
        # Word-boundary safety: substrings must NOT trigger false positives
        "what is a quadratic equation?",   # contains "adr" in "quadratic"
        "explain the bladder function",    # contains "dar" in "bladder"
        "use a standard approach",         # contains "dar" in "standard"
    ])
    def test_no_subject_for_generic_queries(self, query):
        """Generic queries without document type keywords should return None."""
        assert _detect_subject(query) is None


class TestFollowupResolution:
    """Test that ambiguous follow-ups are resolved using conversation context."""

    def test_list_them_after_dars(self):
        """'list them' after mentioning DARs should resolve to 'list dars'."""
        conv_id = "test-conv-1"
        # First query establishes subject
        resolve_followup("and how about DARs?", conv_id)
        # Follow-up should resolve
        result = resolve_followup("list them", conv_id)
        assert result == "list dars"

    def test_show_them_after_principles(self):
        """'show them' after mentioning principles should resolve."""
        conv_id = "test-conv-2"
        resolve_followup("what principles exist?", conv_id)
        result = resolve_followup("show them", conv_id)
        assert result == "list principles"

    def test_list_those_after_adrs(self):
        """'list those' after mentioning ADRs should resolve."""
        conv_id = "test-conv-3"
        resolve_followup("list adrs", conv_id)
        result = resolve_followup("list those", conv_id)
        assert result == "list adrs"

    def test_list_them_without_context_returns_unchanged(self):
        """'list them' without prior subject returns the query unchanged."""
        result = resolve_followup("list them", "no-context-conv")
        assert result == "list them"

    def test_list_them_no_conversation_returns_unchanged(self):
        """'list them' without conversation_id returns unchanged."""
        result = resolve_followup("list them", None)
        assert result == "list them"

    def test_subject_updates_on_new_query(self):
        """Subject should update when user asks about a different doc type."""
        conv_id = "test-conv-4"
        resolve_followup("list adrs", conv_id)
        assert _conversation_subjects[conv_id] == "adrs"
        resolve_followup("and how about DARs?", conv_id)
        assert _conversation_subjects[conv_id] == "dars"
        result = resolve_followup("list them", conv_id)
        assert result == "list dars"

    def test_non_followup_passes_through(self):
        """Normal queries should pass through unchanged."""
        conv_id = "test-conv-5"
        resolve_followup("list adrs", conv_id)
        result = resolve_followup("what is ADR.0025?", conv_id)
        assert result == "what is ADR.0025?"


class TestFollowupPatterns:
    """Test the follow-up pattern matching."""

    @pytest.mark.parametrize("query", [
        "list them",
        "List them",
        "show them",
        "Show those",
        "display them",
        "give me those",
        "tell me about them",
        "show me them",
        "list all of them",
        "show them all",
        "list them.",
        "show those?",
    ])
    def test_followup_patterns_match(self, query):
        """Known follow-up patterns should trigger resolution."""
        conv_id = "pattern-test"
        resolve_followup("list adrs", conv_id)  # establish subject
        result = resolve_followup(query, conv_id)
        assert result == "list adrs", f"'{query}' should resolve to 'list adrs'"

    @pytest.mark.parametrize("query", [
        "list all adrs",
        "show me the ADRs",
        "list them and explain each one",
        "tell me about ADR.0025",
        "what are they used for?",
    ])
    def test_non_followup_patterns_do_not_match(self, query):
        """Non-ambiguous queries should NOT trigger follow-up resolution."""
        conv_id = "pattern-test-2"
        resolve_followup("list dars", conv_id)
        result = resolve_followup(query, conv_id)
        assert result == query, f"'{query}' should NOT be rewritten"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
