"""Web chat regression: count comparison queries must return numeric data, not list dumps.

Conversation flow:
1. "And can you show me DARs?"
2. "But I need DARs for ADRs"
3. "Do we have more DARs for ADRs than PCPs?"

Assert: last answer contains numeric comparison, not a list dump.

NOTE: These tests validate the intent_router classification logic offline.
They do NOT require a running web server or Weaviate instance.
For full end-to-end tests, use the regression runner.
"""

import re
import pytest

from src.intent_router import (
    heuristic_classify,
    handle_compare_concepts,
    Intent,
    EntityScope,
)


class TestCountComparisonConversation:
    """Simulate the count comparison conversation flow."""

    def test_show_me_dars_is_list(self):
        """'Show me DARs' is a list intent."""
        d = heuristic_classify("And can you show me DARs?")
        assert d.intent == Intent.LIST
        assert d.entity_scope in (
            EntityScope.DAR_ALL,
            EntityScope.DAR_ADR,
            EntityScope.DAR_PCP,
        )

    def test_dars_for_adrs_is_list(self):
        """'DARs for ADRs' is a list intent scoped to DAR_ADR."""
        d = heuristic_classify("But I need DARs for ADRs")
        # Could be LIST or SEMANTIC_ANSWER — but should NOT be compare
        assert d.intent in (Intent.LIST, Intent.SEMANTIC_ANSWER, Intent.LOOKUP_DOC)

    def test_more_dars_for_adrs_than_pcps_is_compare_counts(self):
        """The key test: 'Do we have more DARs for ADRs than PCPs?' must be COMPARE_COUNTS."""
        d = heuristic_classify("Do we have more DARs for ADRs than PCPs?")
        assert d.intent == Intent.COMPARE_COUNTS
        assert d.intent != Intent.LIST

    def test_compare_counts_not_a_list_dump(self):
        """Verify the response for count comparison is numeric, not a doc list."""
        d = heuristic_classify("Do we have more DARs for ADRs than PCPs?")
        # The response handler should produce numeric comparison
        # Here we just verify the intent is correct
        assert d.intent == Intent.COMPARE_COUNTS
        assert d.output_shape.value in ("table", "short_answer")


class TestNegativeCases:
    """Ensure list-triggering keywords don't override compare intent."""

    def test_dars_keyword_alone_is_not_compare(self):
        """Just mentioning DARs should be LIST, not compare."""
        d = heuristic_classify("Show me all DARs")
        assert d.intent == Intent.LIST

    def test_how_many_is_count_not_compare(self):
        """'How many ADRs?' is COUNT, not COMPARE_COUNTS."""
        d = heuristic_classify("How many ADRs are there?")
        assert d.intent == Intent.COUNT
        assert d.intent != Intent.COMPARE_COUNTS
