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

from src.chat_ui import (
    resolve_followup,
    FollowupResult,
    _detect_subject,
    _conversation_subjects,
    _evict_stale_conversations,
    _MAX_TRACKED_CONVERSATIONS,
)


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
        assert result.question == "list dars"
        assert result.rewrite_applied is True
        assert result.rewrite_reason == "subject_rewrite"

    def test_show_them_after_principles(self):
        """'show them' after mentioning principles should resolve."""
        conv_id = "test-conv-2"
        resolve_followup("what principles exist?", conv_id)
        result = resolve_followup("show them", conv_id)
        assert result.question == "list principles"
        assert result.rewrite_applied is True

    def test_list_those_after_adrs(self):
        """'list those' after mentioning ADRs should resolve."""
        conv_id = "test-conv-3"
        resolve_followup("list adrs", conv_id)
        result = resolve_followup("list those", conv_id)
        assert result.question == "list adrs"

    def test_list_them_without_context_returns_unchanged(self):
        """'list them' without prior subject returns the query unchanged."""
        result = resolve_followup("list them", "no-context-conv")
        assert result.question == "list them"
        assert result.rewrite_applied is False
        assert result.rewrite_reason == "no_rewrite"

    def test_list_them_no_conversation_returns_unchanged(self):
        """'list them' without conversation_id returns unchanged."""
        result = resolve_followup("list them", None)
        assert result.question == "list them"
        assert result.rewrite_applied is False

    def test_subject_updates_on_new_query(self):
        """Subject should update when user asks about a different doc type."""
        conv_id = "test-conv-4"
        resolve_followup("list adrs", conv_id)
        assert _conversation_subjects[conv_id] == "adrs"
        resolve_followup("and how about DARs?", conv_id)
        assert _conversation_subjects[conv_id] == "dars"
        result = resolve_followup("list them", conv_id)
        assert result.question == "list dars"

    def test_non_followup_passes_through(self):
        """Normal queries should pass through unchanged."""
        conv_id = "test-conv-5"
        resolve_followup("list adrs", conv_id)
        result = resolve_followup("what is ADR.0025?", conv_id)
        assert result.question == "what is ADR.0025?"
        assert result.rewrite_applied is False
        assert result.rewrite_reason == "no_rewrite"


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
        assert result.question == "list adrs", f"'{query}' should resolve to 'list adrs'"
        assert result.rewrite_applied is True

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
        assert result.question == query, f"'{query}' should NOT be rewritten"
        assert result.rewrite_applied is False


class TestApprovalFollowup:
    """Test approval follow-up resolution: 'who approved them?'."""

    def test_who_approved_them_after_adrs(self):
        """'who approved them?' after listing ADRs should resolve."""
        conv_id = "approval-test-1"
        resolve_followup("list adrs", conv_id)
        result = resolve_followup("who approved them?", conv_id)
        assert "who approved" in result.question.lower()
        assert "adrs" in result.question.lower()
        assert result.rewrite_applied is True
        assert result.rewrite_reason == "approval_rewrite"

    def test_who_signed_off_on_them_after_dars(self):
        """'who signed off on them?' should also resolve."""
        conv_id = "approval-test-2"
        resolve_followup("list dars", conv_id)
        result = resolve_followup("who signed off on them?", conv_id)
        assert "dars" in result.question.lower()
        assert result.rewrite_applied is True

    def test_who_approved_those_after_principles(self):
        """'who approved those?' after principles should resolve."""
        conv_id = "approval-test-3"
        resolve_followup("list principles", conv_id)
        result = resolve_followup("who approved those?", conv_id)
        assert "principles" in result.question.lower()

    def test_who_approved_without_context(self):
        """'who approved them?' without context returns unchanged."""
        result = resolve_followup("who approved them?", "no-context")
        assert result.question == "who approved them?"
        assert result.rewrite_applied is False


class TestContinuationFollowup:
    """Test continuation phrases: 'what about those?', 'how about them?'."""

    def test_what_about_them_after_adrs(self):
        """'what about them?' after ADRs should resolve."""
        conv_id = "cont-test-1"
        resolve_followup("list adrs", conv_id)
        result = resolve_followup("what about them?", conv_id)
        assert result.question == "list adrs"
        assert result.rewrite_applied is True
        assert result.rewrite_reason == "continuation_rewrite"

    def test_how_about_those_after_dars(self):
        """'how about those?' after DARs should resolve."""
        conv_id = "cont-test-2"
        resolve_followup("and how about DARs?", conv_id)
        result = resolve_followup("how about those?", conv_id)
        assert result.question == "list dars"

    def test_and_what_about_them(self):
        """'and what about them?' after principles should resolve."""
        conv_id = "cont-test-3"
        resolve_followup("list principles", conv_id)
        result = resolve_followup("and what about them?", conv_id)
        assert result.question == "list principles"

    def test_continuation_without_context(self):
        """Continuation without context returns unchanged."""
        result = resolve_followup("what about them?", "no-context")
        assert result.question == "what about them?"
        assert result.rewrite_applied is False

    def test_continuation_with_explicit_subject_not_caught(self):
        """'how about DARs?' has a real subject, NOT a pronoun follow-up."""
        conv_id = "cont-test-4"
        resolve_followup("list adrs", conv_id)
        # This should detect "dars" as a new subject, not trigger pronoun resolution
        result = resolve_followup("how about DARs?", conv_id)
        assert result.question == "how about DARs?"  # Pass through (routing handles it)
        assert result.rewrite_applied is False
        assert _conversation_subjects[conv_id] == "dars"


class TestConversationStateCap:
    """Test that conversation state is bounded."""

    def test_eviction_when_over_cap(self):
        """Exceeding cap should evict oldest half of conversations."""
        # Fill to over capacity
        for i in range(_MAX_TRACKED_CONVERSATIONS + 10):
            _conversation_subjects[f"conv-{i}"] = "adrs"

        assert len(_conversation_subjects) > _MAX_TRACKED_CONVERSATIONS

        _evict_stale_conversations()

        # Should have evicted roughly half
        assert len(_conversation_subjects) <= (_MAX_TRACKED_CONVERSATIONS + 10) // 2 + 10

    def test_eviction_preserves_recent(self):
        """Eviction should keep the most recent conversations."""
        for i in range(_MAX_TRACKED_CONVERSATIONS + 10):
            _conversation_subjects[f"conv-{i}"] = "adrs"

        _evict_stale_conversations()

        # Most recent conversations should survive
        last_id = f"conv-{_MAX_TRACKED_CONVERSATIONS + 9}"
        assert last_id in _conversation_subjects

    def test_no_eviction_under_cap(self):
        """No eviction when under the cap."""
        for i in range(10):
            _conversation_subjects[f"conv-{i}"] = "adrs"

        _evict_stale_conversations()
        assert len(_conversation_subjects) == 10


class TestDocRefAwareFollowup:
    """When _conversation_doc_refs has cached refs, follow-ups must pass through
    unchanged so ArchitectureAgent can inject last_doc_refs.

    Regression: "Show it" after ADR.0012 was rewritten to "list adrs",
    destroying the follow-up chain.
    """

    def test_show_it_passthrough_when_doc_refs_cached(self):
        """'Show it' with cached doc_refs must NOT be rewritten to 'list adrs'."""
        conv_id = "docref-test-1"
        doc_refs_cache = {
            conv_id: [{"canonical_id": "ADR.12", "prefix": "ADR", "number_value": "0012"}],
        }
        # Establish subject so the old code path would fire
        _conversation_subjects[conv_id] = "adrs"
        result = resolve_followup("Show it", conv_id, doc_refs_cache=doc_refs_cache)
        assert result.question == "Show it", f"Expected passthrough, got '{result.question}'"
        assert result.rewrite_applied is False
        assert result.rewrite_reason == "doc_refs_cached_passthrough"

    def test_quote_decision_passthrough_when_doc_refs_cached(self):
        """'Quote the decision sentence' with cached doc_refs must pass through."""
        conv_id = "docref-test-2"
        doc_refs_cache = {
            conv_id: [{"canonical_id": "ADR.12", "prefix": "ADR", "number_value": "0012"}],
        }
        _conversation_subjects[conv_id] = "adrs"
        result = resolve_followup(
            "Quote the decision sentence", conv_id, doc_refs_cache=doc_refs_cache
        )
        assert result.question == "Quote the decision sentence"
        assert result.rewrite_reason == "doc_refs_cached_passthrough"

    def test_tell_me_more_passthrough_when_doc_refs_cached(self):
        """'tell me about it' with cached doc_refs must pass through."""
        conv_id = "docref-test-3"
        doc_refs_cache = {
            conv_id: [{"canonical_id": "PCP.22", "prefix": "PCP", "number_value": "0022"}],
        }
        _conversation_subjects[conv_id] = "adrs"
        result = resolve_followup(
            "tell me about it", conv_id, doc_refs_cache=doc_refs_cache
        )
        assert result.question == "tell me about it"
        assert result.rewrite_reason == "doc_refs_cached_passthrough"

    def test_list_them_still_rewrites_when_no_doc_refs(self):
        """Without cached doc_refs, 'list them' should still rewrite normally."""
        conv_id = "docref-test-4"
        doc_refs_cache = {}  # Empty — no cached doc refs
        _conversation_subjects[conv_id] = "dars"
        result = resolve_followup("list them", conv_id, doc_refs_cache=doc_refs_cache)
        assert result.question == "list dars"
        assert result.rewrite_applied is True
        assert result.rewrite_reason == "subject_rewrite"

    def test_approval_followup_passthrough_when_doc_refs_cached(self):
        """'who approved it?' with cached doc_refs must pass through."""
        conv_id = "docref-test-5"
        doc_refs_cache = {
            conv_id: [{"canonical_id": "ADR.12", "prefix": "ADR", "number_value": "0012"}],
        }
        _conversation_subjects[conv_id] = "adrs"
        result = resolve_followup(
            "who approved it?", conv_id, doc_refs_cache=doc_refs_cache
        )
        # Should NOT be rewritten to "who approved the adrs?"
        assert result.question == "who approved it?"
        assert result.rewrite_reason == "doc_refs_cached_passthrough"

    def test_continuation_passthrough_when_doc_refs_cached(self):
        """'what about it?' with cached doc_refs must pass through."""
        conv_id = "docref-test-6"
        doc_refs_cache = {
            conv_id: [{"canonical_id": "ADR.12", "prefix": "ADR", "number_value": "0012"}],
        }
        _conversation_subjects[conv_id] = "adrs"
        result = resolve_followup(
            "what about it?", conv_id, doc_refs_cache=doc_refs_cache
        )
        assert result.question == "what about it?"
        assert result.rewrite_reason == "doc_refs_cached_passthrough"

    def test_empty_doc_refs_list_does_not_block_rewrite(self):
        """Empty list (not None) for doc_refs should NOT block rewrite."""
        conv_id = "docref-test-7"
        doc_refs_cache = {conv_id: []}  # Present but empty
        _conversation_subjects[conv_id] = "adrs"
        result = resolve_followup("show them", conv_id, doc_refs_cache=doc_refs_cache)
        # Empty list is falsy → should fall through to rewrite
        assert result.question == "list adrs"
        assert result.rewrite_applied is True
        assert result.rewrite_reason == "subject_rewrite"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
