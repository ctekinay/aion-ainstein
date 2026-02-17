"""Test that _conversation_doc_refs is populated after queries with doc refs.

Validates the state management directly — not dependent on logging config.
Regression test for the bug where uvicorn's WARNING-level root logger caused
ROUTE_TRACE to be silently dropped, leaving _conversation_doc_refs empty
and breaking follow-up queries.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.base import AgentResponse


# =============================================================================
# Fixtures: mock agent + isolated module state
# =============================================================================

@dataclass
class _FakeRouteTrace:
    """Minimal route trace for logging."""
    doc_refs_detected: list[str] = field(default_factory=list)
    intent: str = "lookup_doc"

    def to_json(self):
        import json
        return json.dumps({
            "doc_refs_detected": self.doc_refs_detected,
            "intent": self.intent,
            "signals": {},
            "scores": {},
            "winner": self.intent,
            "threshold_met": True,
            "margin_ok": True,
            "path": "lookup_exact",
            "selected_chunk": "decision",
            "filters_applied": "",
            "bare_number_resolution": "",
            "semantic_postfilter_dropped": 0,
            "followup_injected": False,
        })


def _make_agent_response(canonical_ids: list[str]) -> AgentResponse:
    """Build an AgentResponse with sources carrying canonical_ids."""
    return AgentResponse(
        answer="test answer",
        sources=[
            {"canonical_id": cid, "type": cid.split(".")[0], "title": f"Doc {cid}"}
            for cid in canonical_ids
        ],
        confidence=0.95,
        agent_name="test",
    )


def _emit_route_trace(doc_refs: list[str]) -> None:
    """Emit a ROUTE_TRACE log line matching ArchitectureAgent._emit_trace."""
    trace = _FakeRouteTrace(doc_refs_detected=doc_refs)
    logging.getLogger("src.agents.architecture_agent").info(
        f"ROUTE_TRACE {trace.to_json()}"
    )


# =============================================================================
# Tests
# =============================================================================

class TestConversationDocRefsCaching:
    """Verify _conversation_doc_refs is populated after a query."""

    @pytest.fixture(autouse=True)
    def _isolate_state(self):
        """Clear module-level state before each test."""
        from src import chat_ui
        chat_ui._conversation_doc_refs.clear()
        yield
        chat_ui._conversation_doc_refs.clear()

    @pytest.fixture
    def mock_agent(self):
        """Mock ArchitectureAgent that returns known doc refs."""
        agent = AsyncMock()
        agent.query = AsyncMock(
            return_value=_make_agent_response(["ADR.12", "PCP.12"])
        )
        return agent

    def _run_stream(self, question, conv_id, mock_agent):
        """Run stream_architecture_response and drain all events."""
        from src.chat_ui import stream_architecture_response, _conversation_doc_refs

        async def _drain():
            with patch("src.chat_ui._architecture_agent", mock_agent):
                events = []
                async for event in stream_architecture_response(question, conv_id):
                    events.append(event)
            return events

        asyncio.new_event_loop().run_until_complete(_drain())
        return _conversation_doc_refs

    def test_refs_cached_via_sources_fallback(self, mock_agent):
        """Doc refs are cached from response.sources even without ROUTE_TRACE.

        This is the regression scenario: if logger level is too high,
        ROUTE_TRACE is never captured, but sources fallback still works.
        """
        # Suppress the architecture_agent logger to simulate the original bug
        arch_logger = logging.getLogger("src.agents.architecture_agent")
        original_level = arch_logger.level
        arch_logger.setLevel(logging.CRITICAL)  # suppress all INFO logs

        try:
            from src.chat_ui import _conversation_doc_refs
            conv_id = "test-conv-sources-fallback"
            self._run_stream("Compare ADR.12 and PCP.12", conv_id, mock_agent)

            assert conv_id in _conversation_doc_refs, (
                "Doc refs not cached — sources fallback failed"
            )
            cached_ids = [r["canonical_id"] for r in _conversation_doc_refs[conv_id]]
            assert "ADR.12" in cached_ids
            assert "PCP.12" in cached_ids
        finally:
            arch_logger.setLevel(original_level)

    def test_refs_cached_via_route_trace(self, mock_agent):
        """Doc refs are cached from ROUTE_TRACE when logger is at INFO.

        The primary path: trace handler captures the log, refs extracted
        from doc_refs_detected.
        """
        # Make the mock agent also emit a ROUTE_TRACE log (simulating real agent)
        async def _query_with_trace(question, **kwargs):
            _emit_route_trace(["ADR.12", "PCP.12"])
            return _make_agent_response(["ADR.12", "PCP.12"])

        mock_agent.query = AsyncMock(side_effect=_query_with_trace)

        from src.chat_ui import _conversation_doc_refs
        conv_id = "test-conv-route-trace"
        self._run_stream("Compare ADR.12 and PCP.12", conv_id, mock_agent)

        assert conv_id in _conversation_doc_refs
        cached_ids = [r["canonical_id"] for r in _conversation_doc_refs[conv_id]]
        assert "ADR.12" in cached_ids
        assert "PCP.12" in cached_ids

    def test_refs_carry_to_followup(self, mock_agent):
        """After caching, a follow-up query receives last_doc_refs."""
        from src.chat_ui import _conversation_doc_refs

        conv_id = "test-conv-followup"

        # Turn 1: query with doc refs
        self._run_stream("What does ADR.12 decide?", conv_id, mock_agent)
        assert conv_id in _conversation_doc_refs

        # Turn 2: follow-up — verify last_doc_refs was passed to query()
        self._run_stream("compare them", conv_id, mock_agent)

        # The second query() call should have received last_doc_refs
        calls = mock_agent.query.call_args_list
        assert len(calls) >= 2
        second_call_kwargs = calls[1][1] if calls[1][1] else {}
        last_refs = second_call_kwargs.get("last_doc_refs")
        assert last_refs is not None, "last_doc_refs not passed to follow-up query"
        ref_ids = [r["canonical_id"] for r in last_refs]
        assert "ADR.12" in ref_ids

    def test_empty_sources_no_cache(self, mock_agent):
        """No caching when response has no doc refs."""
        mock_agent.query = AsyncMock(
            return_value=AgentResponse(
                answer="No results", sources=[], confidence=0.0, agent_name="test"
            )
        )

        from src.chat_ui import _conversation_doc_refs
        conv_id = "test-conv-empty"
        self._run_stream("Hello", conv_id, mock_agent)

        assert conv_id not in _conversation_doc_refs

    def test_prefix_extracted_correctly(self, mock_agent):
        """Cached refs have correct prefix extracted from canonical_id."""
        mock_agent.query = AsyncMock(
            return_value=_make_agent_response(["ADR.12"])
        )

        from src.chat_ui import _conversation_doc_refs
        conv_id = "test-conv-prefix"
        self._run_stream("Show ADR.12", conv_id, mock_agent)

        assert conv_id in _conversation_doc_refs
        ref = _conversation_doc_refs[conv_id][0]
        assert ref["canonical_id"] == "ADR.12"
        assert ref["prefix"] == "ADR"
