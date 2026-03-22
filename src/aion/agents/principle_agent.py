"""PrincipleAgent — Pydantic AI agent for architecture principles.

Handles generation, validation, quality assessment, and artifact persistence
for architecture and enterprise principles following TOGAF-aligned criteria.

Stateless per query — the Persona handles multi-turn context via query
rewriting before this agent is called.
"""

import logging
import time
from queue import Queue

from pydantic_ai import Agent
from pydantic_ai.tools import RunContext
from weaviate import WeaviateClient

from aion.agents import AGENT_LABELS, SessionContext, _get_max_tool_calls
from aion.config import settings
from aion.text_utils import elapsed_ms
from aion.tools.artifacts import (
    get_artifact as _get_artifact_fn,
)
from aion.tools.artifacts import (
    save_artifact as _save_artifact_fn,
)
from aion.tools.capability_gaps import request_data as _request_data
from aion.tools.rag_search import RAGToolkit, _get_skill_content

logger = logging.getLogger(__name__)

# Required sections for a valid principle document
_REQUIRED_SECTIONS = ("Statement", "Rationale", "Implications")


def _build_principle_agent(toolkit: RAGToolkit) -> Agent[SessionContext, str]:
    """Build the Pydantic AI agent with principle + artifact tools (once at init)."""
    agent: Agent[SessionContext, str] = Agent(
        model=settings.build_pydantic_ai_model("tree"),
        deps_type=SessionContext,
        retries=1,
    )

    @agent.system_prompt
    def dynamic_system_prompt(ctx: RunContext[SessionContext]) -> str:
        return ctx.deps.system_prompt

    # ── Principle tools (1-2) ──
    # NOTE: Decision events use "Decision: X Reasoning: Y" format which is
    # rewritten to human-readable text by SessionContext.emit_event().
    # See agents/__init__.py:_rewrite_decision for the rewrite logic.

    @agent.tool
    def search_related_principles(
        ctx_: RunContext[SessionContext], query: str, limit: int = 6
    ) -> list[dict]:
        """Search existing principles in the knowledge base for generation context.

        Use this BEFORE generating a principle to:
        - Avoid duplicating existing principles
        - Ensure consistency with the existing principle set
        - Use similar principles as structural references

        Args:
            query: Topic or theme to search for (e.g. "data sovereignty", "API design")
            limit: Maximum number of principles to return (default 6)

        Returns:
            List of dicts with principle_number, title, content, owner_team fields
        """
        if ctx_.deps.check_iteration_limit():
            return [{"error": "Tool call limit reached"}]
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": f"Decision: search_related_principles Reasoning: Searching KB for context on '{query}'",
            "elapsed_ms": elapsed,
        })
        try:
            return toolkit.search_principles(query, limit=limit)
        except Exception as e:
            logger.exception("search_related_principles error")
            return [{"error": str(e)}]

    @agent.tool
    def search_principles(
        ctx_: RunContext[SessionContext], query: str, limit: int = 10
    ) -> list[dict]:
        """Search principles by topic or identifier for quality assessment.

        Use this to retrieve specific principles when the user asks to assess,
        evaluate, or review principle quality. Supports PCP number lookups
        (e.g. "0022" for PCP.22) and topic-based search.

        Args:
            query: Search query — use 4-digit number for ID lookups, or topic text
            limit: Maximum number of results to return

        Returns:
            List of matching principles with all available metadata and content
        """
        if ctx_.deps.check_iteration_limit():
            return [{"error": "Tool call limit reached"}]
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": f"Decision: search_principles Reasoning: Searching principles for '{query}'",
            "elapsed_ms": elapsed,
        })
        try:
            result = toolkit.search_principles(query, limit, doc_refs=ctx_.deps.doc_refs)
            ctx_.deps.retrieved_objects.extend(result)
            ctx_.deps.emit_event({
                "type": "status",
                "content": f"Found {len(result)} principle results",
                "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
            })
            return result
        except Exception as e:
            logger.exception("search_principles error")
            return [{"error": str(e)}]

    @agent.tool
    def list_principles(ctx_: RunContext[SessionContext]) -> list[dict]:
        """List ALL architecture and governance principles (PCPs) in the system.

        Use this when assessing a broad set of principles, or when the user asks
        to evaluate, compare, or classify multiple principles without specifying
        exact IDs.

        Returns:
            Complete list of all principles with all available metadata
        """
        if ctx_.deps.check_iteration_limit():
            return [{"error": "Tool call limit reached"}]
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: list_principles Reasoning: Listing all principles",
            "elapsed_ms": elapsed,
        })
        try:
            result = toolkit.list_principles()
            ctx_.deps.retrieved_objects.extend(result)
            ctx_.deps.emit_event({
                "type": "status",
                "content": f"Found {len(result)} principles",
                "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
            })
            return result
        except Exception as e:
            logger.exception("list_principles error")
            return [{"error": str(e)}]

    @agent.tool
    def validate_principle_structure(
        ctx_: RunContext[SessionContext], principle_text: str
    ) -> dict:
        """Validate that a principle document contains all required sections.

        Checks for the presence of Statement, Rationale, and Implications sections.

        Args:
            principle_text: The generated principle in markdown format

        Returns:
            Dict with valid (bool), missing_sections (list), and message (str)
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: validate_principle_structure Reasoning: Validating principle sections",
            "elapsed_ms": elapsed,
        })
        missing = [s for s in _REQUIRED_SECTIONS if f"**{s}**" not in principle_text and f"## {s}" not in principle_text]
        if missing:
            return {
                "valid": False,
                "missing_sections": missing,
                "message": f"Missing required sections: {', '.join(missing)}. Add them before saving.",
            }
        return {
            "valid": True,
            "missing_sections": [],
            "message": "All required sections present (Statement, Rationale, Implications).",
        }

    # ── Artifact tools (3-4) ──

    @agent.tool
    def save_principle(
        ctx_: RunContext[SessionContext],
        filename: str,
        content: str,
        summary: str,
    ) -> dict:
        """Save a generated principle as an artifact for download and future refinement.

        Call this after generating and validating the principle.

        Args:
            filename: Descriptive filename (e.g., "data-sovereignty-principle.md")
            content: The full principle in markdown format
            summary: One-line summary (e.g., "Enterprise principle on data sovereignty")

        Returns:
            Dict with artifact_id, filename, summary — or error
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": f"Decision: save_principle Reasoning: Saving principle '{filename}'",
            "elapsed_ms": elapsed,
        })
        return _save_artifact_fn(
            filename=filename,
            content=content,
            content_type="principle/markdown",
            summary=summary,
            conversation_id=ctx_.deps.conversation_id,
            event_queue=ctx_.deps.event_queue,
        )

    @agent.tool
    def get_principle(
        ctx_: RunContext[SessionContext],
    ) -> dict:
        """Load the most recently saved principle for refinement.

        Use this when the user asks to refine, update, or improve a previously
        generated principle (e.g. "make the rationale more concise").

        Returns:
            Dict with filename, content, content_type, summary — or error
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: get_principle Reasoning: Loading previous principle for refinement",
            "elapsed_ms": elapsed,
        })
        return _get_artifact_fn(
            conversation_id=ctx_.deps.conversation_id,
            content_type="principle/markdown",
        )

    # ── Capability gap probe (5) ──

    @agent.tool
    def request_data(
        ctx_: RunContext[SessionContext],
        capability: str,
        reason: str,
    ) -> dict:
        """Signal that required data or capability is missing from the knowledge base.

        Use when the KB search returns insufficient context to generate a
        well-grounded principle and the user should be informed of the gap.

        Args:
            capability: What data or context is missing
            reason: Why it's needed for principle generation

        Returns:
            Acknowledgement dict
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        return _request_data(
            description=f"{capability}: {reason}",
            conversation_id=ctx_.deps.conversation_id,
            agent="principle",
        )

    return agent


class PrincipleAgent:
    """Pydantic AI agent for architecture principle lifecycle.

    Tools:
      1. search_related_principles — hybrid search for generation context
      2. search_principles — fetch specific principles for assessment
      3. list_principles — enumerate all principles for broad assessment
      4. validate_principle_structure — check Statement/Rationale/Implications present
      5. save_principle — persist generated principle as artifact
      6. get_principle — load previous principle for refinement
      7. request_data — capability gap probe
    """

    def __init__(self, client: WeaviateClient):
        self.toolkit = RAGToolkit(client)
        self._agent = _build_principle_agent(self.toolkit)

    async def query(
        self,
        question: str,
        event_queue: Queue | None = None,
        skill_tags: list[str] | None = None,
        doc_refs: list[str] | None = None,
        conversation_id: str | None = None,
        artifact_context: str | None = None,
    ) -> tuple[str, list[dict]]:
        """Process a principle generation, refinement, or quality assessment query.

        Returns (response_text, retrieved_objects) tuple.
        """
        skill_content = _get_skill_content(question, skill_tags=skill_tags or ["generate-principle"])

        ctx = SessionContext(
            conversation_id=conversation_id,
            event_queue=event_queue,
            doc_refs=doc_refs or [],
            skill_tags=skill_tags or [],
            artifact_context=artifact_context,
            agent_label=AGENT_LABELS["principle_agent"],
            system_prompt=self._build_system_prompt(skill_content, artifact_context),
            _query_start=time.perf_counter(),
            max_tool_calls=_get_max_tool_calls("principle_agent", 8),
        )

        logger.info(f"PrincipleAgent processing: {question}")

        try:
            result = await self._agent.run(question, deps=ctx)
            response = result.output
        except Exception as e:
            logger.exception("PrincipleAgent error")
            response = f"I encountered an error generating the principle: {e}"

        elapsed = elapsed_ms(ctx._query_start)
        logger.info(
            "PrincipleAgent complete: %d ms, %d tool calls",
            elapsed, ctx.tool_call_count,
        )

        return response, ctx.retrieved_objects

    @staticmethod
    def _build_system_prompt(skill_content: str, artifact_context: str | None) -> str:
        """Build the system prompt from skill content + optional artifact."""
        parts = [
            "You are AInstein, the Energy System Architecture AI Assistant at Alliander.",
            "",
            "Your role is to help architects generate, refine, and assess the quality of "
            "architecture and enterprise principles following TOGAF-aligned criteria.",
        ]
        if skill_content:
            parts.extend(["", skill_content])
        parts.extend([
            "",
            "Guidelines:",
            "- For GENERATION: use search_related_principles first, then validate and save",
            "- For ASSESSMENT: use search_principles or list_principles to fetch the "
            "principles being assessed, then apply quality criteria from your instructions",
            "- Always validate structure with validate_principle_structure before saving",
            "- Use get_principle when refining a previously generated principle",
            "- If the KB lacks sufficient context, use request_data to flag the gap",
        ])
        if artifact_context:
            parts.extend(["", artifact_context])
        return "\n".join(parts)
