"""ArchiMateAgent — Pydantic AI agent for ArchiMate model operations.

Handles validation, inspection, merge, and artifact persistence for
ArchiMate 3.2 Open Exchange XML models.

Stateless per query — the Persona handles multi-turn context via query
rewriting before this agent is called.
"""

import logging
import time
from queue import Queue

from pydantic_ai import Agent
from pydantic_ai.tools import RunContext

from aion.agents import AGENT_LABELS, SessionContext, _get_max_tool_calls
from aion.config import settings
from aion.text_utils import elapsed_ms
from aion.tools.archimate import (
    inspect_archimate_model as _inspect_archimate,
)
from aion.tools.archimate import (
    merge_archimate_view as _merge_archimate_view,
)
from aion.tools.archimate import (
    validate_archimate as _validate_archimate,
)
from aion.tools.artifacts import (
    get_artifact as _get_artifact_fn,
)
from aion.tools.artifacts import (
    save_artifact as _save_artifact_fn,
)
from aion.tools.capability_gaps import request_data as _request_data
from aion.tools.rag_search import _get_skill_content

logger = logging.getLogger(__name__)


def _build_archimate_agent() -> Agent[SessionContext, str]:
    """Build the Pydantic AI agent with ArchiMate + artifact tools (once at init)."""
    agent: Agent[SessionContext, str] = Agent(
        model=settings.build_pydantic_ai_model("tree"),
        deps_type=SessionContext,
        retries=1,
    )

    @agent.system_prompt
    def dynamic_system_prompt(ctx: RunContext[SessionContext]) -> str:
        return ctx.deps.system_prompt

    # ── ArchiMate tools (1-3) ──
    # NOTE: Decision events use "Decision: X Reasoning: Y" format which is
    # rewritten to human-readable text by SessionContext.emit_event().
    # See agents/__init__.py:_rewrite_decision for the rewrite logic.

    @agent.tool
    def validate_archimate(
        ctx_: RunContext[SessionContext], xml_content: str
    ) -> dict:
        """Validate an ArchiMate 3.2 Open Exchange XML model.

        Checks element types, relationship types, and source/target
        compatibility against the ArchiMate 3.2 specification.

        Args:
            xml_content: Complete ArchiMate XML string

        Returns:
            Dict with valid (bool), element_count, relationship_count,
            errors (list), and warnings (list)
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: validate_archimate Reasoning: Validating ArchiMate XML",
            "elapsed_ms": elapsed,
        })
        return _validate_archimate(xml_content)

    @agent.tool
    def inspect_archimate_model(
        ctx_: RunContext[SessionContext], xml_content: str
    ) -> dict:
        """Inspect an ArchiMate model to understand its structure.

        Parses an ArchiMate XML model and returns a summary of its
        elements by layer, relationships by type, existing views,
        and element/relationship indices.

        Args:
            xml_content: Complete ArchiMate XML string

        Returns:
            Dict with model_name, element_count, elements_by_layer,
            relationships_by_type, existing_views, element_index,
            relationship_index
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: inspect_archimate_model Reasoning: Inspecting ArchiMate model structure",
            "elapsed_ms": elapsed,
        })
        return _inspect_archimate(xml_content)

    @agent.tool
    def merge_archimate_view(
        ctx_: RunContext[SessionContext],
        model_xml: str,
        fragment_xml: str,
    ) -> dict:
        """Merge an ArchiMate view fragment into an existing model.

        Args:
            model_xml: The base ArchiMate model XML
            fragment_xml: The view fragment XML to merge in

        Returns:
            Dict with success (bool), merged_xml, elements_added,
            relationships_added, views_added, error (str or None)
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: merge_archimate_view Reasoning: Merging view fragment into model",
            "elapsed_ms": elapsed,
        })
        return _merge_archimate_view(model_xml, fragment_xml)

    # ── Artifact tools (4-5) ──

    @agent.tool
    def save_artifact(
        ctx_: RunContext[SessionContext],
        filename: str,
        content: str,
        content_type: str,
        summary: str = "",
    ) -> dict:
        """ALWAYS call this tool after generating any structured output
        (ArchiMate XML, JSON schemas, configuration files, etc.).
        Call save_artifact BEFORE writing the text response — the artifact
        must be persisted so the user can request refinements in follow-up
        messages. If you skip this tool, the generated content will be lost
        between turns.

        Args:
            filename: Descriptive filename (e.g., "oauth2-model.archimate.xml")
            content: The full artifact content
            content_type: MIME-like type (e.g., "archimate/xml")
            summary: Brief description

        Returns:
            Dict with artifact_id and filename
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": f"Decision: save_artifact Reasoning: Saving artifact '{filename}'",
            "elapsed_ms": elapsed,
        })
        return _save_artifact_fn(
            filename=filename,
            content=content,
            content_type=content_type,
            summary=summary,
            conversation_id=ctx_.deps.conversation_id,
            event_queue=ctx_.deps.event_queue,
        )

    @agent.tool
    def get_artifact(
        ctx_: RunContext[SessionContext], content_type: str = ""
    ) -> dict:
        """ALWAYS call this tool FIRST when the user wants to refine,
        modify, review, compare, or analyze a previously generated or
        uploaded artifact. This loads the full content from the previous
        turn so you can work with the complete artifact.

        Args:
            content_type: Optional filter (e.g., "archimate/xml").
                Leave empty for any type.

        Returns:
            Dict with filename, content, content_type, summary — or error
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: get_artifact Reasoning: Loading artifact from previous turn",
            "elapsed_ms": elapsed,
        })
        return _get_artifact_fn(
            conversation_id=ctx_.deps.conversation_id,
            content_type=content_type,
        )

    # ── Capability gap probe (6) ──

    @agent.tool
    def request_data(ctx_: RunContext[SessionContext], description: str) -> str:
        """Use this when you need data that none of your other tools can
        provide. Describe exactly what data you need and why. This tool
        will retrieve it for you.

        Args:
            description: Precise description of the data you need and why

        Returns:
            The requested data
        """
        if ctx_.deps.check_iteration_limit():
            return "Tool call limit reached"
        return _request_data(
            description=description,
            conversation_id=ctx_.deps.conversation_id,
            agent="archimate",
        )

    return agent


class ArchiMateAgent:
    """Pydantic AI agent for ArchiMate model operations.

    Tools:
      1. validate_archimate — validate XML against ArchiMate 3.2 spec
      2. inspect_archimate_model — parse XML, return structure summary
      3. merge_archimate_view — merge view fragment into model
      4. save_artifact — persist generated/modified content
      5. get_artifact — load previous artifact for refinement
      6. request_data — capability gap probe
    """

    def __init__(self):
        self._agent = _build_archimate_agent()

    async def query(
        self,
        question: str,
        event_queue: Queue | None = None,
        skill_tags: list[str] | None = None,
        doc_refs: list[str] | None = None,
        conversation_id: str | None = None,
        artifact_context: str | None = None,
    ) -> tuple[str, list[dict]]:
        """Process an ArchiMate query using the Pydantic AI agent.

        Returns (response_text, retrieved_objects) tuple.
        """
        skill_content = _get_skill_content(question, skill_tags=skill_tags or ["archimate"])

        ctx = SessionContext(
            conversation_id=conversation_id,
            event_queue=event_queue,
            doc_refs=doc_refs or [],
            skill_tags=skill_tags or [],
            artifact_context=artifact_context,
            agent_label=AGENT_LABELS["archimate_agent"],
            system_prompt=self._build_system_prompt(skill_content, artifact_context),
            _query_start=time.perf_counter(),
            max_tool_calls=_get_max_tool_calls("archimate_agent", 8),
        )

        logger.info(f"ArchiMateAgent processing: {question}")

        try:
            result = await self._agent.run(question, deps=ctx)
            response = result.output
        except Exception as e:
            logger.exception("ArchiMateAgent error")
            response = f"I encountered an error processing the ArchiMate model: {e}"

        elapsed = elapsed_ms(ctx._query_start)
        logger.info(
            "ArchiMateAgent complete: %d ms, %d tool calls",
            elapsed, ctx.tool_call_count,
        )

        return response, ctx.retrieved_objects

    @staticmethod
    def _build_system_prompt(skill_content: str, artifact_context: str | None) -> str:
        """Build the system prompt from skill content + optional artifact."""
        parts = [
            "You are AInstein, the Energy System Architecture AI Assistant at Alliander.",
            "",
            "Your role is to help architects work with ArchiMate 3.2 models — "
            "validating, inspecting, and merging XML content.",
        ]
        if skill_content:
            parts.extend(["", skill_content])
        parts.extend([
            "",
            "Guidelines:",
            "- Use get_artifact FIRST when the user references a previous model",
            "- Always validate ArchiMate XML before saving as an artifact",
            "- Use save_artifact after any model modifications",
            "- Be specific about validation errors — cite element IDs and types",
        ])
        if artifact_context:
            parts.extend(["", artifact_context])
        return "\n".join(parts)
