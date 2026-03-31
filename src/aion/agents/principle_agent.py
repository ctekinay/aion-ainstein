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
from pydantic_ai.messages import ModelMessage
from pydantic_ai.tools import RunContext
from weaviate import WeaviateClient

from aion.agents import AGENT_LABELS, SessionContext, _get_max_tool_calls, process_history
from aion.config import settings
from aion.text_utils import elapsed_ms
from aion.tools.artifacts import (
    get_artifact as _get_artifact_fn,
)
from aion.tools.artifacts import (
    save_artifact as _save_artifact_fn,
)
from aion.skills.loader import get_thresholds_value
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
        history_processors=[process_history],
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
    def list_principles(
        ctx_: RunContext[SessionContext],
        query: str = "",
        limit: int = 0,
    ) -> list[dict]:
        """List ALL architecture and governance principles (PCPs) in the system.

        Use this when assessing a broad set of principles, or when the user asks
        to evaluate, compare, or classify multiple principles without specifying
        exact IDs. Always returns ALL principles regardless of parameters.

        Args:
            query: Ignored — exists for compatibility with weaker models
            limit: Ignored — always returns all principles

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
        message_history: list[ModelMessage] | None = None,
        running_summary: str | None = None,
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
            agent_label=AGENT_LABELS["principle_agent"],
            system_prompt=self._build_system_prompt(skill_content),
            _query_start=time.perf_counter(),
            max_tool_calls=_get_max_tool_calls("principle_agent", 8),
            running_summary=running_summary,
        )

        logger.info(f"PrincipleAgent processing: {question}")
        logger.info("principle_agent_model model=%s", self._agent.model.model_name)

        # Batched compliance evaluation — splits principles into groups for
        # thorough per-principle analysis. "force" providers always batch
        # (weak models need it); "optional" providers only batch when
        # compliance_batch_enabled is true (toggle for testing/thoroughness).
        _agent_cfg = get_thresholds_value("get_agent_config", {})
        _provider = settings.effective_rag_provider
        _force = _agent_cfg.get("compliance_batch_force_providers", ["ollama"])
        _optional = _agent_cfg.get("compliance_batch_optional_providers", [])
        _opt_enabled = _agent_cfg.get("compliance_batch_enabled", False)
        if (
            artifact_context
            and (
                _provider in _force
                or (_provider in _optional and _opt_enabled)
            )
        ):
            return await self._query_batched(
                question, artifact_context, ctx, _agent_cfg,
            )

        try:
            # Prepend document content to user message for cross-reference
            user_message = question
            if artifact_context:
                user_message = f"{artifact_context}\n\n## QUESTION:\n{question}"
            result = await self._agent.run(user_message, deps=ctx, message_history=message_history or [])
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

    async def _query_batched(
        self,
        question: str,
        artifact_context: str,
        ctx: SessionContext,
        agent_cfg: dict,
    ) -> tuple[str, list[dict]]:
        """Evaluate document against principles in batches for weak models.

        Splits all principles into groups of ~batch_size, runs one LLM call
        per batch with the document + that subset of principles, then
        synthesizes all partial results into a unified compliance table.
        """
        batch_size = agent_cfg.get("compliance_batch_size", 10)

        # Fetch all principles directly (Python call, no LLM tool call)
        all_principles = self.toolkit.list_principles()
        total = len(all_principles)
        ctx.retrieved_objects.extend(all_principles)

        batches = [all_principles[i:i + batch_size]
                    for i in range(0, total, batch_size)]
        logger.info("compliance_batch_start total=%d batches=%d batch_size=%d",
                     total, len(batches), batch_size)
        ctx.emit_event({
            "type": "status",
            "content": f"Evaluating {total} principles in {len(batches)} batches...",
        })

        partial_results = []
        for batch_idx, batch in enumerate(batches):
            pcp_ids = [p.get("principle_number", "?") for p in batch]
            ctx.emit_event({
                "type": "status",
                "content": (
                    f"Batch {batch_idx + 1}/{len(batches)}: "
                    f"{pcp_ids[0]}–{pcp_ids[-1]}..."
                ),
            })

            principles_text = "\n\n".join(
                f"### {p.get('principle_number', '?')} — "
                f"{p.get('title', 'Untitled')}\n{p.get('content', '')}"
                for p in batch
            )
            batch_prompt = (
                f"{artifact_context}\n\n"
                f"## PRINCIPLES TO EVALUATE "
                f"(batch {batch_idx + 1}/{len(batches)}, "
                f"{len(batch)} of {total} total):\n\n"
                f"{principles_text}\n\n"
                f"## TASK:\n"
                f"Evaluate the document against ONLY the {len(batch)} "
                f"principles above. For each produce one row in a markdown table "
                f"with columns: Principle ID | Name "
                f"| Verdict (COMPLIANT/VIOLATED/PARTIAL/N/A) | Evidence "
                f"| Reasoning | Recommended Action.\n"
                f"Output ONLY the markdown table rows. No introduction, no preamble, "
                f"no summary, no conclusion, no 'Overall notes'. Start directly with "
                f"the table header and end with the last row.\n"
                f"Do NOT call any tools.\n"
                f"Original question: {question}"
            )

            # Fresh context per batch — prevents tool_call_count accumulation
            batch_ctx = SessionContext(
                conversation_id=ctx.conversation_id,
                event_queue=ctx.event_queue,
                agent_label=ctx.agent_label,
                system_prompt=ctx.system_prompt,
                _query_start=ctx._query_start,
                max_tool_calls=0,
            )

            try:
                result = await self._agent.run(
                    batch_prompt, deps=batch_ctx, message_history=[],
                )
                partial_results.append(result.output)
            except Exception as e:
                logger.error("compliance_batch_error batch=%d error=%s",
                             batch_idx + 1, e)
                partial_results.append(
                    f"[Batch {batch_idx + 1} failed: {e}]"
                )

        # Programmatic concatenation — skip the synthesis LLM call.
        # Weak models can't merge tables reliably, and the extra call
        # costs ~150s for no value. Just join the batch tables and add
        # a count summary.
        ctx.emit_event({
            "type": "status",
            "content": "Combining batch results...",
        })

        # Build unified table: single header + all batch rows
        table_header = (
            "| Principle ID | Name | Verdict | Evidence | Reasoning "
            "| Recommended Action |\n"
            "|---|---|---|---|---|---|"
        )

        # Extract table rows from each batch result, stripping any
        # headers/preamble the model may have included despite instructions
        all_rows = []
        for batch_result in partial_results:
            for line in batch_result.strip().splitlines():
                stripped = line.strip()
                # Keep only table data rows (start with |, not separators)
                if stripped.startswith("|") and not stripped.startswith("|---"):
                    # Skip duplicate header rows
                    if "Principle ID" in stripped and "Verdict" in stripped:
                        continue
                    all_rows.append(stripped)

        # Count verdicts
        verdicts = {"COMPLIANT": 0, "VIOLATED": 0, "PARTIAL": 0, "N/A": 0}
        for row in all_rows:
            for v in verdicts:
                if v in row:
                    verdicts[v] += 1
                    break

        response = (
            f"## Compliance Evaluation: {total} Principles\n\n"
            f"{table_header}\n"
            + "\n".join(all_rows)
            + f"\n\n### Summary\n\n"
            f"- **{verdicts['COMPLIANT']}** Compliant\n"
            f"- **{verdicts['PARTIAL']}** Partial\n"
            f"- **{verdicts['VIOLATED']}** Violated\n"
            f"- **{verdicts['N/A']}** Not Applicable\n"
            f"- **{total}** Total principles evaluated"
        )

        elapsed = elapsed_ms(ctx._query_start)
        logger.info(
            "compliance_batch_complete total_ms=%d batches=%d principles=%d",
            elapsed, len(batches), total,
        )
        return response, ctx.retrieved_objects

    @staticmethod
    def _build_system_prompt(skill_content: str) -> str:
        """Build the system prompt from skill content."""
        parts = [
            "You are AInstein, the Energy System Architecture AI Assistant at Alliander.",
            "",
            "Your role is to help architects generate, refine, and assess the quality of "
            "architecture and enterprise principles, AND to evaluate documents against "
            "the principles in the knowledge base for compliance.",
        ]
        if skill_content:
            parts.extend(["", skill_content])
        parts.extend([
            "",
            "Guidelines:",
            "- For GENERATION: use search_related_principles first, then validate and save",
            "- For ASSESSMENT: use search_principles or list_principles to fetch the "
            "principles being assessed, then apply quality criteria from your instructions",
            "- For COMPLIANCE EVALUATION (when a document is provided in the user message): "
            "use list_principles to fetch ALL principles, then systematically evaluate the "
            "document against EVERY principle. For each principle, determine: COMPLIANT "
            "(document explicitly satisfies the principle), VIOLATED (document contradicts "
            "or fails to address a requirement of the principle), PARTIAL (intent is present "
            "but evidence is incomplete), or N/A (principle is outside the document's scope). "
            "Produce a COMPLETE traceable table covering ALL principles — not a partial list. "
            "Include: Principle ID, Principle Name, Verdict, Evidence (quote from the document), "
            "Reasoning, and Recommended Action. Be assertive and definitive in your assessments. "
            "Do not ask for page numbers or additional uploads — work with the text provided.",
            "",
            "  TRANSPARENCY RULE FOR COMPLIANCE EVALUATION: "
            "If the number of principles is too large to evaluate thoroughly in a single "
            "response, you MUST follow this protocol:",
            "  1. State clearly at the TOP of your response how many total principles exist "
            "and which subset you are covering (e.g., 'There are 41 principles total. "
            "This response covers PCP.10 through PCP.20.').",
            "  2. Evaluate that subset thoroughly — do NOT produce shallow one-line verdicts "
            "just to fit more principles in.",
            "  3. At the END of your response, list every principle ID you have NOT yet "
            "covered and explicitly offer to continue (e.g., 'The following 30 principles "
            "remain: PCP.21–PCP.50. Shall I continue with the next batch?').",
            "  NEVER silently omit principles. The user must always know the complete scope: "
            "how many principles exist, how many you evaluated, and how many remain. "
            "Partial coverage without disclosure destroys user trust.",
            "",
            "- Always validate structure with validate_principle_structure before saving",
            "- Use get_principle when refining a previously generated principle",
            "- If the KB lacks sufficient context, use request_data to flag the gap",
        ])
        # artifact_context is NOT appended here — document content goes in
        # the user message, not the system prompt. Models process user message
        # content reliably; long system prompts get truncated or deprioritized.
        return "\n".join(parts)
