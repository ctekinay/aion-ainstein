"""Multi-step orchestrator: executes a Persona plan and yields SSE events.

Sequential execution is intentional for Phase 2 — simpler, debuggable, and
avoids concurrent Weaviate/LLM load on local models. The run() interface is
compatible with asyncio.gather()-based parallel execution in Phase 3 without
caller changes.

TODO Phase 3: collect sources from each step's complete event and merge into
the synthesis complete so the UI can show citations for multi-step queries.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import structlog

from aion.agents import AGENT_LABELS
from aion.events import Event
from aion.generation import stream_synthesis_response
from aion.text_utils import elapsed_ms

if TYPE_CHECKING:
    from aion.persona import PersonaResult

logger = structlog.get_logger(__name__)


class MultiStepOrchestrator:
    """Execute a multi-step Persona plan and yield a single streamed SSE response."""

    async def run(
        self,
        persona_result: PersonaResult,
        original_message: str,
        conversation_id: str,
        artifact_context: str | None,
        prior_sources: list[dict] | None = None,
        message_history: list | None = None,
        running_summary: str | None = None,
    ) -> AsyncGenerator[Event, None]:
        """Execute each step, synthesize results, yield typed Event objects.

        Phase 1a.4: yields typed ``Event`` objects (not SSE strings). The
        outermost endpoint converts via ``Event.to_sse()`` at the FastAPI
        boundary. Inner-stream consumption no longer round-trips through
        ``json.loads`` — the inner ``stream_rag_response`` also yields
        ``Event``, so attribute access (``event.type``, ``event.response``)
        replaces the pre-1a string-parse pattern.

        Yields:
            status events for each step and synthesis progress,
            text events streaming the synthesis response token-by-token,
            a single complete event with the final synthesized response.

        Inner RAG step events (decision, thinking, status) are suppressed from
        the caller — only orchestrator-level status events are forwarded. This
        prevents the thinking panel from showing 2–3× the normal decision events,
        which would be unreadable in multi-step mode. Inner events are logged at
        DEBUG for observability.
        """
        # Import here to avoid circular import (chat_ui defines stream_rag_response)
        from aion.chat_ui import stream_rag_response

        steps = persona_result.steps
        n = len(steps)
        step_results: list[str] = []
        step_timings: list[dict] = []

        for i, step in enumerate(steps):
            yield Event(
                type="status",
                agent=AGENT_LABELS["orchestrator"],
                content=f"Step {i + 1}/{n}: Searching knowledge base...",
            )
            logger.info("orchestrator_step_start", step=i + 1, total_steps=n, query=step.query[:200])
            step_start = time.perf_counter()

            step_response: str | None = None
            async for event in stream_rag_response(
                step.query,
                skill_tags=step.skill_tags,
                doc_refs=step.doc_refs,
                conversation_id=conversation_id,
                artifact_context=artifact_context,
                prior_sources=prior_sources,
                message_history=message_history,
                running_summary=running_summary,
                step_index=i + 1,
            ):
                if event.type == "complete":
                    step_response = event.response or ""
                    continue  # capture internally, do not forward
                # Suppress inner events from the thinking panel; log at
                # DEBUG for observability. (Pre-1a, this branch did
                # ``json.loads(event_str.replace("data: ", "").strip())``
                # before reading the type — Phase 1a.4 retires that
                # round-trip via direct attribute access.)
                logger.debug("inner_event_suppressed", step=i + 1, event_type=event.type)

            step_ms = elapsed_ms(step_start)
            logger.info(
                "orchestrator_step_complete",
                step=i + 1,
                response_chars=len(step_response or ""),
                latency_ms=step_ms,
                preview=(step_response or "")[:200],
            )
            step_timings.append({"step": i + 1, "retrieval_ms": step_ms})

            if step_response:
                step_results.append(step_response)

        if len(step_results) < n:
            logger.warning(
                "orchestrator_steps_missing",
                expected=n,
                received=len(step_results),
            )
        if not step_results:
            no_results_msg = (
                "I wasn't able to find relevant information for this query. "
                "Try asking about each document separately."
            )
            yield Event(type="complete", response=no_results_msg, sources=[], timing={})
            return

        # Label each result with its step query so the synthesis LLM has clear provenance
        combined = "\n\n".join(
            f"--- Result {i + 1}: {step.query} ---\n\n{result}"
            for i, (step, result) in enumerate(zip(steps, step_results))
        )

        yield Event(
            type="status",
            agent=AGENT_LABELS["synthesis"],
            content=f"Synthesizing {len(step_results)} results into a combined response...",
        )
        logger.info("orchestrator_synthesis_start", combined_chars=len(combined))
        synthesis_start = time.perf_counter()

        accumulated: list[str] = []
        async for token in stream_synthesis_response(
            original_message,
            combined,
            persona_result.synthesis_instruction,
            artifact_context=artifact_context,
        ):
            accumulated.append(token)
            yield Event(type="text", content=token)

        synthesis_ms = elapsed_ms(synthesis_start)
        synthesis_text = "".join(accumulated)
        if not synthesis_text:
            synthesis_text = (
                "I found relevant information but was unable to synthesize it. "
                "Try asking about each document separately."
            )

        logger.info(
            "orchestrator_synthesis_complete",
            response_chars=len(synthesis_text),
            latency_ms=synthesis_ms,
        )

        total_retrieval_ms = sum(s["retrieval_ms"] for s in step_timings)
        timing = {
            "total_ms": total_retrieval_ms + synthesis_ms,
            "retrieval_ms": total_retrieval_ms,
            "synthesis_ms": synthesis_ms,
            "steps": step_timings,
        }
        yield Event(type="complete", response=synthesis_text, sources=[], timing=timing)
