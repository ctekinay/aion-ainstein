"""Tests for src/intent_router.py — intent-first query classification."""

import pytest

from src.intent_router import (
    Intent,
    EntityScope,
    OutputShape,
    IntentDecision,
    heuristic_classify,
    needs_clarification,
    _build_fallback_clarification,
    handle_compare_concepts,
    DEFAULT_CONFIDENCE_THRESHOLD,
)


class TestHeuristicClassifyMeta:
    """Meta intent: questions about AInstein itself."""

    def test_who_are_you(self):
        d = heuristic_classify("Who are you?")
        assert d.intent == Intent.META

    def test_explain_your_architecture(self):
        d = heuristic_classify("Explain your architecture")
        assert d.intent == Intent.META

    def test_are_you_elysia(self):
        d = heuristic_classify("Are you Elysia?")
        assert d.intent == Intent.META

    def test_how_do_you_work(self):
        d = heuristic_classify("How do you work?")
        assert d.intent == Intent.META


class TestHeuristicClassifyLookupDoc:
    """Specific document lookup via doc reference."""

    def test_adr_reference(self):
        d = heuristic_classify("Tell me about ADR.0025")
        assert d.intent == Intent.LOOKUP_DOC
        assert len(d.detected_entities) >= 1

    def test_pcp_reference(self):
        d = heuristic_classify("What is PCP.10?")
        assert d.intent == Intent.LOOKUP_DOC

    def test_dar_reference_approval(self):
        d = heuristic_classify("Who approved ADR.0025?")
        assert d.intent == Intent.LOOKUP_APPROVAL
        assert len(d.detected_entities) >= 1


class TestHeuristicClassifyCompareConcepts:
    """Compare concepts: definitional / difference questions."""

    def test_difference_adr_pcp(self):
        d = heuristic_classify("What's the difference between an ADR and a PCP?")
        assert d.intent == Intent.COMPARE_CONCEPTS

    def test_compare_adr_dar(self):
        d = heuristic_classify("Compare ADRs and DARs")
        assert d.intent == Intent.COMPARE_CONCEPTS

    def test_what_is_a_dar(self):
        """'What is a DAR?' must be definitional, NOT a list."""
        d = heuristic_classify("What is a DAR?")
        assert d.intent == Intent.COMPARE_CONCEPTS
        assert d.intent != Intent.LIST

    def test_what_is_an_adr(self):
        """'What is an ADR?' must be definitional, NOT a list."""
        d = heuristic_classify("What is an ADR?")
        assert d.intent == Intent.COMPARE_CONCEPTS
        assert d.intent != Intent.LIST

    def test_define_pcp(self):
        d = heuristic_classify("Define PCP")
        assert d.intent == Intent.COMPARE_CONCEPTS


class TestHeuristicClassifyCompareCounts:
    """Compare counts: numeric comparisons."""

    def test_more_dars_for_adrs_than_pcps(self):
        d = heuristic_classify("Do we have more DARs for ADRs than PCPs?")
        assert d.intent == Intent.COMPARE_COUNTS

    def test_fewer_policies_than_adrs(self):
        d = heuristic_classify("Are there fewer policies than ADRs?")
        assert d.intent == Intent.COMPARE_COUNTS


class TestHeuristicClassifyList:
    """List intent: explicit list requests."""

    def test_list_adrs(self):
        d = heuristic_classify("List all ADRs")
        assert d.intent == Intent.LIST
        assert d.entity_scope == EntityScope.ADR

    def test_show_principles(self):
        d = heuristic_classify("Show me all principles")
        assert d.intent == Intent.LIST
        assert d.entity_scope == EntityScope.PCP

    def test_what_adrs_exist(self):
        d = heuristic_classify("What ADRs exist?")
        assert d.intent == Intent.LIST

    def test_which_policies_do_we_have(self):
        d = heuristic_classify("Which policies do we have?")
        assert d.intent == Intent.LIST
        assert d.entity_scope == EntityScope.POLICY


class TestHeuristicClassifyCount:
    """Count intent: total/number questions."""

    def test_how_many_adrs(self):
        d = heuristic_classify("How many ADRs are there?")
        assert d.intent == Intent.COUNT

    def test_total_number_of_principles(self):
        d = heuristic_classify("Total number of principles?")
        assert d.intent == Intent.COUNT


class TestHeuristicClassifySemanticAnswer:
    """Semantic answer: domain questions without specific intent patterns."""

    def test_esa_domain_question(self):
        d = heuristic_classify("What architecture decisions affect API design?")
        assert d.intent == Intent.SEMANTIC_ANSWER

    def test_governance_question(self):
        d = heuristic_classify("How does ESA governance handle data quality?")
        assert d.intent == Intent.SEMANTIC_ANSWER


class TestHeuristicClassifyUnknown:
    """Unknown: no ESA cues, no intent patterns."""

    def test_random_question(self):
        d = heuristic_classify("What's the weather like today?")
        assert d.intent == Intent.UNKNOWN
        assert d.confidence < DEFAULT_CONFIDENCE_THRESHOLD

    def test_greeting(self):
        d = heuristic_classify("Hello there!")
        assert d.intent == Intent.UNKNOWN


class TestEntityScopeDetection:
    """Verify entity scope is correctly identified."""

    def test_adr_scope(self):
        d = heuristic_classify("List ADRs")
        assert d.entity_scope == EntityScope.ADR

    def test_dar_adr_scope(self):
        d = heuristic_classify("Show DARs for ADRs")
        assert d.entity_scope == EntityScope.DAR_ADR

    def test_dar_pcp_scope(self):
        d = heuristic_classify("Show DARs for principles")
        assert d.entity_scope == EntityScope.DAR_PCP

    def test_dar_all_scope(self):
        d = heuristic_classify("Show all DARs")
        assert d.entity_scope == EntityScope.DAR_ALL

    def test_policy_scope(self):
        d = heuristic_classify("List policies")
        assert d.entity_scope == EntityScope.POLICY


class TestNeedsClarification:
    """Low confidence triggers clarification."""

    def test_low_confidence_needs_clarification(self):
        d = IntentDecision(
            intent=Intent.UNKNOWN,
            entity_scope=EntityScope.UNKNOWN,
            output_shape=OutputShape.CLARIFICATION,
            confidence=0.20,
        )
        assert needs_clarification(d) is True

    def test_high_confidence_no_clarification(self):
        d = IntentDecision(
            intent=Intent.LIST,
            entity_scope=EntityScope.ADR,
            output_shape=OutputShape.LIST,
            confidence=0.90,
        )
        assert needs_clarification(d) is False

    def test_unknown_intent_always_clarifies(self):
        d = IntentDecision(
            intent=Intent.UNKNOWN,
            entity_scope=EntityScope.UNKNOWN,
            output_shape=OutputShape.CLARIFICATION,
            confidence=0.90,
        )
        assert needs_clarification(d) is True


class TestBuildClarificationResponse:
    """Clarification responses are well-formed."""

    def test_clarification_with_options(self):
        d = IntentDecision(
            intent=Intent.UNKNOWN,
            entity_scope=EntityScope.UNKNOWN,
            output_shape=OutputShape.CLARIFICATION,
            confidence=0.20,
            clarification_options=["Search knowledge base", "List documents"],
        )
        result = _build_fallback_clarification(d)
        assert "clarify" in result.lower() or "not sure" in result.lower()
        assert "Search knowledge base" in result

    def test_clarification_without_options(self):
        d = IntentDecision(
            intent=Intent.UNKNOWN,
            entity_scope=EntityScope.UNKNOWN,
            output_shape=OutputShape.CLARIFICATION,
            confidence=0.20,
        )
        result = _build_fallback_clarification(d)
        assert "list" in result.lower()
        assert "definition" in result.lower() or "comparison" in result.lower()


class TestHandleCompareConcepts:
    """Deterministic concept comparison responses."""

    def test_adr_vs_pcp(self):
        result = handle_compare_concepts("What's the difference between ADR and PCP?")
        assert "ADR" in result
        assert "PCP" in result or "Principle" in result
        assert "decision" in result.lower()

    def test_adr_vs_dar(self):
        result = handle_compare_concepts("Difference between ADR and DAR?")
        assert "ADR" in result
        assert "DAR" in result
        assert "approval" in result.lower()

    def test_no_list_dump(self):
        """compare_concepts must NOT produce numbered list items."""
        result = handle_compare_concepts("Compare ADR and PCP")
        # Should not have numbered list (1., 2., etc.) that looks like doc listing
        import re
        numbered_list = re.findall(r"^\d+\.\s+ADR\.", result, re.MULTILINE)
        assert len(numbered_list) == 0, "compare_concepts must not dump a list of ADRs"


class TestNegativeRouting:
    """Ensure common misroutes do NOT happen."""

    def test_what_is_adr_is_not_list(self):
        """'What is an ADR?' must NOT route to LIST."""
        d = heuristic_classify("What is an ADR?")
        assert d.intent != Intent.LIST

    def test_what_is_dar_is_not_list(self):
        """'What is a DAR?' must NOT route to LIST."""
        d = heuristic_classify("What is a DAR?")
        assert d.intent != Intent.LIST

    def test_difference_is_not_list(self):
        """'What's the difference between ADR and PCP?' must NOT route to LIST."""
        d = heuristic_classify("What's the difference between an ADR and a PCP?")
        assert d.intent != Intent.LIST

    def test_comparative_count_is_not_list(self):
        """'Do we have more DARs for ADRs than PCPs?' must NOT route to LIST."""
        d = heuristic_classify("Do we have more DARs for ADRs than PCPs?")
        assert d.intent != Intent.LIST


class TestIntentDecisionSerialization:
    """IntentDecision can be serialized to dict."""

    def test_to_dict(self):
        d = IntentDecision(
            intent=Intent.LIST,
            entity_scope=EntityScope.ADR,
            output_shape=OutputShape.LIST,
            confidence=0.85,
            reasoning="test",
        )
        result = d.to_dict()
        assert result["intent"] == "list"
        assert result["entity_scope"] == "adr"
        assert result["output_shape"] == "list"
        assert result["confidence"] == 0.85
