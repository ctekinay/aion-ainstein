"""Agent package — Pydantic AI agents for RAG and tool orchestration."""

import logging
from dataclasses import dataclass, field
from queue import Queue

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.tools import RunContext

logger = logging.getLogger(__name__)


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
    "document_agent": "Document Analysis",
    "synthesis": "Synthesis",
}


# Human-readable labels for tool names — shown in thinking steps.
# Unmapped tools fall back to title-cased snake_case.
_TOOL_LABELS: dict[str, str] = {
    # RAG Agent
    "search_architecture_decisions": "Searching architecture decisions",
    "search_principles": "Searching principles",
    "search_policies": "Searching policies",
    "list_adrs": "Listing architecture decisions",
    "list_principles": "Listing principles",
    "list_policies": "Listing policies",
    "list_dars": "Listing approval records",
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


def _get_max_tool_calls(agent_key: str, fallback: int) -> int:
    """Read max_tool_calls for an agent from thresholds.yaml.

    Args:
        agent_key: Key from AGENT_LABELS (e.g. "archimate_agent").
        fallback: Hardcoded default if config unavailable.
    """
    try:
        from aion.skills.loader import get_thresholds_value
        agent_config = get_thresholds_value("get_agent_config", {})
        max_calls = agent_config.get("max_tool_calls", {})
        return max_calls.get(agent_key, max_calls.get("default", fallback))
    except Exception:
        logger.warning("Failed to read max_tool_calls for '%s', using fallback %d", agent_key, fallback)
        return fallback


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

    # Rolling conversation summary for history processor
    running_summary: str | None = None

    # Orchestrator step index (None for non-orchestrator calls)
    step_index: int | None = None

    # Search result cache — prevents retry spirals where the agent calls
    # the same search tool with the same parameters multiple times.
    # Scoped to a single query() call, not persisted across requests.
    _search_cache: dict[str, list[dict]] = field(default_factory=dict)

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
        if self.tool_call_count > self.max_tool_calls:
            self.emit_event({
                "type": "status",
                "content": (
                    f"Tool call limit reached "
                    f"({self.tool_call_count}/{self.max_tool_calls}). "
                    f"Stopping iteration."
                ),
            })
            logger.warning(
                "tool_call_limit_reached agent=%s count=%d max=%d",
                self.agent_label, self.tool_call_count, self.max_tool_calls,
            )
            return True
        return False


# Max turn pairs (request + response) to keep in message history.
# 8 pairs = 16 messages — sized for tool-heavy agents (repo analysis: 7 tool calls).
# process_history boundary logic correctly backs up past orphaned tool returns (Bug V fix).
MAX_HISTORY_PAIRS = 8


def process_history(
    ctx: RunContext[SessionContext], messages: list[ModelMessage]
) -> list[ModelMessage]:
    """Truncate conversation history and optionally prepend running summary.

    Keeps the last MAX_HISTORY_PAIRS turn pairs. If a tool call or tool
    return sits at the truncation boundary, includes the extra message(s)
    to avoid corrupted tool interaction sequences.

    Shared across all agents — extracted from rag_agent.py.
    """
    result: list[ModelMessage] = []

    if ctx.deps.running_summary:
        result.append(ModelRequest(parts=[
            UserPromptPart(content=f"[Prior conversation summary]: {ctx.deps.running_summary}")
        ]))

    if not messages:
        return result

    max_msgs = MAX_HISTORY_PAIRS * 2
    if len(messages) <= max_msgs:
        result.extend(messages)
        return result

    start = len(messages) - max_msgs
    # Back up past ModelResponse (assistant) AND tool-return ModelRequests.
    # Both serialize to OpenAI message types that require a preceding partner.
    while start > 0 and (
        isinstance(messages[start], ModelResponse)
        or (
            isinstance(messages[start], ModelRequest)
            and messages[start].parts  # guard: all() on empty iterable returns True
            and all(isinstance(p, ToolReturnPart) for p in messages[start].parts)
        )
    ):
        start -= 1
    if start < 0:
        start = 0
    result.extend(messages[start:])
    return result
