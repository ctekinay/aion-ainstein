"""RAGAgent — Pydantic AI agent for knowledge base queries.

Single-query stateless agent. The Persona handles multi-turn context
via query rewriting before this agent is called. The Agent instance and
tools are built once in __init__; each query() call reuses them with a
fresh SessionContext.

Fallback path: when the agent fails, _direct_query() performs keyword-based
retrieval + direct LLM call as a degraded-mode fallback.
"""

import json
import logging
import time

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.tools import RunContext
from weaviate import WeaviateClient
from weaviate.classes.query import Filter, MetadataQuery

from aion.agents import AGENT_LABELS, SessionContext, _get_max_tool_calls, process_history
from aion.config import is_reasoning_model, settings
from aion.skills.loader import get_thresholds_value
from aion.text_utils import elapsed_ms, strip_think_tags
from aion.tools.capability_gaps import request_data as _request_data
from aion.tools.rag_search import (
    RAGToolkit,
    _get_skill_content,

    _get_truncation,
    _is_permanent_llm_error,
    get_abstention_response,
    is_general_knowledge_eligible,
    should_abstain,
)

logger = logging.getLogger(__name__)

def _build_rag_agent(toolkit: RAGToolkit) -> Agent[SessionContext, str]:
    """Build the Pydantic AI agent with 9 tools: 8 RAG + request_data (once at init)."""
    agent: Agent[SessionContext, str] = Agent(
        model=settings.build_pydantic_ai_model("tree"),
        deps_type=SessionContext,
        retries=1,
        history_processors=[process_history],
    )

    @agent.system_prompt
    def dynamic_system_prompt(ctx: RunContext[SessionContext]) -> str:
        return ctx.deps.system_prompt

    # ── RAG tools (1-8) ──
    # NOTE: Decision events use "Decision: X Reasoning: Y" format which is
    # rewritten to human-readable text by SessionContext.emit_event().
    # See agents/__init__.py:_rewrite_decision for the rewrite logic.

    @agent.tool
    def search_architecture_decisions(
        ctx_: RunContext[SessionContext], query: str, limit: int = 10
    ) -> list[dict]:
        """Search Architectural Decision Records (ADRs) for design decisions.

        ADRs are formal records of significant architecture decisions. Each has
        sections: Context (problem statement), Decision (outcome), Consequences.
        Identifier format: ADR.NN (e.g., ADR.12 = "Use CIM as default domain language").

        ADR number ranges:
        - ADR.0-2: Meta decisions (markdown format, writing conventions, DACI)
        - ADR.10-12: Standardisation (IEC standards, CIM adoption)
        - ADR.20-31: Energy system decisions (demand response, security, OAuth, TLS)

        Decision Approval Records (DARs): Files like 0029D contain the approval
        record for ADR.29. Use these for "who approved" or "when was it approved" queries.

        ID aliases — all of these refer to ADR.29:
        "ADR 29", "adr-29", "ADR.0029", "ADR-0029", "decision 29"

        IMPORTANT — Numbering overlap with Principles:
        Numbers 10-12 and 20-31 exist in BOTH ADRs and Principles. For example:
        - ADR.22 = "Use priority-based scheduling" (architecture decision)
        - PCP.22 = "Omnichannel Multibrand" (business principle)
        If the user says "document 22" or just a number without specifying ADR or PCP,
        search BOTH this collection AND search_principles to present both results.

        Query intent patterns:
        - "What does ADR.12 decide?" → lookup the ADR itself
        - "Who approved ADR.29?" → search for "0029D" to find the DAR
        - "What decisions about security?" → topic search
        - "List all ADRs" → use list_adrs tool instead

        Args:
            query: Search query — use the 4-digit number (e.g., "0029") for ID lookups
            limit: Maximum number of results to return

        Returns:
            List of matching ADRs with all available metadata and truncated content
        """
        # Cache check first — cached no-ops must not burn a tool call slot.
        cache_key = f"adr:{','.join(sorted(ctx_.deps.doc_refs))}:{query}:{limit}"
        cached = ctx_.deps._search_cache.get(cache_key)
        if cached is not None:
            logger.info("search_architecture_decisions cache hit key=%s", cache_key[:80])
            return cached

        if ctx_.deps.check_iteration_limit():
            return [{"error": "Tool call limit reached"}]

        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": f"Decision: search_architecture_decisions Reasoning: Searching ADRs for '{query}'",
            "elapsed_ms": elapsed,
        })
        result = toolkit.search_architecture_decisions(
            query, limit, doc_refs=ctx_.deps.doc_refs,
        )
        ctx_.deps._search_cache[cache_key] = result
        ctx_.deps.retrieved_objects.extend(result)
        ctx_.deps.emit_event({
            "type": "status",
            "content": f"Found {len(result)} ADR results",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        return result

    @agent.tool
    def search_principles(
        ctx_: RunContext[SessionContext], query: str, limit: int = 10
    ) -> list[dict]:
        """Search architecture and governance principles (PCPs).

        Principles are guiding statements with sections: Statement, Rationale,
        Implications. Identifier format: PCP.NN (e.g., PCP.10 = "Eventual
        Consistency by Design").

        PCP number ranges:
        - PCP.10-20: ESA Architecture Principles (data design, consistency, sovereignty)
        - PCP.21-30: Business Architecture Principles (omnichannel, customer, value streams)
        - PCP.31-40: Data Office Governance Principles (data quality, accessibility, AI)

        Decision Approval Records: Files like 0022D contain the approval record
        for PCP.22. Use these for "who approved" queries.

        ID aliases — all of these refer to PCP.22:
        "PCP 22", "pcp-22", "PCP.0022", "principle 22"

        IMPORTANT — Numbering overlap with ADRs:
        Numbers 10-12 and 20-31 exist in BOTH Principles and ADRs.
        If the user says "document 22" or just a number without specifying ADR or PCP,
        search BOTH this collection AND search_architecture_decisions to present both.

        Note: PCP.21-30 are Dutch-language Business Architecture Principles.
        PCP.31-40 are Data Office principles (mix of Dutch and English).

        Query intent patterns:
        - "What are the data governance principles?" → PCP.31-40
        - "What does PCP.10 say?" → lookup PCP.10
        - "List all principles" → use list_principles tool instead

        Args:
            query: Search query — use the 4-digit number (e.g., "0022") for ID lookups
            limit: Maximum number of results to return

        Returns:
            List of matching principles with all available metadata and truncated content
        """
        # Cache check first — cached no-ops must not burn a tool call slot.
        cache_key = f"pcp:{','.join(sorted(ctx_.deps.doc_refs))}:{query}:{limit}"
        cached = ctx_.deps._search_cache.get(cache_key)
        if cached is not None:
            logger.info("search_principles cache hit key=%s", cache_key[:80])
            return cached

        if ctx_.deps.check_iteration_limit():
            return [{"error": "Tool call limit reached"}]

        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": f"Decision: search_principles Reasoning: Searching principles for '{query}'",
            "elapsed_ms": elapsed,
        })
        result = toolkit.search_principles(
            query, limit, doc_refs=ctx_.deps.doc_refs,
        )
        ctx_.deps._search_cache[cache_key] = result
        ctx_.deps.retrieved_objects.extend(result)
        ctx_.deps.emit_event({
            "type": "status",
            "content": f"Found {len(result)} principle results",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        return result

    @agent.tool
    def search_policies(
        ctx_: RunContext[SessionContext], query: str, limit: int = 5
    ) -> list[dict]:
        """Search data governance and policy documents (DOCX/PDF).

        Policy documents are formal governance DOCX/PDF files from the Data Office
        (DO) and Corporate Governance (CG), primarily in Dutch.

        Use this tool ONLY for searching specific policy content, NOT for listing.
        To enumerate or count policies, use list_policies instead.

        Do NOT use this tool for ADRs (use search_architecture_decisions) or
        Principles (use search_principles).

        Args:
            query: Search query for policy documents
            limit: Maximum number of results to return

        Returns:
            List of matching policy documents with all available metadata
        """
        if ctx_.deps.check_iteration_limit():
            return [{"error": "Tool call limit reached"}]
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": f"Decision: search_policies Reasoning: Searching policies for '{query}'",
            "elapsed_ms": elapsed,
        })
        result = toolkit.search_policies(query, limit)
        ctx_.deps.retrieved_objects.extend(result)
        ctx_.deps.emit_event({
            "type": "status",
            "content": f"Found {len(result)} policy results",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        return result

    @agent.tool
    def list_adrs(
        ctx_: RunContext[SessionContext],
        owner_filter: str = "",
        status_filter: str = "",
    ) -> list[dict]:
        """List Architectural Decision Records (ADRs), optionally filtered.

        Use this tool (not search_architecture_decisions) when the user wants
        to enumerate, count, or filter ADRs.

        Args:
            owner_filter: Filter by owner team abbreviation (e.g., "ESA", "BA"). Empty = all.
            status_filter: Filter by status (e.g., "accepted", "proposed"). Empty = all.

        Returns:
            Filtered list with _summary at position 0 containing total_count
            (unfiltered) and filtered_count.
        """
        if ctx_.deps.check_iteration_limit():
            return [{"error": "Tool call limit reached"}]
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: list_adrs Reasoning: Listing all ADRs",
            "elapsed_ms": elapsed,
        })
        result = toolkit.list_adrs()
        # Summary from FULL unfiltered list
        summary = {"_summary": True, "total_count": len(result)}
        # Apply filters
        filtered = result
        if owner_filter:
            filtered = [r for r in filtered if r.get("owner_team_abbr", "").upper() == owner_filter.upper()]
        if status_filter:
            filtered = [r for r in filtered if r.get("status", "").lower() == status_filter.lower()]
        summary["filtered_count"] = len(filtered)
        # Track only what the LLM actually sees (filtered)
        ctx_.deps.retrieved_objects.extend(filtered)
        ctx_.deps.emit_event({
            "type": "status",
            "content": f"Found {len(filtered)} ADRs" + (f" (of {summary['total_count']} total)" if owner_filter or status_filter else ""),
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        filtered.insert(0, dict(summary))
        return filtered

    @agent.tool
    def list_principles(
        ctx_: RunContext[SessionContext],
        owner_filter: str = "",
        status_filter: str = "",
    ) -> list[dict]:
        """List architecture and governance principles (PCPs), optionally filtered.

        ALWAYS use this tool (never search_principles) when the user wants to:
        - see, enumerate, or count principles
        - filter or group principles by owner, team, status, or group
          (e.g. "which are ESA owned?", "show BA principles", "list accepted PCPs")

        Args:
            owner_filter: Filter by owner team abbreviation (e.g., "ESA", "BA", "DO", "NB-EA", "EA"). Empty = all.
            status_filter: Filter by status (e.g., "proposed", "accepted"). Empty = all.

        Returns:
            Filtered list with _summary at position 0 containing total_count,
            by_owner_team breakdown, and filtered_count.
        """
        if ctx_.deps.check_iteration_limit():
            return [{"error": "Tool call limit reached"}]
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: list_principles Reasoning: Listing all principles",
            "elapsed_ms": elapsed,
        })
        result = toolkit.list_principles()
        # Summary from FULL unfiltered list with owner breakdown
        by_owner = {}
        for r in result:
            owner = r.get("owner_team_abbr", "unknown")
            by_owner[owner] = by_owner.get(owner, 0) + 1
        summary = {"_summary": True, "total_count": len(result), "by_owner_team": by_owner}
        # Apply filters
        filtered = result
        if owner_filter:
            filtered = [r for r in filtered if r.get("owner_team_abbr", "").upper() == owner_filter.upper()]
        if status_filter:
            filtered = [r for r in filtered if r.get("status", "").lower() == status_filter.lower()]
        summary["filtered_count"] = len(filtered)
        ctx_.deps.retrieved_objects.extend(filtered)
        ctx_.deps.emit_event({
            "type": "status",
            "content": f"Found {len(filtered)} principles" + (f" (of {summary['total_count']} total)" if owner_filter or status_filter else ""),
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        filtered.insert(0, dict(summary))
        return filtered

    @agent.tool
    def list_policies(
        ctx_: RunContext[SessionContext],
        owner_filter: str = "",
    ) -> list[dict]:
        """List policy documents, optionally filtered by owner.

        ALWAYS use this tool (never search_policies) when the user wants to
        see, enumerate, or count policy documents.

        Args:
            owner_filter: Filter by owner team (e.g., "Data Office"). Empty = all.

        Returns:
            Filtered list with _summary at position 0.
        """
        if ctx_.deps.check_iteration_limit():
            return [{"error": "Tool call limit reached"}]
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: list_policies Reasoning: Listing all policies",
            "elapsed_ms": elapsed,
        })
        result = toolkit.list_policies()
        summary = {"_summary": True, "total_count": len(result)}
        filtered = result
        if owner_filter:
            filtered = [r for r in filtered if (r.get("owner_team", "") or "").upper() == owner_filter.upper()]
        summary["filtered_count"] = len(filtered)
        ctx_.deps.retrieved_objects.extend(filtered)
        ctx_.deps.emit_event({
            "type": "status",
            "content": f"Found {len(filtered)} policies" + (f" (of {summary['total_count']} total)" if owner_filter else ""),
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        filtered.insert(0, dict(summary))
        return filtered

    @agent.tool
    def list_dars(
        ctx_: RunContext[SessionContext],
        source_filter: str = "",
        owner_filter: str = "",
        status_filter: str = "",
    ) -> list[dict]:
        """List Decision Approval Records (DARs), optionally filtered.

        ALWAYS use this tool when the user asks about approval records,
        who approved a decision/principle, or wants to see DARs.

        Args:
            source_filter: Filter by source collection ("ADR" or "PCP"). Empty = all.
            owner_filter: Filter by owner team abbreviation (e.g., "ESA"). Empty = all.
            status_filter: Filter by decision status. Empty = all.

        Returns:
            Filtered list with _summary at position 0 containing total_count,
            adr_dar_count, pcp_dar_count, and filtered_count.
        """
        if ctx_.deps.check_iteration_limit():
            return [{"error": "Tool call limit reached"}]
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: list_dars Reasoning: Listing all approval records",
            "elapsed_ms": elapsed,
        })
        result = toolkit.list_dars()
        adr_count = sum(1 for r in result if r.get("dar_source") == "ADR")
        pcp_count = sum(1 for r in result if r.get("dar_source") == "PCP")
        summary = {
            "_summary": True,
            "total_count": len(result),
            "adr_dar_count": adr_count,
            "pcp_dar_count": pcp_count,
        }
        filtered = result
        if source_filter:
            filtered = [r for r in filtered if r.get("dar_source", "").upper() == source_filter.upper()]
        if owner_filter:
            filtered = [r for r in filtered if r.get("owner_team_abbr", "").upper() == owner_filter.upper()]
        if status_filter:
            filtered = [r for r in filtered if (r.get("status", "") or "").lower() == status_filter.lower()]
        summary["filtered_count"] = len(filtered)
        ctx_.deps.retrieved_objects.extend(filtered)
        ctx_.deps.emit_event({
            "type": "status",
            "content": f"Found {len(filtered)} DARs" + (f" (of {summary['total_count']} total)" if source_filter or owner_filter or status_filter else ""),
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        filtered.insert(0, dict(summary))
        return filtered

    @agent.tool
    def search_by_team(
        ctx_: RunContext[SessionContext],
        team_name: str,
        query: str = "",
        limit: int = 10,
    ) -> list[dict]:
        """Search documents owned by a specific team on a topic.

        Use this tool when the user asks about a TOPIC within a team's work
        (e.g., "What has ESA decided about security?", "Show me Data Office
        principles about data quality"). This does a semantic/hybrid search
        over that team's documents.

        DO NOT use this tool to enumerate ALL documents for a team
        (e.g., "List all ESA principles", "Which principles are ESA owned?").
        For exhaustive ownership listing, use list_principles or
        list_adrs and filter by owner_team_abbr.

        Known team abbreviations: ESA, BA, DO, NB-EA, EA

        Args:
            team_name: Team name or abbreviation (e.g., "ESA", "DO", "NB-EA")
            query: Topic to search within the team's documents
            limit: Maximum number of results per collection

        Returns:
            Topically relevant documents filtered by owner
        """
        if ctx_.deps.check_iteration_limit():
            return [{"error": "Tool call limit reached"}]
        elapsed = elapsed_ms(ctx_.deps._query_start)
        ctx_.deps.emit_event({
            "type": "decision",
            "content": f"Decision: search_by_team Reasoning: Searching documents owned by '{team_name}'",
            "elapsed_ms": elapsed,
        })
        result = toolkit.search_by_team(team_name, query, limit)
        ctx_.deps.retrieved_objects.extend(result)
        ctx_.deps.emit_event({
            "type": "status",
            "content": f"Found {len(result)} documents for team '{team_name}'",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        return result

    # ── Capability gap probe (9) ──

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
            agent="rag",
        )

    return agent


class RAGAgent:
    """Pydantic AI–based RAG agent for knowledge base queries.

    Tools:
      1. search_architecture_decisions — hybrid search ADRs
      2. search_principles — hybrid search PCPs
      3. search_policies — hybrid search policy documents
      4. list_adrs — enumerate all ADRs
      5. list_principles — enumerate all PCPs
      6. list_policies — enumerate all policies
      7. list_dars — enumerate all approval records (from both collections)
      8. search_by_team — search docs by owner team
      9. request_data — capability gap probe
    """

    def __init__(self, client: WeaviateClient):
        from aion.agents.quality_gate import ResponseQualityGate

        self.client = client
        self.toolkit = RAGToolkit(client)
        self._agent = _build_rag_agent(self.toolkit)
        self._quality_gate = ResponseQualityGate()

    async def query(
        self,
        question: str,
        collection_names: list[str] | None = None,
        event_queue=None,
        skill_tags: list[str] | None = None,
        doc_refs: list[str] | None = None,
        conversation_id: str | None = None,
        artifact_context: str | None = None,
        complexity: str | None = None,
        prior_sources: list[dict] | None = None,
        message_history: list[ModelMessage] | None = None,
        running_summary: str | None = None,
        step_index: int | None = None,
    ) -> tuple[str, list[dict]]:
        """Process a query using the Pydantic AI agent.

        Returns (response_text, retrieved_objects) tuple.
        """
        skill_content = _get_skill_content(question, skill_tags=skill_tags)

        ctx = SessionContext(
            conversation_id=conversation_id,
            event_queue=event_queue,
            doc_refs=doc_refs or [],
            skill_tags=skill_tags or [],
            artifact_context=artifact_context,
            agent_label=AGENT_LABELS["rag_agent"],
            step_index=step_index,
            system_prompt=self._build_system_prompt(
                skill_content, artifact_context, prior_sources,
            ),
            _query_start=time.perf_counter(),
            max_tool_calls=_get_max_tool_calls("rag_agent", 15),
            running_summary=running_summary,
        )

        logger.info(f"RAGAgent processing: {question}")
        logger.info("rag_agent_model model=%s", self._agent.model.model_name)

        # ── Run the agent ──

        try:
            # Prepend document content to user message for cross-reference
            user_message = question
            if artifact_context:
                user_message = f"{artifact_context}\n\n## QUESTION:\n{question}"

            result = await self._agent.run(
                user_message, deps=ctx, message_history=message_history or [],
            )
            final_response = result.output

            # Post-generation quality gate
            final_response, _gate_meta = await self._quality_gate.evaluate(
                response=final_response,
                query=question,
                complexity=complexity,
                event_queue=ctx.event_queue,
                agent_label=ctx.agent_label,
            )

            total_ms = elapsed_ms(ctx._query_start)
            logger.info(
                f"[timing] RAGAgent total: {total_ms}ms "
                f"({ctx.tool_call_count} tool calls)"
            )

        except Exception as e:
            # Permanent LLM errors must not be swallowed into fallback
            if _is_permanent_llm_error(e):
                from aion.persona import PermanentLLMError
                raise PermanentLLMError(
                    f"Model error: {e}. Check your model settings."
                ) from e
            # Transient errors: fall back to direct tool execution
            logger.warning(
                "RAGAgent failed: %s, using direct tool execution step=%s",
                e, ctx.step_index,
            )
            final_response, objects = await self._direct_query(question, ctx)
            return final_response, objects

        return final_response, ctx.retrieved_objects

    def _build_system_prompt(
        self,
        skill_content: str,
        artifact_context: str | None,
        prior_sources: list[dict] | None = None,
    ) -> str:
        """Build the system prompt from skill content + optional artifact + prior sources."""
        parts = [
            "You are AInstein, the Energy System Architecture AI Assistant at Alliander.",
            "",
            "Your role is to help architects, engineers, and stakeholders navigate "
            "Alliander's energy system architecture knowledge base.",
        ]
        if skill_content:
            parts.extend(["", skill_content])
        if artifact_context:
            # Cross-reference mode: document + KB. The user uploaded a
            # document and wants to compare it against KB content.
            parts.extend([
                "",
                "The user uploaded a document and is asking you to cross-reference "
                "it against the knowledge base. Use your search tools to find "
                "relevant ADRs, principles, or policies. Compare the uploaded "
                "document against what you find. Do NOT search the knowledge base "
                "FOR the uploaded document -- it is already provided below.",
                "",
                "When presenting your analysis, aim to cover:",
                "- Which principles are relevant and how they relate to the document",
                "- Where the document aligns with existing principles",
                "- Where there are gaps or conflicts",
                "- Identify gaps in the document compared to the knowledge base",
                "- Specific recommendations citing the ADR.XX / PCP.XX identifiers",
                "Adapt the depth and structure to match the user's question.",
                "",
                "NEVER claim you have access to a document unless its content "
                "appears in your current context. If a user references a document "
                "you cannot see, tell them to re-upload it.",
                "",
                # Document content moved to user message (not system prompt).
                # Models process user message content reliably; long system
                # prompts get truncated or deprioritized by smaller models.
            ])
        else:
            # Normal KB-only mode
            parts.extend([
                "",
                "Guidelines:",
                "- Base your answers strictly on the provided context from tools",
                "- If the information is not available, clearly state that",
                "- Be concise but thorough",
                "- When referencing ADRs, include the ADR identifier (e.g., ADR.12)",
                "- When referencing Principles, include the PCP identifier (e.g., PCP.10)",
                "",
                "NEVER claim you have access to a document unless its content "
                "appears in your current context. If a user references a document "
                "you cannot see, tell them to re-upload it.",
            ])
        if prior_sources:
            # Size is already capped upstream (50 items, lightweight fields only).
            sources_text = json.dumps(prior_sources)
            parts.extend([
                "",
                "## PREVIOUS TURN RESULTS",
                "The user is asking a follow-up about these results from the "
                "previous query. Use them to answer if possible before searching "
                "the knowledge base again.",
                "",
                f"```json\n{sources_text}\n```",
            ])
        return "\n".join(parts)

    # ── Fallback: _direct_query (degraded mode) ──

    async def _direct_query(
        self, question: str, ctx: SessionContext
    ) -> tuple[str, list[dict]]:
        """Direct query execution when the agent fails.

        Keyword-based routing to listing handlers or search+LLM fallback.
        This is a degraded-mode path — see CLAUDE.md §2 Known exception.
        """
        # If doc_refs exist, use the search tool directly instead of
        # keyword-based routing. This ensures the 400 fallback still
        # produces content-rich results for orchestrator steps.
        if ctx.doc_refs:
            adr_refs = [r for r in ctx.doc_refs if r.upper().startswith("ADR")]
            pcp_refs = [r for r in ctx.doc_refs if r.upper().startswith("PCP")]
            all_results = []
            if adr_refs:
                logger.info("_direct_query: using doc_refs for ADR search step=%s", ctx.step_index)
                all_results.extend(
                    self.toolkit.search_architecture_decisions(
                        question, doc_refs=adr_refs,
                    )
                )
            if pcp_refs:
                logger.info("_direct_query: using doc_refs for PCP search step=%s", ctx.step_index)
                all_results.extend(
                    self.toolkit.search_principles(
                        question, doc_refs=pcp_refs,
                    )
                )
            if all_results:
                ctx_limit = _get_truncation().get("max_context_results", 50)
                context = "\n\n".join([
                    f"[{r.get('type', 'Document')}] "
                    f"{r.get('title', r.get('label', 'Untitled'))}: "
                    f"{r.get('content', r.get('definition', ''))}"
                    for r in all_results[:ctx_limit]
                ])
                skill_content = _get_skill_content(question)
                system_prompt = self._build_system_prompt(skill_content, ctx.artifact_context)
                user_prompt = f"Context:\n{context}\n\nQuestion: {question}"
                if ctx.artifact_context:
                    user_prompt = f"{ctx.artifact_context}\n\n{user_prompt}"
                if settings.effective_rag_provider != "ollama":
                    response_text = await self._generate_with_openai(system_prompt, user_prompt)
                else:
                    response_text = await self._generate_with_ollama(system_prompt, user_prompt)
                return response_text, all_results

        question_lower = question.lower()

        # Listing pattern detection (keyword-based fallback)
        list_adr_patterns = [
            "what adr", "list adr", "list all adr", "show adr", "show all adr",
            "adrs exist", "all adrs", "all the adr", "architecture decision",
        ]
        if any(p in question_lower for p in list_adr_patterns):
            logger.info("Detected ADR listing query, using direct fetch")
            return self._handle_list_adrs_query()

        list_principle_patterns = [
            "what principle", "list principle", "list all principle",
            "show principle", "principles exist", "all principles",
            "all the principle", "governance principle",
        ]
        if any(p in question_lower for p in list_principle_patterns):
            logger.info("Detected principles listing query, using direct fetch")
            return self._handle_list_principles_query()

        list_policy_patterns = [
            "what polic", "list polic", "list all polic", "show polic",
            "policies exist", "all policies", "all the polic",
            "policy document", "what beleid", "governance polic",
        ]
        if any(p in question_lower for p in list_policy_patterns):
            logger.info("Detected policy listing query, using direct fetch")
            return self._handle_list_policies_query()

        list_dar_patterns = [
            "approval record", "list dar", "show dar", "all dar",
            "dars exist", "all the dar", "decision approval",
        ]
        if any(p in question_lower for p in list_dar_patterns):
            logger.info("Detected DAR listing query, using direct fetch")
            return self._handle_list_dars_query()

        # General search fallback
        query_vector = self.toolkit._get_query_vector(question)
        all_results = []

        content_filter = Filter.by_property("doc_type").equal("content")
        metadata_request = MetadataQuery(score=True, distance=True)
        content_limit = _get_truncation().get("content_max_chars", 800)

        collection_map = [
            ("ArchitecturalDecision", "ADR", ["adr", "decision", "architecture"]),
            ("Principle", "Principle", ["principle", "governance", "esa"]),
            ("PolicyDocument", "Policy", ["policy", "data governance", "compliance"]),
        ]

        # Search relevant collections based on keyword triggers
        for base_name, type_label, keywords in collection_map:
            if not any(term in question_lower for term in keywords):
                continue
            try:
                collection = self.client.collections.get(base_name)
                props = self.toolkit._get_return_props(collection)
                coll_filter = content_filter if base_name != "PolicyDocument" else None
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=5,
                    alpha=settings.alpha_vocabulary,
                    filters=coll_filter, return_metadata=metadata_request,
                    return_properties=props,
                )
                for obj in results.objects:
                    item = self.toolkit._build_result(obj, props, content_limit)
                    item["type"] = type_label
                    item["distance"] = obj.metadata.distance
                    item["score"] = obj.metadata.score
                    all_results.append(item)
            except Exception as e:
                logger.warning(f"Error searching {base_name}: {e}")

        # If no specific collection matched, search all
        if not all_results:
            for base_name, type_label, _ in collection_map:
                try:
                    collection = self.client.collections.get(base_name)
                    props = self.toolkit._get_return_props(collection)
                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=3,
                        alpha=settings.alpha_vocabulary,
                        return_metadata=metadata_request,
                        return_properties=props,
                    )
                    for obj in results.objects:
                        item = self.toolkit._build_result(obj, props, content_limit)
                        item["type"] = type_label
                        item["distance"] = obj.metadata.distance
                        item["score"] = obj.metadata.score
                        all_results.append(item)
                except Exception as e:
                    logger.warning(f"Error searching {base_name}: {e}")

        # Abstention check — with general knowledge fallback for broad queries
        abstain, reason = should_abstain(question, all_results)
        if abstain:
            if is_general_knowledge_eligible(question):
                logger.info("RAG abstained but query eligible for general knowledge fallback")
                fallback = await self._general_knowledge_fallback(question)
                if fallback:
                    return fallback, all_results
            logger.info(f"Abstaining from query: {reason}")
            return get_abstention_response(reason), all_results

        # Build context — read limit from config so listing queries aren't
        # silently truncated in the fallback path.
        ctx_limit = _get_truncation().get("max_context_results", 50)
        context = "\n\n".join([
            f"[{r.get('type', 'Document')}] "
            f"{r.get('title', r.get('label', 'Untitled'))}: "
            f"{r.get('content', r.get('definition', ''))}"
            for r in all_results[:ctx_limit]
        ])

        skill_content = _get_skill_content(question)
        system_prompt = f"""You are AInstein, the Energy System Architecture AI Assistant at Alliander.

Your role is to help architects, engineers, and stakeholders navigate Alliander's energy system architecture knowledge base.

{skill_content}

Guidelines:
- Base your answers strictly on the provided context
- If the information is not in the context, clearly state that you don't have that information
- Be concise but thorough
- When referencing ADRs, include the ADR identifier (e.g., ADR.12)
- When referencing Principles, include the PCP identifier (e.g., PCP.10)
- For vocabulary terms, include the source standard (e.g., from IEC 61970)
- For technical terms, provide clear explanations"""
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

        # Generate response based on provider
        if settings.effective_rag_provider != "ollama":
            response_text = await self._generate_with_openai(system_prompt, user_prompt)
        else:
            response_text = await self._generate_with_ollama(system_prompt, user_prompt)

        return response_text, all_results

    async def _generate_with_ollama(
        self, system_prompt: str, user_prompt: str
    ) -> str:
        """Generate response using Ollama API."""
        import httpx

        start_time = time.perf_counter()
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            async with httpx.AsyncClient(timeout=settings.timeout_long_running) as client:
                response = await client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model": settings.effective_rag_model,
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {"num_predict": 1000},
                    },
                )
                response.raise_for_status()
                result = response.json()
                response_text = result.get("response", "")

                # Strip <think>...</think> tags
                response_text = strip_think_tags(response_text)

                return response_text

        except httpx.TimeoutException:
            raise Exception(
                f"Ollama generation timed out after {elapsed_ms(start_time)}ms."
            )

        except httpx.HTTPStatusError as e:
            raise Exception(
                f"Ollama HTTP error after {elapsed_ms(start_time)}ms: {str(e)}"
            )

    async def _generate_with_openai(
        self, system_prompt: str, user_prompt: str
    ) -> str:
        """Generate response using OpenAI API."""
        from openai import AsyncOpenAI

        model = settings.effective_rag_model
        completion_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        token_limits = get_thresholds_value("get_llm_token_limits", {})
        # Use higher token budget when an uploaded document is in context.
        # Document analysis (review, summarize) needs 4-8x more output than Q&A.
        has_doc = "## LOADED DOCUMENT:" in system_prompt
        if is_reasoning_model(model):
            key = "rag_document_reasoning" if has_doc else "rag_reasoning"
            completion_kwargs["max_completion_tokens"] = token_limits.get(key, 8192 if has_doc else 1000)
        else:
            key = "rag_document_standard" if has_doc else "rag_standard"
            completion_kwargs["max_tokens"] = token_limits.get(key, 4096 if has_doc else 1000)

        async with AsyncOpenAI(
            **settings.get_openai_client_kwargs(
                settings.effective_rag_provider, timeout=settings.timeout_long_running,
            )
        ) as openai_client:
            response = await openai_client.chat.completions.create(**completion_kwargs)
        return response.choices[0].message.content

    _GK_PREFIX = (
        "**Note:** This answer draws on general architecture knowledge — "
        "the knowledge base did not contain specific documents on this topic.\n\n"
    )
    _GK_SUFFIX = (
        "\n\n---\n*For organization-specific guidance, try asking about specific "
        "ADRs, principles, or policies in the knowledge base.*"
    )

    async def _general_knowledge_fallback(self, question: str) -> str | None:
        """Answer from general LLM knowledge when RAG has no results.

        Returns None if the LLM also can't provide a useful answer.
        Programmatically prepends/appends disclaimer so it always appears.
        """
        system_prompt = (
            "You are a senior enterprise architect. Answer the following question "
            "using your general professional knowledge. Be practical and actionable."
        )
        try:
            if settings.effective_rag_provider != "ollama":
                response = await self._generate_with_openai(system_prompt, question)
            else:
                response = await self._generate_with_ollama(system_prompt, question)
            return self._GK_PREFIX + response + self._GK_SUFFIX
        except Exception as e:
            logger.warning(f"General knowledge fallback failed: {e}")
            return None

    # ── Listing query handlers (fallback path) ──

    def _handle_list_adrs_query(self) -> tuple[str, list[dict]]:
        """Handle 'list all ADRs' directly in fallback mode."""
        try:
            all_results = self.toolkit.list_adrs()
        except Exception as e:
            logger.warning(f"Error listing ADRs: {e}")
            return "I encountered an error while retrieving the ADR list.", []

        if not all_results:
            return (
                "No Architectural Decision Records (ADRs) were found "
                "in the knowledge base.",
                [],
            )

        response_lines = [
            f"I found {len(all_results)} Architectural Decision Records (ADRs):\n"
        ]
        for adr in all_results:
            status_badge = (
                f"[{adr.get('status', '')}]" if adr.get("status") else ""
            )
            title = (adr.get("title", "") or "").split(" - ")[0]
            response_lines.append(f"- **{title}** {status_badge}")

        return "\n".join(response_lines), all_results

    def _handle_list_principles_query(self) -> tuple[str, list[dict]]:
        """Handle 'list all principles' directly in fallback mode."""
        try:
            all_results = self.toolkit.list_principles()
        except Exception as e:
            logger.warning(f"Error listing principles: {e}")
            return (
                "I encountered an error while retrieving the principles list.",
                [],
            )

        if not all_results:
            return "No principles were found in the knowledge base.", []

        response_lines = [f"I found {len(all_results)} principles:\n"]
        for principle in all_results:
            pn = principle.get("principle_number", "")
            pcp = f"PCP.{int(pn)}" if pn else ""
            title = (principle.get("title", "") or "").split(" - ")[0]
            status_badge = (
                f"[{principle.get('status', '')}]"
                if principle.get("status")
                else ""
            )
            response_lines.append(f"- **{pcp} {title}** {status_badge}")

        return "\n".join(response_lines), all_results

    def _handle_list_policies_query(self) -> tuple[str, list[dict]]:
        """Handle 'list all policies' directly in fallback mode."""
        try:
            all_results = self.toolkit.list_policies()
        except Exception as e:
            logger.warning(f"Error listing policies: {e}")
            return (
                "I encountered an error while retrieving the policy list.",
                [],
            )

        if not all_results:
            return (
                "No policy documents were found in the knowledge base.",
                [],
            )

        response_lines = [
            f"I found {len(all_results)} policy documents:\n"
        ]
        for policy in all_results:
            title = policy.get("title", "Untitled")
            owner = policy.get("owner_team", "")
            owner_suffix = f" — Owner: {owner}" if owner else ""
            response_lines.append(f"- {title}{owner_suffix}")

        return "\n".join(response_lines), all_results

    def _handle_list_dars_query(self) -> tuple[str, list[dict]]:
        """Handle 'list all DARs' directly in fallback mode."""
        try:
            all_results = self.toolkit.list_dars()
        except Exception as e:
            logger.warning(f"Error listing DARs: {e}")
            return (
                "I encountered an error while retrieving the approval records.",
                [],
            )

        if not all_results:
            return "No approval records were found in the knowledge base.", []

        response_lines = [f"I found {len(all_results)} approval records:\n"]
        for dar in all_results:
            title = dar.get("title", "Untitled")
            source = dar.get("dar_source", "")
            source_tag = f" [{source}]" if source else ""
            response_lines.append(f"- {title}{source_tag}")

        return "\n".join(response_lines), all_results

    def query_sync(self, question: str) -> str:
        """Synchronous query wrapper for CLI usage."""
        import asyncio
        response, _ = asyncio.run(self.query(question))
        return response
