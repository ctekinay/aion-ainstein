"""VocabularyAgent — Pydantic AI agent for SKOSMOS vocabulary lookup.

Handles term definitions, concept details, and vocabulary listing via
the SKOSMOS REST API. Includes a scoped Weaviate search tool for Tier 2
fallback when SKOSMOS has no results.

Stateless per query — the Persona handles multi-turn context via query
rewriting before this agent is called.
"""

import logging
import time
from queue import Queue

from pydantic_ai import Agent
from pydantic_ai.tools import RunContext
from weaviate import WeaviateClient

from aion.agents import AGENT_LABELS, SessionContext
from aion.config import settings
from aion.text_utils import elapsed_ms
from aion.tools.capability_gaps import request_data as _request_data
from aion.tools.rag_search import (
    RAGToolkit,
    _get_skill_content,
)
from aion.tools.skosmos import (
    skosmos_concept_details as _skosmos_details,
)
from aion.tools.skosmos import (
    skosmos_list_vocabularies as _skosmos_vocabs,
)
from aion.tools.skosmos import (
    skosmos_search as _skosmos_search,
)

logger = logging.getLogger(__name__)


def _build_vocabulary_agent(toolkit: RAGToolkit | None) -> Agent[SessionContext, str]:
    """Build the Pydantic AI agent with vocabulary tools (once at init)."""
    agent: Agent[SessionContext, str] = Agent(
        model=settings.build_pydantic_ai_model("tree"),
        deps_type=SessionContext,
        retries=1,
    )

    @agent.system_prompt
    def dynamic_system_prompt(ctx: RunContext[SessionContext]) -> str:
        return ctx.deps.system_prompt

    # ── SKOSMOS tools (1-3) ──
    # NOTE: Decision events use "Decision: X Reasoning: Y" format which is
    # rewritten to human-readable text by SessionContext.emit_event().
    # See agents/__init__.py:_rewrite_decision for the rewrite logic.

    @agent.tool
    def skosmos_search(
        ctx_: RunContext[SessionContext],
        query: str,
        lang: str = "en",
        vocab: str | None = None,
        max_results: int = 10,
    ) -> dict:
        """Search SKOSMOS for vocabulary terms by label matching.

        This is step 1 of a two-step lookup. After finding a match, you MUST
        call skosmos_concept_details with the result's uri and vocab to
        retrieve the actual definition.

        IMPORTANT: This tool finds terms but does NOT return definitions.
        Always follow up with skosmos_concept_details to get the definition.

        Args:
            query: The term or phrase to search for
            lang: Language code (default "en")
            vocab: Optional vocabulary ID to limit search to
            max_results: Maximum results to return (default 10)

        Returns:
            Dict with results list and total_results
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": f"Decision: skosmos_search Reasoning: Searching SKOSMOS for '{query}'",
            "elapsed_ms": elapsed,
        })
        result = _skosmos_search(query, lang=lang, vocab=vocab, max_results=max_results)

        # Accumulate per-term disambiguation state
        vocabs_hit = {r["vocab"] for r in result.get("results", []) if r.get("vocab")}
        # PydanticAI may pass None as string "None" — guard against that
        explicit_vocab = vocab and str(vocab).strip().lower() != "none"
        if len(vocabs_hit) > 1 and not explicit_vocab:
            ctx_.deps.pending_disambiguations[query] = sorted(vocabs_hit)
            result["multi_vocab"] = True
            result["vocabs_found"] = sorted(vocabs_hit)
        elif query in ctx_.deps.pending_disambiguations and explicit_vocab:
            # User picked a vocab, agent re-searched with explicit vocab — resolved
            del ctx_.deps.pending_disambiguations[query]

        return result

    @agent.tool
    def skosmos_concept_details(
        ctx_: RunContext[SessionContext],
        uri: str,
        vocab: str,
        lang: str = "en",
    ) -> dict:
        """Get the full definition and details for a SKOS concept by URI.

        This is step 2 of vocabulary lookup. ALWAYS call this after
        skosmos_search returns results.

        IMPORTANT: Both uri and vocab are REQUIRED. Get them from
        skosmos_search results.

        Args:
            uri: The concept URI (from skosmos_search results)
            vocab: The vocabulary ID (from skosmos_search results)
            lang: Language code (default "en")

        Returns:
            Dict with uri, prefLabel, altLabels, definition, broader,
            narrower, related, scopeNote, notation
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}

        # Gate: block drill-down until all ambiguous terms are resolved
        if ctx_.deps.pending_disambiguations:
            return {
                "disambiguation_required": True,
                "pending_terms": ctx_.deps.pending_disambiguations,
                "message": "These terms have multiple definitions. "
                           "Present all options to the user before proceeding.",
            }

        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": f"Decision: skosmos_concept_details Reasoning: Getting concept details for {uri}",
            "elapsed_ms": elapsed,
        })
        return _skosmos_details(uri, vocab=vocab, lang=lang)

    @agent.tool
    def skosmos_list_vocabularies(
        ctx_: RunContext[SessionContext], lang: str = "en"
    ) -> dict:
        """List all vocabularies available in SKOSMOS.

        Returns vocabulary IDs, titles, descriptions, and concept counts.

        Args:
            lang: Language code (default "en")

        Returns:
            Dict with vocabularies list
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: skosmos_list_vocabularies Reasoning: Listing available vocabularies",
            "elapsed_ms": elapsed,
        })
        return _skosmos_vocabs(lang=lang)

    # ── Tier 2 fallback tool (4) ──

    if toolkit:
        @agent.tool
        def search_knowledge_base(
            ctx_: RunContext[SessionContext], query: str
        ) -> list[dict]:
            """Search the architecture knowledge base for term definitions.

            Tier 2 fallback — use ONLY after SKOSMOS returns no results.
            Searches ADRs, Principles, and Policies for contextual definitions.
            Results from this tool are NOT authoritative vocabulary definitions.

            Args:
                query: The term or phrase to search for

            Returns:
                List of matching KB documents with metadata and content
            """
            if ctx_.deps.check_iteration_limit():
                return [{"error": "Tool call limit reached"}]
            elapsed = elapsed_ms(ctx_.deps._query_start)
            ctx_.deps.emit_event({
                "type": "decision",
                "content": f"Decision: search_knowledge_base Reasoning: SKOSMOS had no results, searching KB for '{query}'",
                "elapsed_ms": elapsed,
            })
            results = []
            for search_fn in (
                toolkit.search_architecture_decisions,
                toolkit.search_principles,
                toolkit.search_policies,
            ):
                try:
                    results.extend(search_fn(query, limit=3))
                except Exception:
                    logger.warning("Tier 2 KB search failed for %s", search_fn.__name__, exc_info=True)
            ctx_.deps.retrieved_objects.extend(results)
            ctx_.deps.emit_event({
                "type": "status",
                "content": f"Found {len(results)} KB results (Tier 2 fallback)",
                "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
            })
            return results

    # ── Capability gap probe ──

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
            agent="vocabulary",
        )

    return agent


class VocabularyAgent:
    """Pydantic AI agent for vocabulary lookup via SKOSMOS.

    Tools:
      1. skosmos_search — find terms by label matching (Tier 1)
      2. skosmos_concept_details — get full definition by URI (Tier 1)
      3. skosmos_list_vocabularies — list available vocabularies
      4. search_knowledge_base — scoped Weaviate search (Tier 2 fallback)
      5. request_data — capability gap probe
    """

    def __init__(self, client: WeaviateClient | None = None):
        self.toolkit = RAGToolkit(client) if client else None
        self._agent = _build_vocabulary_agent(self.toolkit)

    async def query(
        self,
        question: str,
        event_queue: Queue | None = None,
        skill_tags: list[str] | None = None,
        doc_refs: list[str] | None = None,
        conversation_id: str | None = None,
    ) -> tuple[str, list[dict]]:
        """Process a vocabulary query using the Pydantic AI agent.

        Returns (response_text, retrieved_objects) tuple.
        """
        skill_content = _get_skill_content(question, skill_tags=skill_tags or ["vocabulary"])

        ctx = SessionContext(
            conversation_id=conversation_id,
            event_queue=event_queue,
            doc_refs=doc_refs or [],
            skill_tags=skill_tags or [],
            agent_label=AGENT_LABELS["vocabulary_agent"],
            system_prompt=self._build_system_prompt(skill_content),
            _query_start=time.perf_counter(),
            max_tool_calls=8,
        )

        logger.info(f"VocabularyAgent processing: {question}")

        # Run the agent
        try:
            result = await self._agent.run(question, deps=ctx)
            response = result.output
        except Exception as e:
            logger.exception("VocabularyAgent error")
            response = f"I encountered an error while looking up vocabulary terms: {e}"

        elapsed = elapsed_ms(ctx._query_start)
        logger.info(
            "VocabularyAgent complete: %d ms, %d tool calls",
            elapsed, ctx.tool_call_count,
        )

        return response, ctx.retrieved_objects

    @staticmethod
    def _build_system_prompt(skill_content: str) -> str:
        """Build the system prompt from skill content."""
        parts = [
            "You are AInstein, the Energy System Architecture AI Assistant at Alliander.",
            "",
            "Your role is to help architects, engineers, and stakeholders look up "
            "vocabulary terms, definitions, and standard terminology.",
        ]
        if skill_content:
            parts.extend(["", skill_content])
        parts.extend([
            "",
            "Guidelines:",
            "- Follow the tiered fallback chain strictly: SKOSMOS first, then KB, then your own knowledge",
            "- Present SKOSMOS definitions verbatim — do not rephrase",
            "- When using KB results, clearly label them as contextual, not authoritative",
            "- When using your own knowledge, clearly flag it as tentative and ask for confirmation",
            "- Include vocabulary source and concept URI in citations",
        ])
        return "\n".join(parts)
