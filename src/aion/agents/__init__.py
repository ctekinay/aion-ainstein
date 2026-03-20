"""Agent package — Pydantic AI agents for RAG and tool orchestration."""

from dataclasses import dataclass, field
from queue import Queue


# Canonical agent display labels — single source of truth.
# Used by SessionContext.agent_label, pixel_agents.py, and the frontend.
AGENT_LABELS: dict[str, str] = {
    "persona": "Persona",
    "orchestrator": "Orchestrator",
    "rag_agent": "RAG Agent",
    "vocabulary_agent": "Vocabulary",
    "archimate_agent": "ArchiMate",
    "principle_agent": "Principles",
    "repo_analysis_agent": "Repository Analysis",
    "synthesis": "Synthesis",
}


# Human-readable labels for tool names — shown in thinking steps.
# Unmapped tools fall back to title-cased snake_case.
_TOOL_LABELS: dict[str, str] = {
    # RAG Agent
    "search_architecture_decisions": "Searching architecture decisions",
    "search_principles": "Searching principles",
    "search_policies": "Searching policies",
    "list_all_adrs": "Listing all architecture decisions",
    "list_all_principles": "Listing all principles",
    "list_all_policies": "Listing all policies",
    "search_by_team": "Searching documents by team",
    # Vocabulary Agent
    "skosmos_search": "Searching vocabulary",
    "skosmos_concept_details": "Getting concept details",
    "skosmos_list_vocabularies": "Listing vocabularies",
    "search_knowledge_base": "Searching knowledge base (fallback)",
    # Principle Agent
    "search_related_principles": "Searching related principles",
    "validate_principle_structure": "Validating principle structure",
    "save_principle": "Saving principle",
    "get_principle": "Loading principle",
    # Repo Analysis Agent
    "clone_repo": "Cloning repository",
    "profile_repo": "Profiling repository structure",
    "extract_manifests": "Extracting manifest files",
    "extract_code_structure": "Analyzing code structure",
    "build_dep_graph": "Building dependency graph",
    "merge_and_save_notes": "Saving architecture analysis",
    # ArchiMate Agent
    "validate_archimate": "Validating ArchiMate XML",
    "inspect_archimate_model": "Inspecting ArchiMate model",
    "merge_archimate_view": "Merging view into model",
    "save_artifact": "Saving artifact",
    "get_artifact": "Loading artifact",
    # Shared
    "request_data": "Checking for missing data",
}


def _humanize_tool_name(tool_name: str) -> str:
    """Convert snake_case tool name to a readable label."""
    return _TOOL_LABELS.get(tool_name, tool_name.replace("_", " ").capitalize())


def _rewrite_decision(event: dict) -> None:
    """Rewrite 'Decision: X Reasoning: Y' into human-readable text in-place.

    Input content:  "Decision: search_principles Reasoning: Searching principles for 'PCP.10'"
    Output content: "Searching principles for 'PCP.10'"
    Also adds a machine-readable "tool" field for pixel agents / debugging.
    """
    content = event.get("content", "")
    if not content.startswith("Decision:"):
        event.setdefault("tool", "unknown")
        return
    # Extract tool name and reasoning
    parts = content.split("Reasoning:", 1)
    if len(parts) == 2:
        tool_name = parts[0].replace("Decision:", "").strip()
        reasoning = parts[1].strip()
        event["tool"] = tool_name
        # Use the LLM's reasoning if it adds context (e.g. includes the query),
        # otherwise fall back to our human-readable label from the map.
        if reasoning and reasoning.lower() != tool_name.replace("_", " ").lower():
            event["content"] = reasoning
        else:
            event["content"] = _humanize_tool_name(tool_name)
    else:
        # No "Reasoning:" part — just "Decision: tool_name"
        tool_name = content.replace("Decision:", "").strip()
        event["tool"] = tool_name
        event["content"] = _humanize_tool_name(tool_name)


@dataclass
class SessionContext:
    """Per-query context threaded through agent tool calls.

    Each field maps to a specific piece of per-query state passed
    to tool functions via RunContext[SessionContext].deps.
    """

    conversation_id: str | None = None
    event_queue: Queue | None = None
    doc_refs: list[str] = field(default_factory=list)
    skill_tags: list[str] = field(default_factory=list)
    artifact_context: str | None = None

    # Human-readable agent name — injected into every emitted event
    agent_label: str = ""

    # Dynamic system prompt — computed in query(), read by @agent.system_prompt
    system_prompt: str = ""

    # Timing — set in query() before agent.run()
    _query_start: float = 0.0

    # Iteration tracking
    tool_call_count: int = 0
    max_tool_calls: int = 4  # overridden from thresholds.yaml at query time

    # Vocabulary disambiguation — tracks per-term ambiguity across searches
    # e.g. {"asset": ["ESAV", "IEC61968", "IEC62443"], "risk": ["ISO31000", "IEC62443"]}
    pending_disambiguations: dict[str, list[str]] = field(default_factory=dict)

    # Accumulated results from tool calls
    retrieved_objects: list[dict] = field(default_factory=list)

    def emit_event(self, event: dict) -> None:
        """Push an SSE event to the queue if one is attached.

        Auto-injects agent_label and rewrites decision text to be human-readable.
        """
        if self.event_queue is not None:
            # Inject agent label
            if self.agent_label and "agent" not in event:
                event["agent"] = self.agent_label
            # Rewrite "Decision: X Reasoning: Y" to human text + add "tool" field
            if event.get("type") == "decision":
                _rewrite_decision(event)
            self.event_queue.put(event)

    def check_iteration_limit(self) -> bool:
        """Increment tool call count, return True if limit exceeded."""
        self.tool_call_count += 1
        return self.tool_call_count > self.max_tool_calls
