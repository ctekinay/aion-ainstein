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


def get_execution_model(
    intent: str,
    skill_tags: list[str] | None,
    artifact_content_type: str | None = None,
) -> ExecutionModel:
    """Determine execution path based on intent and skill registry.

    Intent is the sole routing gate. The registry's execution field
    confirms the pipeline type but never overrides intent.
    """
    # Repo analysis only for generation intent -- follow-ups, retrieval, and
    # refinement with stale "repo-analysis" tags fall through to normal routing.
    # inspect is excluded: it's for reviewing existing models, not running the
    # extraction pipeline. See: misroute incident where Persona classified
    # "Is this compliant with our principles?" as inspect+repo-analysis.
    if skill_tags and "repo-analysis" in skill_tags and intent == "generation":
        return ExecutionModel.REPO_ANALYSIS
    if intent == ExecutionModel.GENERATION:
        return ExecutionModel.GENERATION

    # Document analysis: uploaded doc WITHOUT KB cross-reference intent.
    # MUST be before INSPECT check -- intercepts inspect misroute for documents.
    # If Persona set KB-related skill_tags, user wants cross-reference -> TREE.
    if (
        artifact_content_type
        and artifact_content_type.startswith("document/")
        and intent in ("inspect", "retrieval", "listing", "follow_up")
        and not _has_kb_skill_tags(skill_tags)
    ):
        return ExecutionModel.DOCUMENT_ANALYSIS

    if intent == ExecutionModel.INSPECT:
        return ExecutionModel.INSPECT
    if intent == ExecutionModel.REFINEMENT and skill_tags:
        # Only route refinement to a specialist agent if the skill tag
        # indicates content that agent actually produces. Assessment/quality
        # tags (e.g. principle-quality) produce RAG/synthesis output, not
        # agent artifacts -- refinement of those stays in TREE.
        _ASSESSMENT_ONLY_TAGS = {"principle-quality"}
        if set(skill_tags).issubset(_ASSESSMENT_ONLY_TAGS):
            return ExecutionModel.TREE
        registry = get_skill_registry()
        exec_model = registry.get_execution_model(skill_tags)
        if exec_model == ExecutionModel.GENERATION:
            return ExecutionModel.GENERATION
        if exec_model == ExecutionModel.ARCHIMATE:
            return ExecutionModel.ARCHIMATE
        if exec_model == ExecutionModel.PRINCIPLE:
            return ExecutionModel.PRINCIPLE
    # Vocabulary / ArchiMate / Principle routing via skill registry
    if skill_tags:
        registry = get_skill_registry()
        exec_model = registry.get_execution_model(skill_tags)
        if exec_model == ExecutionModel.VOCABULARY:
            return ExecutionModel.VOCABULARY
        if exec_model == ExecutionModel.ARCHIMATE:
            return ExecutionModel.ARCHIMATE
        if exec_model == ExecutionModel.PRINCIPLE:
            return ExecutionModel.PRINCIPLE
    return ExecutionModel.TREE
