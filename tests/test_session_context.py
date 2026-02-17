"""Unit tests for SessionContext — anaphora detection, ref resolution, state.

Tests cover:
  SC1: SessionState initialization (empty state)
  SC2: update() tracks last_doc_refs, last_intent, last_query, turn_count
  SC3: update() without doc_refs preserves previous refs
  SC4: resolve_refs() returns current_refs when present
  SC5: resolve_refs() injects last_doc_refs when anaphora detected + no current refs
  SC6: resolve_refs() returns empty when no anaphora + no current refs
  SC7: _has_anaphora() detects pronouns ("it", "them", "those", "these")
  SC8: _has_anaphora() detects demonstratives ("that", "this")
  SC9: _has_anaphora() detects noun phrases ("the document", "the adr")
  SC10: _has_anaphora() rejects non-anaphoric queries
  SC11: _has_anaphora() handles edge cases (word boundaries)
  SC12: Multi-turn scenario: refs carry across turns correctly
"""

import pytest

from src.agents.session_context import SessionContext, SessionState


# =============================================================================
# Test data
# =============================================================================

_REF_ADR12 = {"canonical_id": "ADR.12", "number_value": "0012", "prefix": "ADR"}
_REF_PCP22 = {"canonical_id": "PCP.22", "number_value": "0022", "prefix": "PCP"}


# =============================================================================
# SC1: SessionState initialization
# =============================================================================

class TestSessionStateInit:
    def test_default_state(self):
        state = SessionState()
        assert state.last_doc_refs == []
        assert state.last_intent == "none"
        assert state.last_query == ""
        assert state.turn_count == 0


# =============================================================================
# SC2: update() tracks state
# =============================================================================

class TestSessionUpdate:
    def test_update_sets_all_fields(self):
        ctx = SessionContext()
        ctx.update("What does ADR.12 decide?", "lookup_doc", [_REF_ADR12])
        assert ctx.state.last_doc_refs == [_REF_ADR12]
        assert ctx.state.last_intent == "lookup_doc"
        assert ctx.state.last_query == "What does ADR.12 decide?"
        assert ctx.state.turn_count == 1

    def test_update_increments_turn_count(self):
        ctx = SessionContext()
        ctx.update("q1", "list", [])
        ctx.update("q2", "count", [])
        ctx.update("q3", "semantic_answer", [])
        assert ctx.state.turn_count == 3

    def test_update_with_refs_replaces_previous(self):
        ctx = SessionContext()
        ctx.update("q1", "lookup_doc", [_REF_ADR12])
        ctx.update("q2", "lookup_doc", [_REF_PCP22])
        assert ctx.state.last_doc_refs == [_REF_PCP22]


# =============================================================================
# SC3: update() without doc_refs preserves previous
# =============================================================================

class TestUpdatePreservesRefs:
    def test_empty_refs_preserves_previous(self):
        ctx = SessionContext()
        ctx.update("q1", "lookup_doc", [_REF_ADR12])
        ctx.update("q2", "list", [])  # No refs in this turn
        assert ctx.state.last_doc_refs == [_REF_ADR12]

    def test_none_refs_preserves_previous(self):
        ctx = SessionContext()
        ctx.update("q1", "lookup_doc", [_REF_ADR12])
        ctx.update("q2", "semantic_answer", None)
        assert ctx.state.last_doc_refs == [_REF_ADR12]


# =============================================================================
# SC4: resolve_refs() returns current when present
# =============================================================================

class TestResolveRefsCurrentPresent:
    def test_current_refs_returned_unchanged(self):
        ctx = SessionContext()
        ctx.update("q1", "lookup_doc", [_REF_ADR12])
        result = ctx.resolve_refs("show PCP.22", [_REF_PCP22])
        assert result == [_REF_PCP22]

    def test_current_refs_not_overridden_by_session(self):
        ctx = SessionContext()
        ctx.update("q1", "lookup_doc", [_REF_ADR12])
        result = ctx.resolve_refs("show them", [_REF_PCP22])
        # Even with anaphora, current refs take precedence
        assert result == [_REF_PCP22]


# =============================================================================
# SC5: resolve_refs() injects when anaphora + no current refs
# =============================================================================

class TestResolveRefsInjection:
    def test_anaphora_injects_last_refs(self):
        ctx = SessionContext()
        ctx.update("q1", "lookup_doc", [_REF_ADR12])
        result = ctx.resolve_refs("show it", [])
        assert result == [_REF_ADR12]

    def test_anaphora_injects_multiple_refs(self):
        ctx = SessionContext()
        ctx.update("q1", "compare", [_REF_ADR12, _REF_PCP22])
        result = ctx.resolve_refs("compare them", [])
        assert result == [_REF_ADR12, _REF_PCP22]


# =============================================================================
# SC6: resolve_refs() returns empty when no anaphora
# =============================================================================

class TestResolveRefsNoAnaphora:
    def test_no_anaphora_no_injection(self):
        ctx = SessionContext()
        ctx.update("q1", "lookup_doc", [_REF_ADR12])
        result = ctx.resolve_refs("List all ADRs", [])
        assert result == []

    def test_no_session_refs_returns_empty(self):
        ctx = SessionContext()
        result = ctx.resolve_refs("show it", [])
        assert result == []


# =============================================================================
# SC7: _has_anaphora() — pronouns
# =============================================================================

class TestAnaphoraPronouns:
    @pytest.mark.parametrize("query", [
        "show it",
        "what does it decide?",
        "show them",
        "compare those",
        "explain these",
    ])
    def test_pronoun_detected(self, query):
        ctx = SessionContext()
        assert ctx._has_anaphora(query)


# =============================================================================
# SC8: _has_anaphora() — demonstratives
# =============================================================================

class TestAnaphoraDemonstratives:
    @pytest.mark.parametrize("query", [
        "show that",
        "explain this",
        "what about that?",
        "tell me about this",
    ])
    def test_demonstrative_detected(self, query):
        ctx = SessionContext()
        assert ctx._has_anaphora(query)


# =============================================================================
# SC9: _has_anaphora() — noun phrases
# =============================================================================

class TestAnaphoraNounPhrases:
    @pytest.mark.parametrize("query", [
        "show me the document",
        "what does the adr say?",
        "explain the principle",
        "compare both",
        "the same please",
    ])
    def test_noun_phrase_detected(self, query):
        ctx = SessionContext()
        assert ctx._has_anaphora(query)


# =============================================================================
# SC10: _has_anaphora() — non-anaphoric queries
# =============================================================================

class TestAnaphoraRejection:
    @pytest.mark.parametrize("query", [
        "List all ADRs",
        "How many principles exist?",
        "What does ADR.12 decide?",
        "Compare ADR.12 and PCP.22",
        "What security patterns are used?",
    ])
    def test_non_anaphoric_rejected(self, query):
        ctx = SessionContext()
        assert not ctx._has_anaphora(query)


# =============================================================================
# SC11: _has_anaphora() — edge cases (word boundaries)
# =============================================================================

class TestAnaphoraEdgeCases:
    def test_item_does_not_match_it(self):
        """'item' contains 'it' but should not trigger anaphora."""
        ctx = SessionContext()
        assert not ctx._has_anaphora("List every item in the catalog")

    def test_them_at_end_of_query(self):
        ctx = SessionContext()
        assert ctx._has_anaphora("compare them")

    def test_it_at_start_of_query(self):
        ctx = SessionContext()
        assert ctx._has_anaphora("it decides on deployment")

    def test_the_one_phrase(self):
        ctx = SessionContext()
        assert ctx._has_anaphora("show me the one about security")


# =============================================================================
# SC12: Multi-turn scenario
# =============================================================================

class TestMultiTurnScenario:
    def test_three_turn_conversation(self):
        ctx = SessionContext()

        # Turn 1: user asks about ADR.12
        ctx.update("What does ADR.12 decide?", "lookup_doc", [_REF_ADR12])
        assert ctx.state.turn_count == 1

        # Turn 2: user asks follow-up "show it"
        resolved = ctx.resolve_refs("show it", [])
        assert resolved == [_REF_ADR12]
        ctx.update("show it", "lookup_doc", resolved)
        assert ctx.state.turn_count == 2

        # Turn 3: user asks new unrelated question
        resolved = ctx.resolve_refs("List all ADRs", [])
        assert resolved == []  # No injection — not anaphoric
        ctx.update("List all ADRs", "list", [])
        assert ctx.state.turn_count == 3
        # Refs preserved from turn 2 (no new refs in turn 3)
        assert ctx.state.last_doc_refs == [_REF_ADR12]

    def test_compare_then_followup(self):
        ctx = SessionContext()

        # Turn 1: compare two docs
        refs = [_REF_ADR12, _REF_PCP22]
        ctx.update("Compare ADR.12 and PCP.22", "compare", refs)

        # Turn 2: "tell me more about those"
        resolved = ctx.resolve_refs("tell me more about those", [])
        assert resolved == refs

    def test_refs_update_when_new_refs_provided(self):
        ctx = SessionContext()

        ctx.update("What does ADR.12 decide?", "lookup_doc", [_REF_ADR12])
        ctx.update("Show PCP.22", "lookup_doc", [_REF_PCP22])

        # Follow-up should use PCP.22, not ADR.12
        resolved = ctx.resolve_refs("explain it", [])
        assert resolved == [_REF_PCP22]
