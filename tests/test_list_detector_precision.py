"""Tests for PR Y: list detector precision.

Verifies that:
1. "What is an ADR?" does NOT trigger list routing
2. "list ADRs" still triggers list routing
3. "What ADRs exist?" still triggers list routing
4. Bare doc-type mention without list verb does NOT list
"""

import re
import pytest

from src.elysia_agents import is_list_query


class TestListDetectorPrecision:
    """Bare doc-type keywords without list intent must NOT trigger listing."""

    # --- Should be list queries (have list verbs/patterns) ---

    @pytest.mark.parametrize("query", [
        "list ADRs",
        "list all ADRs",
        "show me the ADRs",
        "What ADRs exist?",
        "Which ADRs do we have?",
        "show all principles",
        "list policies",
        "enumerate all DARs",
        "list principles",
        "What principles exist?",
    ])
    def test_list_queries_detected(self, query):
        assert is_list_query(query), f"'{query}' should be a list query"

    # --- Should NOT be list queries ---

    @pytest.mark.parametrize("query", [
        "What is an ADR?",
        "What's the difference between an ADR and a PCP?",
        "Explain the ADR process",
        "Tell me about ADR.0025",
        "How does the ADR lifecycle work?",
        "What is a principle?",
        "Describe the policy framework",
    ])
    def test_non_list_queries_not_detected(self, query):
        assert not is_list_query(query), f"'{query}' should NOT be a list query"


class TestListIntentRegex:
    """The list-intent regex used in the routing chain catches the right patterns."""

    _LIST_INTENT_RE = re.compile(
        r"\blist\b|\bshow\b|\benumerate\b|\ball\b|\bwhich\b"
        r"|\bexist(?:s|ing)?\b|\bprovide\b"
        r"|\bhow\s+about\b|\bwhat\s+about\b"
        r"|\bhow\s+many\b",
        re.IGNORECASE,
    )

    @pytest.mark.parametrize("query", [
        "list ADRs",
        "show me all ADRs",
        "which principles exist?",
        "how about DARs?",
        "what about policies?",
        "how many ADRs do we have?",
        "And can you provide DARs?",
    ])
    def test_list_intent_present(self, query):
        assert self._LIST_INTENT_RE.search(query.lower()), (
            f"'{query}' should have list intent"
        )

    @pytest.mark.parametrize("query", [
        "What is an ADR?",
        "What is a DAR?",
        "What is a DAR? Do you know?",
        "What's the difference between an ADR and a PCP?",
        "Tell me about ADR.0025",
        "Explain the ADR process",
        "describe the principle",
    ])
    def test_list_intent_absent(self, query):
        assert not self._LIST_INTENT_RE.search(query.lower()), (
            f"'{query}' should NOT have list intent"
        )
