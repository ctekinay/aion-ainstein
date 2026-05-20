"""Phase 1a.7: tests for the composed ``skosmos_define`` tool (ISS-001).

Two layers tested separately:
  - Pure helper (``aion.tools.skosmos.skosmos_define``): no ctx, no
    cache, no event emission. Asserts the three shape branches
    (single-vocab, multi-vocab disambiguation, no-match).
  - Agent-tool wrapper (defined inside ``_build_vocabulary_agent``):
    handles iteration-limit + decision event emission + populates
    ``pending_disambiguations``. Tested via the agent instance.

ISS-001 regression: ``what is active power?`` resolves to a single
vocab (EURLEX) and returns the authoritative definition in one call —
NOT via 16+ ``skosmos_search`` retries that exhaust the budget.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Layer 1 — pure helper
# ---------------------------------------------------------------------------

class TestSkosmosDefinePureHelper:
    """Pure ``aion.tools.skosmos.skosmos_define`` — no ctx, no cache,
    no event emission. Mocks ``skosmos_search`` + ``skosmos_concept_details``
    to control the inputs.
    """

    def test_single_vocab_returns_definition(self):
        """ISS-001 happy path: one hit (or all hits in the same vocab)
        → ``skosmos_concept_details`` called once, authoritative
        definition returned directly.
        """
        from aion.tools.skosmos import skosmos_define

        single_hit_search = {
            "results": [{
                "uri": "http://example.org/eurlex/active-power",
                "prefLabel": "active power",
                "vocab": "EURLEX",
                "definition": "",  # search returns empty by design
            }],
            "total_results": 1,
        }
        authoritative = {
            "uri": "http://example.org/eurlex/active-power",
            "prefLabel": "Active power",
            "definition": (
                "The real component of the apparent power at fundamental "
                "frequency, expressed in watts or multiples thereof."
            ),
            "altLabels": [],
            "broader": [],
            "narrower": [],
            "related": [],
        }

        with patch("aion.tools.skosmos.skosmos_search", return_value=single_hit_search) as mock_search, \
             patch("aion.tools.skosmos.skosmos_concept_details", return_value=authoritative) as mock_details:
            result = skosmos_define("active power")

        assert result == {
            "definition": authoritative["definition"],
            "vocabulary": "EURLEX",
            "uri": "http://example.org/eurlex/active-power",
            "prefLabel": "Active power",
            "hit_count": 1,
        }
        # The atomic composition fires search + details exactly once each —
        # NOT 16 search retries (the ISS-001 pre-fix behaviour).
        mock_search.assert_called_once()
        mock_details.assert_called_once()

    def test_all_hits_same_vocab_returns_definition(self):
        """If search returns multiple hits but all from the same
        vocabulary, take the top hit's details — still single-vocab.
        """
        from aion.tools.skosmos import skosmos_define

        same_vocab_hits = {
            "results": [
                {"uri": "u1", "prefLabel": "p1", "vocab": "EURLEX", "definition": ""},
                {"uri": "u2", "prefLabel": "p2", "vocab": "EURLEX", "definition": ""},
            ],
            "total_results": 2,
        }
        details = {"definition": "definition of top hit", "prefLabel": "p1"}

        with patch("aion.tools.skosmos.skosmos_search", return_value=same_vocab_hits), \
             patch("aion.tools.skosmos.skosmos_concept_details", return_value=details):
            result = skosmos_define("term")

        assert result["definition"] == "definition of top hit"
        assert result["vocabulary"] == "EURLEX"
        assert result["hit_count"] == 2

    def test_multi_vocab_returns_disambiguation(self):
        """If hits span vocabularies, return the disambiguation list —
        DON'T silently pick one. Matches the existing multi-vocab
        flow in vocabulary_agent.
        """
        from aion.tools.skosmos import skosmos_define

        multi_vocab_hits = {
            "results": [
                {"uri": "u1", "prefLabel": "asset", "vocab": "ESAV", "definition": ""},
                {"uri": "u2", "prefLabel": "asset", "vocab": "IEC61968", "definition": ""},
                {"uri": "u3", "prefLabel": "asset", "vocab": "IEC62443", "definition": ""},
            ],
            "total_results": 3,
        }

        with patch("aion.tools.skosmos.skosmos_search", return_value=multi_vocab_hits), \
             patch("aion.tools.skosmos.skosmos_concept_details") as mock_details:
            result = skosmos_define("asset")

        assert "disambiguation" in result
        assert result["vocabularies"] == ["ESAV", "IEC61968", "IEC62443"]  # sorted
        assert len(result["disambiguation"]) == 3
        # No drill-down attempted — user must disambiguate first.
        mock_details.assert_not_called()

    def test_no_match_returns_error(self):
        """No hits from search → return a clean error shape, no
        concept_details call."""
        from aion.tools.skosmos import skosmos_define

        empty = {"results": [], "total_results": 0}
        with patch("aion.tools.skosmos.skosmos_search", return_value=empty), \
             patch("aion.tools.skosmos.skosmos_concept_details") as mock_details:
            result = skosmos_define("nonexistent term")

        assert result == {"error": "no matches", "term": "nonexistent term"}
        mock_details.assert_not_called()

    def test_search_error_propagates_with_term(self):
        """If ``skosmos_search`` returns an error (service unavailable,
        HTTP failure), preserve that error and tag with the term so
        the caller can surface a useful message.
        """
        from aion.tools.skosmos import skosmos_define

        with patch("aion.tools.skosmos.skosmos_search", return_value={
            "results": [], "total_results": 0,
            "error": "SKOSMOS service unavailable",
        }):
            result = skosmos_define("active power")
        assert result["error"] == "SKOSMOS service unavailable"
        assert result["term"] == "active power"


# ---------------------------------------------------------------------------
# Layer 2 — ISS-001 regression via the agent wrapper
# ---------------------------------------------------------------------------

class TestIss001VocabularyThrashRegression:
    """ISS-001 regression: ``what is active power?`` resolves to a single
    EURLEX hit and returns the definition in one tool call. Pre-fix the
    vocabulary agent ran ~16 ``skosmos_search`` calls thrashing on
    variants before hitting the iteration-limit cap.

    These tests pin the post-fix behaviour through the agent tool
    wrapper layer (with the iteration-limit + event-emission concerns).
    """

    def test_iteration_limit_short_circuit_in_wrapper(self):
        """The agent wrapper respects ``check_iteration_limit()`` and
        returns a clean error when the budget is exhausted — the same
        guard every vocabulary tool uses.
        """
        from aion.agents import SessionContext
        from aion.agents.vocabulary_agent import _build_vocabulary_agent

        agent = _build_vocabulary_agent(toolkit=None)
        # Find the skosmos_define tool function (Pydantic AI registers
        # tools internally; the function is the raw callable).
        tool_fn = next(
            t.function for t in agent._function_toolset.tools.values()
            if t.name == "skosmos_define"
        )

        # SessionContext with max_tool_calls=0 → first iteration trips.
        ctx = SessionContext(max_tool_calls=0)
        rc = MagicMock()
        rc.deps = ctx

        result = tool_fn(rc, term="active power")
        assert result == {"error": "Tool call limit reached"}

    def test_single_vocab_returns_definition_via_wrapper(self):
        """ISS-001 happy path through the agent wrapper:
            * iteration budget OK
            * mocked single-vocab return from the pure helper
            * decision event emitted
            * pending_disambiguations NOT populated (single-vocab path)
        """
        from queue import Queue

        from aion.agents import SessionContext
        from aion.agents.vocabulary_agent import _build_vocabulary_agent
        from aion.events import Event

        agent = _build_vocabulary_agent(toolkit=None)
        tool_fn = next(
            t.function for t in agent._function_toolset.tools.values()
            if t.name == "skosmos_define"
        )

        q = Queue()
        ctx = SessionContext(event_queue=q, max_tool_calls=4)
        rc = MagicMock()
        rc.deps = ctx

        single_vocab_result = {
            "definition": (
                "The real component of the apparent power at fundamental "
                "frequency, expressed in watts or multiples thereof."
            ),
            "vocabulary": "EURLEX",
            "uri": "http://example.org/eurlex/active-power",
            "prefLabel": "Active power",
            "hit_count": 1,
        }
        with patch(
            "aion.agents.vocabulary_agent._skosmos_define",
            return_value=single_vocab_result,
        ) as mock_pure:
            result = tool_fn(rc, term="active power")

        # The wrapper called the pure helper exactly once
        mock_pure.assert_called_once_with(term="active power", lang="en", vocab=None)
        # The authoritative definition flows back unchanged
        assert "real component of the apparent power" in result["definition"]
        assert result["vocabulary"] == "EURLEX"
        # Decision event was emitted on the queue
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        # After _rewrite_decision, ``event.content`` is the human-readable
        # reasoning and ``event.tool`` carries the tool name.
        assert any(
            isinstance(e, Event) and e.type == "decision" and e.tool == "skosmos_define"
            for e in events
        ), [(e.type, e.tool, e.content) for e in events if isinstance(e, Event)]
        # Single-vocab path → no pending disambiguation recorded
        assert "active power" not in ctx.pending_disambiguations

    def test_multi_vocab_populates_pending_disambiguations(self):
        """Multi-vocab path: the wrapper records the disambiguation in
        ``ctx.deps.pending_disambiguations`` so the existing
        disambiguation gate on ``skosmos_concept_details`` fires for
        a follow-up call (the user picks a vocab).
        """
        from aion.agents import SessionContext
        from aion.agents.vocabulary_agent import _build_vocabulary_agent

        agent = _build_vocabulary_agent(toolkit=None)
        tool_fn = next(
            t.function for t in agent._function_toolset.tools.values()
            if t.name == "skosmos_define"
        )

        ctx = SessionContext(max_tool_calls=4)
        rc = MagicMock()
        rc.deps = ctx

        multi_result = {
            "disambiguation": [
                {"uri": "u1", "vocab": "ESAV", "prefLabel": "asset"},
                {"uri": "u2", "vocab": "IEC62443", "prefLabel": "asset"},
            ],
            "vocabularies": ["ESAV", "IEC62443"],
        }
        with patch(
            "aion.agents.vocabulary_agent._skosmos_define",
            return_value=multi_result,
        ):
            result = tool_fn(rc, term="asset")

        assert "disambiguation" in result
        # pending_disambiguations populated → existing gate fires for
        # a follow-up concept_details call until the user disambiguates.
        assert ctx.pending_disambiguations.get("asset") == ["ESAV", "IEC62443"]
