"""Execution model routing — determines which agent handles a query.

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


def get_execution_model(intent: str, skill_tags: list[str] | None) -> ExecutionModel:
    """Determine execution path based on intent and skill registry.

    Intent is the sole routing gate. The registry's execution field
    confirms the pipeline type but never overrides intent.
    """
    # Repo analysis only for generation intent — follow-ups, retrieval, and
    # refinement with stale "repo-analysis" tags fall through to normal routing.
    # inspect is excluded: it's for reviewing existing models, not running the
    # extraction pipeline. See: misroute incident where Persona classified
    # "Is this compliant with our principles?" as inspect+repo-analysis.
    if skill_tags and "repo-analysis" in skill_tags and intent == "generation":
        return ExecutionModel.REPO_ANALYSIS
    if intent == ExecutionModel.GENERATION:
        return ExecutionModel.GENERATION
    if intent == ExecutionModel.INSPECT:
        return ExecutionModel.INSPECT
    if intent == ExecutionModel.REFINEMENT and skill_tags:
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
