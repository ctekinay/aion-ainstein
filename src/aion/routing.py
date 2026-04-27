"""Execution model routing -- determines which agent handles a query.

Extracted from chat_ui.py so tests can import routing logic without
pulling in FastAPI, Weaviate, and the full dependency chain.
"""

from enum import StrEnum

from aion.skills.registry import get_skill_registry


class ExecutionModel(StrEnum):
    """Execution pipeline types for query routing.

    StrEnum so that comparisons with plain strings still work
    (e.g. ExecutionModel.TREE == "tree" is True), while giving
    static analysis and autocomplete benefits.
    """

    TREE = "tree"
    GENERATION = "generation"
    VOCABULARY = "vocabulary"
    ARCHIMATE = "archimate"
    INSPECT = "inspect"
    REFINEMENT = "refinement"
    PRINCIPLE = "principle"
    REPO_ANALYSIS = "repo_analysis"
    DOCUMENT_ANALYSIS = "document_analysis"


# Keep in sync with skill registry tags in skills/skills-registry.yaml.
# Grep for all tags the Persona can emit and ensure coverage.
# If a new skill is added and its tag isn't here, document queries
# will misroute to DOCUMENT_ANALYSIS instead of TREE.
_KB_SKILL_TAGS = frozenset({
    "rag-quality-assurance", "principle-quality", "architecture-review",
    "esa-document-ontology", "archimate", "skosmos",
})


def _has_kb_skill_tags(skill_tags: list[str] | None) -> bool:
    """Check if skill_tags contain KB-related tags (cross-reference intent)."""
    if not skill_tags:
        return False
    return bool(set(skill_tags) & _KB_SKILL_TAGS)


# Terms that indicate the user wants to compare a document against KB content.
# Used as a safety net when the Persona fails to set KB skill tags (common on
# weaker models like Ollama 20B). This is data extraction, not intent detection
# — the Persona already classified intent; we're just catching missing tags.
_KB_CONCEPT_TERMS = (
    "principle", "pcp", "adr", "decision", "policy",
    "knowledge base", "comply", "compliance", "violat",
    "evaluate against", "compare against", "check against",
)


def _mentions_kb_concepts(query: str) -> bool:
    """Detect if query references KB content (principles, ADRs, policies)."""
    lower = query.lower()
    return any(term in lower for term in _KB_CONCEPT_TERMS)


def _route_document(query: str | None) -> ExecutionModel:
    """Route a document query based on KB concept mentions.

    Used by both the inspect and document safety-net paths to avoid
    duplicating the KB-concept detection logic.
    """
    if query and _mentions_kb_concepts(query):
        lower = query.lower()
        if any(t in lower for t in ("principle", "pcp", "compliance", "comply")):
            return ExecutionModel.PRINCIPLE
        return ExecutionModel.TREE
    return ExecutionModel.DOCUMENT_ANALYSIS


def get_execution_model(
    intent: str,
    skill_tags: list[str] | None,
    artifact_content_type: str | None = None,
    query: str | None = None,
    github_refs: list[str] | None = None,
    doc_refs: list[str] | None = None,
) -> ExecutionModel:
    """Determine execution path from intent, skill_tags, and context.

    Priority order:
    1. repo-analysis with generation intent (dedicated pipeline)
    1b. GitHub URL structural fallback (Persona misclassified intent)
    2. Skill_tags registry lookup (most specific signal)
    3. Intent-based routing (generation, inspect)
    4. Document safety net (weak-model fallback)
    5. Default to TREE
    """
    _is_document = (
        artifact_content_type
        and artifact_content_type.startswith("document/")
    )

    # ── 1. Repo-analysis: dedicated gate, requires generation intent ──
    # Stale "repo-analysis" tags from previous turns must NOT trigger
    # the extraction pipeline on follow_up/retrieval/inspect/refinement.
    if skill_tags and "repo-analysis" in skill_tags and intent == "generation":
        return ExecutionModel.REPO_ANALYSIS

    # ── 1b. GitHub URL structural fallback ───────────────────────────
    # When the Persona extracts a GitHub URL but misclassifies intent
    # (e.g. retrieval instead of generation), route to REPO_ANALYSIS.
    # doc_refs wins: "What does ADR.21 say about github.com/...?" is a
    # KB query that happens to mention a URL, not a repo analysis request.
    # inspect stays inspect: bare URL queries are browse-only.
    if (
        github_refs
        and not doc_refs
        and intent != "inspect"
        and not (skill_tags and set(skill_tags) - {"repo-analysis"})
    ):
        return ExecutionModel.REPO_ANALYSIS

    # ── 2. Skill_tags registry: single lookup, used everywhere ────────
    _registry_model = None
    if skill_tags:
        registry = get_skill_registry()
        _registry_model = registry.get_execution_model(skill_tags)

    # ── 3. Generation intent ─────────────────────────────────────────
    if intent == ExecutionModel.GENERATION:
        # If skill_tags point to a specialist that isn't part of the
        # generation pipeline, honour them.  "Create a review matrix"
        # with tags=["principle-quality"] → PRINCIPLE, not GENERATION.
        # ARCHIMATE stays in GENERATION (the generation pipeline loads
        # the archimate skill).  REPO_ANALYSIS already handled above.
        if _registry_model and _registry_model not in (
            ExecutionModel.GENERATION, ExecutionModel.ARCHIMATE,
            ExecutionModel.TREE, ExecutionModel.REPO_ANALYSIS,
        ):
            return ExecutionModel(_registry_model)
        return ExecutionModel.GENERATION

    # ── 4. Inspect intent ────────────────────────────────────────────
    if intent == ExecutionModel.INSPECT:
        # If skill_tags point to a specialist, honour them.
        # REPO_ANALYSIS excluded — has its own generation-only gate.
        if _registry_model and _registry_model not in (
            ExecutionModel.INSPECT, ExecutionModel.TREE,
            ExecutionModel.REPO_ANALYSIS,
        ):
            return ExecutionModel(_registry_model)
        # A PDF is never an ArchiMate model.
        if _is_document:
            return _route_document(query)
        return ExecutionModel.INSPECT

    # ── 5. Refinement intent ─────────────────────────────────────────
    if intent == ExecutionModel.REFINEMENT and _registry_model:
        # Assessment-only tags (principle-quality) produce RAG output,
        # not agent artifacts — refinement stays in TREE.
        _ASSESSMENT_ONLY = {"principle-quality"}
        if skill_tags and set(skill_tags).issubset(_ASSESSMENT_ONLY):
            return ExecutionModel.TREE
        if _registry_model in (
            ExecutionModel.GENERATION, ExecutionModel.ARCHIMATE,
            ExecutionModel.PRINCIPLE,
        ):
            return ExecutionModel(_registry_model)

    # ── 6. Document without KB tags: safety net for weak models ──────
    # follow_up excluded: follow-ups need conversation history which TREE
    # provides. DOCUMENT_ANALYSIS is for standalone doc analysis.
    if (
        _is_document
        and intent in ("retrieval", "listing")
        and not _has_kb_skill_tags(skill_tags)
    ):
        return _route_document(query)

    # ── 7. Skill_tags fallback (retrieval, listing, follow_up) ───────
    if _registry_model and _registry_model in (
        ExecutionModel.VOCABULARY, ExecutionModel.ARCHIMATE,
        ExecutionModel.PRINCIPLE,
    ):
        return ExecutionModel(_registry_model)

    return ExecutionModel.TREE
