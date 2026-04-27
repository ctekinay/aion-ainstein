"""Tests for MultiStepOrchestrator.

Covers:
- Multi-step execution with mocked stream_rag_response
- All-steps-empty fallback message
- Synthesis failure fallback (synthesis returns no text)
- Step result labeling format passed to synthesis
- Status events emitted per step and before synthesis
- Partial results: one step empty, one step with content
"""

import json
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest

from aion.orchestrator import MultiStepOrchestrator
from aion.persona import PersonaResult, PlanStep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_persona(steps: list[PlanStep], synthesis_instruction: str | None = None) -> PersonaResult:
    return PersonaResult(
        intent="retrieval",
        rewritten_query="test query",
        direct_response=None,
        original_message="original message",
        latency_ms=0,
        skill_tags=[],
        doc_refs=[],
        github_refs=[],
        complexity="multi-step",
        synthesis_instruction=synthesis_instruction,
        steps=steps,
    )


async def _rag_events(*responses: str) -> AsyncGenerator[str, None]:
    """Yield a sequence of complete SSE events for mocking stream_rag_response."""
    for response in responses:
        yield f"data: {json.dumps({'type': 'complete', 'response': response, 'sources': [], 'timing': {}})}\n\n"


async def _rag_status_then_complete(response: str) -> AsyncGenerator[str, None]:
    """Simulate realistic RAG output: status event followed by complete."""
    yield f"data: {json.dumps({'type': 'status', 'content': 'Searching...'})}\n\n"
    yield f"data: {json.dumps({'type': 'decision', 'content': 'Calling search_principles'})}\n\n"
    yield f"data: {json.dumps({'type': 'complete', 'response': response, 'sources': [], 'timing': {}})}\n\n"


def _collect_events(raw_events: list[str]) -> list[dict]:
    """Parse a list of raw SSE strings into event dicts."""
    result = []
    for ev in raw_events:
        if ev.startswith("data: "):
            result.append(json.loads(ev[6:].strip()))
    return result


# ---------------------------------------------------------------------------
# Multi-step execution
# ---------------------------------------------------------------------------

class TestMultiStepExecution:
    """Basic multi-step execution with 2 steps and successful synthesis."""

    @pytest.mark.asyncio
    async def test_two_steps_yield_status_per_step(self):
        """A 2-step plan yields 'Step 1/2' and 'Step 2/2' status events."""
        steps = [
            PlanStep(query="PCP.10 statement", skill_tags=[], doc_refs=["PCP.10"]),
            PlanStep(query="ADR.29 decision", skill_tags=[], doc_refs=["ADR.29"]),
        ]
        persona = _make_persona(steps)

        async def mock_rag(query, **kwargs):
            yield f"data: {json.dumps({'type': 'complete', 'response': f'Result for {query}', 'sources': [], 'timing': {}})}\n\n"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response") as mock_synth:
                async def _synth(*args, **kwargs):
                    yield "synthesis result"
                mock_synth.side_effect = _synth

                orch = MultiStepOrchestrator()
                events = []
                async for ev in orch.run(persona, "original", "conv-1", None):
                    events.append(ev)

        parsed = _collect_events(events)
        status_events = [e for e in parsed if e["type"] == "status"]
        assert any("Step 1/2" in e["content"] for e in status_events)
        assert any("Step 2/2" in e["content"] for e in status_events)

    @pytest.mark.asyncio
    async def test_synthesis_status_event_emitted(self):
        """'Synthesizing results...' status event is emitted before synthesis."""
        steps = [PlanStep(query="query", skill_tags=[], doc_refs=[])]
        persona = _make_persona(steps)

        async def mock_rag(query, **kwargs):
            yield f"data: {json.dumps({'type': 'complete', 'response': 'some result', 'sources': [], 'timing': {}})}\n\n"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response") as mock_synth:
                async def _synth(*args, **kwargs):
                    yield "done"
                mock_synth.side_effect = _synth

                events = []
                async for ev in MultiStepOrchestrator().run(persona, "msg", "c", None):
                    events.append(ev)

        parsed = _collect_events(events)
        assert any(e["type"] == "status" and "Synthesizing" in e["content"] for e in parsed)

    @pytest.mark.asyncio
    async def test_complete_event_contains_synthesis_text(self):
        """The final complete event's response field contains the synthesized text."""
        steps = [PlanStep(query="q", skill_tags=[], doc_refs=[])]
        persona = _make_persona(steps)

        async def mock_rag(query, **kwargs):
            yield f"data: {json.dumps({'type': 'complete', 'response': 'kb result', 'sources': [], 'timing': {}})}\n\n"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response") as mock_synth:
                async def _synth(*args, **kwargs):
                    yield "final "
                    yield "answer"
                mock_synth.side_effect = _synth

                events = []
                async for ev in MultiStepOrchestrator().run(persona, "msg", "c", None):
                    events.append(ev)

        parsed = _collect_events(events)
        complete = next(e for e in parsed if e["type"] == "complete")
        assert complete["response"] == "final answer"

    @pytest.mark.asyncio
    async def test_text_tokens_yielded_during_synthesis(self):
        """Text tokens are yielded per-chunk during synthesis streaming."""
        steps = [PlanStep(query="q", skill_tags=[], doc_refs=[])]
        persona = _make_persona(steps)

        async def mock_rag(query, **kwargs):
            yield f"data: {json.dumps({'type': 'complete', 'response': 'result', 'sources': [], 'timing': {}})}\n\n"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response") as mock_synth:
                async def _synth(*args, **kwargs):
                    for token in ["Hello", " world", "!"]:
                        yield token
                mock_synth.side_effect = _synth

                events = []
                async for ev in MultiStepOrchestrator().run(persona, "msg", "c", None):
                    events.append(ev)

        parsed = _collect_events(events)
        text_events = [e for e in parsed if e["type"] == "text"]
        assert [e["content"] for e in text_events] == ["Hello", " world", "!"]


# ---------------------------------------------------------------------------
# All-steps-empty fallback
# ---------------------------------------------------------------------------

class TestAllStepsEmpty:
    """When all RAG steps return empty responses, a user-facing fallback is emitted."""

    @pytest.mark.asyncio
    async def test_empty_rag_responses_yield_fallback_complete(self):
        """All steps return empty string → fallback complete event, no synthesis call."""
        steps = [
            PlanStep(query="q1", skill_tags=[], doc_refs=[]),
            PlanStep(query="q2", skill_tags=[], doc_refs=[]),
        ]
        persona = _make_persona(steps)

        async def mock_rag(query, **kwargs):
            yield f"data: {json.dumps({'type': 'complete', 'response': '', 'sources': [], 'timing': {}})}\n\n"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response") as mock_synth:
                events = []
                async for ev in MultiStepOrchestrator().run(persona, "msg", "c", None):
                    events.append(ev)

        mock_synth.assert_not_called()
        parsed = _collect_events(events)
        complete = next(e for e in parsed if e["type"] == "complete")
        assert "wasn't able to find" in complete["response"]

    @pytest.mark.asyncio
    async def test_no_complete_event_from_rag_yields_fallback(self):
        """RAG stream with no complete event → step_response stays None → fallback."""
        steps = [PlanStep(query="q", skill_tags=[], doc_refs=[])]
        persona = _make_persona(steps)

        async def mock_rag(query, **kwargs):
            yield f"data: {json.dumps({'type': 'status', 'content': 'Searching...'})}\n\n"
            # No complete event emitted

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response") as mock_synth:
                events = []
                async for ev in MultiStepOrchestrator().run(persona, "msg", "c", None):
                    events.append(ev)

        mock_synth.assert_not_called()
        parsed = _collect_events(events)
        complete = next(e for e in parsed if e["type"] == "complete")
        assert "wasn't able to find" in complete["response"]


# ---------------------------------------------------------------------------
# Synthesis failure fallback
# ---------------------------------------------------------------------------

class TestSynthesisFailureFallback:
    """When synthesis produces no text, the orchestrator emits a user-facing message."""

    @pytest.mark.asyncio
    async def test_empty_synthesis_yields_fallback_complete(self):
        """Synthesis stream yields nothing → fallback message in complete event."""
        steps = [PlanStep(query="q", skill_tags=[], doc_refs=[])]
        persona = _make_persona(steps)

        async def mock_rag(query, **kwargs):
            yield f"data: {json.dumps({'type': 'complete', 'response': 'some result', 'sources': [], 'timing': {}})}\n\n"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response") as mock_synth:
                async def _empty_synth(*args, **kwargs):
                    return
                    yield  # make it an async generator
                mock_synth.side_effect = _empty_synth

                events = []
                async for ev in MultiStepOrchestrator().run(persona, "msg", "c", None):
                    events.append(ev)

        parsed = _collect_events(events)
        complete = next(e for e in parsed if e["type"] == "complete")
        assert "unable to synthesize" in complete["response"]


# ---------------------------------------------------------------------------
# Step result labeling
# ---------------------------------------------------------------------------

class TestStepResultLabeling:
    """Labeled combined results are passed to stream_synthesis_response."""

    @pytest.mark.asyncio
    async def test_step_labels_in_synthesis_input(self):
        """Each step result is labeled with its query before being passed to synthesis."""
        steps = [
            PlanStep(query="PCP.10 principles", skill_tags=[], doc_refs=["PCP.10"]),
            PlanStep(query="ADR.29 decision", skill_tags=[], doc_refs=["ADR.29"]),
        ]
        persona = _make_persona(steps, synthesis_instruction="Compare them.")

        responses = ["PCP result text", "ADR result text"]
        call_index = 0

        async def mock_rag(query, **kwargs):
            nonlocal call_index
            resp = responses[call_index]
            call_index += 1
            yield f"data: {json.dumps({'type': 'complete', 'response': resp, 'sources': [], 'timing': {}})}\n\n"

        captured_rag_response = []

        async def mock_synth(original_message, rag_response, synthesis_instruction=None, artifact_context=None):
            captured_rag_response.append(rag_response)
            yield "ok"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response", side_effect=mock_synth):
                async for _ in MultiStepOrchestrator().run(persona, "msg", "c", None):
                    pass

        combined = captured_rag_response[0]
        assert "--- Result 1: PCP.10 principles ---" in combined
        assert "PCP result text" in combined
        assert "--- Result 2: ADR.29 decision ---" in combined
        assert "ADR result text" in combined

    @pytest.mark.asyncio
    async def test_synthesis_instruction_forwarded(self):
        """synthesis_instruction from PersonaResult is passed to stream_synthesis_response."""
        steps = [PlanStep(query="q", skill_tags=[], doc_refs=[])]
        persona = _make_persona(steps, synthesis_instruction="Custom instruction.")

        async def mock_rag(query, **kwargs):
            yield f"data: {json.dumps({'type': 'complete', 'response': 'result', 'sources': [], 'timing': {}})}\n\n"

        captured_instruction = []

        async def mock_synth(original_message, rag_response, synthesis_instruction=None, artifact_context=None):
            captured_instruction.append(synthesis_instruction)
            yield "done"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response", side_effect=mock_synth):
                async for _ in MultiStepOrchestrator().run(persona, "msg", "c", None):
                    pass

        assert captured_instruction[0] == "Custom instruction."


# ---------------------------------------------------------------------------
# Inner event suppression
# ---------------------------------------------------------------------------

class TestInnerEventSuppression:
    """Inner RAG events (decision, status, text) are suppressed; only orchestrator events forwarded."""

    @pytest.mark.asyncio
    async def test_inner_decision_events_not_forwarded(self):
        """Decision and status events from inner RAG calls are not yielded to the caller."""
        steps = [PlanStep(query="q", skill_tags=[], doc_refs=[])]
        persona = _make_persona(steps)

        async def mock_rag(query, **kwargs):
            yield f"data: {json.dumps({'type': 'decision', 'content': 'Calling search_principles'})}\n\n"
            yield f"data: {json.dumps({'type': 'status', 'content': 'Inner status'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'response': 'result', 'sources': [], 'timing': {}})}\n\n"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response") as mock_synth:
                async def _synth(*args, **kwargs):
                    yield "done"
                mock_synth.side_effect = _synth

                events = []
                async for ev in MultiStepOrchestrator().run(persona, "msg", "c", None):
                    events.append(ev)

        parsed = _collect_events(events)
        types = [e["type"] for e in parsed]
        assert "decision" not in types
        # The inner "Inner status" should not appear; only orchestrator-level status events
        inner_status = [e for e in parsed if e["type"] == "status" and e.get("content") == "Inner status"]
        assert inner_status == []

    @pytest.mark.asyncio
    async def test_orchestrator_status_events_are_forwarded(self):
        """Orchestrator-level status events ('Step N/M', 'Synthesizing') are forwarded."""
        steps = [PlanStep(query="q", skill_tags=[], doc_refs=[])]
        persona = _make_persona(steps)

        async def mock_rag(query, **kwargs):
            yield f"data: {json.dumps({'type': 'complete', 'response': 'r', 'sources': [], 'timing': {}})}\n\n"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response") as mock_synth:
                async def _synth(*args, **kwargs):
                    yield "done"
                mock_synth.side_effect = _synth

                events = []
                async for ev in MultiStepOrchestrator().run(persona, "msg", "c", None):
                    events.append(ev)

        parsed = _collect_events(events)
        status_contents = [e["content"] for e in parsed if e["type"] == "status"]
        assert any("Step 1/1" in c for c in status_contents)
        assert any("Synthesizing" in c for c in status_contents)


# ---------------------------------------------------------------------------
# Partial results
# ---------------------------------------------------------------------------

class TestPartialResults:
    """When some steps return content and others return empty, synthesis fires on available results."""

    @pytest.mark.asyncio
    async def test_partial_empty_step_synthesis_fires_on_available(self):
        """Step 2 returns empty → synthesis still fires using only Step 1's result."""
        steps = [
            PlanStep(query="q1", skill_tags=[], doc_refs=[]),
            PlanStep(query="q2", skill_tags=[], doc_refs=[]),
        ]
        persona = _make_persona(steps)

        responses_iter = iter(["step 1 result", ""])

        async def mock_rag(query, **kwargs):
            resp = next(responses_iter)
            yield f"data: {json.dumps({'type': 'complete', 'response': resp, 'sources': [], 'timing': {}})}\n\n"

        captured_rag_response = []

        async def mock_synth(original_message, rag_response, synthesis_instruction=None, artifact_context=None):
            captured_rag_response.append(rag_response)
            yield "partial synthesis"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            with patch("aion.orchestrator.stream_synthesis_response", side_effect=mock_synth):
                events = []
                async for ev in MultiStepOrchestrator().run(persona, "msg", "c", None):
                    events.append(ev)

        # Synthesis was called with only step 1's result
        assert len(captured_rag_response) == 1
        assert "step 1 result" in captured_rag_response[0]
        assert "q2" not in captured_rag_response[0]  # empty step not included

        parsed = _collect_events(events)
        complete = next(e for e in parsed if e["type"] == "complete")
        assert complete["response"] == "partial synthesis"
