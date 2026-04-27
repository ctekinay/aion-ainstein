"""Unit tests for get_execution_model() routing logic.

Mocks aion.routing.get_skill_registry (import-site mock) to isolate
from the YAML skill registry on disk. Tests cover all routing branches
including the critical refinement → generation reroute path.
"""

from unittest.mock import MagicMock, patch

import pytest

from aion.routing import ExecutionModel, get_execution_model


def _make_registry(execution_model: str) -> MagicMock:
    """Return a mock registry whose get_execution_model() returns the given model."""
    registry = MagicMock()
    registry.get_execution_model.return_value = execution_model
    return registry


# ── Intent-only routing (no skill_tags, no registry call) ──────────────────

@pytest.mark.parametrize("intent,expected", [
    ("generation", ExecutionModel.GENERATION),
    ("inspect",    ExecutionModel.INSPECT),
    ("retrieval",  ExecutionModel.TREE),
    ("listing",    ExecutionModel.TREE),
    ("follow_up",  ExecutionModel.TREE),
    ("refinement", ExecutionModel.TREE),   # refinement with NO tags → falls through to TREE
])
def test_intent_only_routing(intent, expected):
    """Intent-only paths that do not consult the registry."""
    result = get_execution_model(intent, skill_tags=None)
    assert result == expected


# ── skill_tags routing via registry ────────────────────────────────────────

@pytest.mark.parametrize("registry_model,expected", [
    (ExecutionModel.VOCABULARY, ExecutionModel.VOCABULARY),
    (ExecutionModel.ARCHIMATE,  ExecutionModel.ARCHIMATE),
    (ExecutionModel.PRINCIPLE,  ExecutionModel.PRINCIPLE),
    (ExecutionModel.TREE,       ExecutionModel.TREE),  # registry default → RAG
])
def test_skill_tag_routing(registry_model, expected):
    """skill_tags present → registry consulted for non-generation/inspect intents."""
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(registry_model)):
        result = get_execution_model("retrieval", skill_tags=["some-tag"])
    assert result == expected


# ── Refinement intent with skill_tags (critical path) ─────────────────────

@pytest.mark.parametrize("registry_model,expected", [
    (ExecutionModel.GENERATION, ExecutionModel.GENERATION),  # refinement → generation reroute
    (ExecutionModel.ARCHIMATE,  ExecutionModel.ARCHIMATE),
    (ExecutionModel.PRINCIPLE,  ExecutionModel.PRINCIPLE),
    (ExecutionModel.TREE,       ExecutionModel.TREE),         # no specific reroute → TREE
])
def test_refinement_with_skill_tags(registry_model, expected):
    """refinement intent + skill_tags → registry consulted for rerouting.

    The refinement → generation path is the most dangerous silent-failure case:
    if it breaks, refinement queries are routed to RAG instead of generation,
    returning search results instead of a refined artifact.
    """
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(registry_model)):
        result = get_execution_model("refinement", skill_tags=["archimate"])
    assert result == expected


# ── generation intent routing ──────────────────────────────────────────────

def test_generation_with_archimate_tags_stays_generation():
    """generation + archimate tags → GENERATION (archimate is part of generation pipeline)."""
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(ExecutionModel.ARCHIMATE)):
        result = get_execution_model("generation", skill_tags=["archimate"])
    assert result == ExecutionModel.GENERATION


def test_generation_with_principle_tags_routes_to_principle():
    """generation + principle-quality → PRINCIPLE (not generation pipeline).

    Catches: "create a review matrix" classified as generation but
    skill_tags=["principle-quality"] points to the principle agent.
    """
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(ExecutionModel.PRINCIPLE)):
        result = get_execution_model("generation", skill_tags=["principle-quality"])
    assert result == ExecutionModel.PRINCIPLE


def test_generation_with_vocabulary_tags_routes_to_vocabulary():
    """generation + vocabulary tags → VOCABULARY (not generation pipeline)."""
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(ExecutionModel.VOCABULARY)):
        result = get_execution_model("generation", skill_tags=["vocabulary"])
    assert result == ExecutionModel.VOCABULARY


def test_inspect_no_tags_routes_to_inspect():
    """inspect intent without skill_tags routes to INSPECT."""
    result = get_execution_model("inspect", skill_tags=None)
    assert result == ExecutionModel.INSPECT


def test_inspect_with_specialist_tags_overrides():
    """inspect + specialist skill_tags → specialist agent wins over inspect.

    Catches Persona misclassification where intent=inspect but skill_tags
    point to a different agent (e.g. principle-quality → PRINCIPLE).
    """
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(ExecutionModel.PRINCIPLE)):
        result = get_execution_model("inspect", skill_tags=["principle-quality"])
    assert result == ExecutionModel.PRINCIPLE


def test_inspect_with_repo_analysis_tag_stays_inspect():
    """inspect + repo-analysis tag → INSPECT (stale tag protection).

    REPO_ANALYSIS is excluded from the override because it has its own
    dedicated gate at line 81 that requires intent=generation.
    """
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(ExecutionModel.REPO_ANALYSIS)):
        result = get_execution_model("inspect", skill_tags=["repo-analysis"])
    assert result == ExecutionModel.INSPECT


def test_inspect_with_inspect_tags_stays_inspect():
    """inspect + tags that map to INSPECT → stays INSPECT (no override)."""
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(ExecutionModel.INSPECT)):
        result = get_execution_model("inspect", skill_tags=["some-inspect-tag"])
    assert result == ExecutionModel.INSPECT


def test_inspect_with_document_no_kb_query():
    """inspect + document/pdf + no KB terms → DOCUMENT_ANALYSIS."""
    result = get_execution_model(
        "inspect", skill_tags=None,
        artifact_content_type="document/pdf",
        query="Summarize this document",
    )
    assert result == ExecutionModel.DOCUMENT_ANALYSIS


def test_inspect_with_document_and_principle_query():
    """inspect + document/pdf + principle query → PRINCIPLE."""
    result = get_execution_model(
        "inspect", skill_tags=None,
        artifact_content_type="document/pdf",
        query="Evaluate against our principles",
    )
    assert result == ExecutionModel.PRINCIPLE


# ── Assessment-only tags bypass specialist routing on refinement ────────

def test_refinement_with_assessment_tag_routes_to_tree():
    """refinement + principle-quality tag → TREE, not PRINCIPLE.

    principle-quality is an assessment skill injected into RAG — its output
    is a synthesis response, not a principle artifact. Refinement of that
    output should stay in RAG/synthesis, not go to PrincipleAgent.
    """
    result = get_execution_model("refinement", skill_tags=["principle-quality"])
    assert result == ExecutionModel.TREE


def test_refinement_with_generate_principle_tag_routes_to_principle():
    """refinement + generate-principle tag → PRINCIPLE (actual artifact)."""
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(ExecutionModel.PRINCIPLE)):
        result = get_execution_model("refinement", skill_tags=["generate-principle"])
    assert result == ExecutionModel.PRINCIPLE


def test_non_refinement_with_assessment_tag_still_routes_to_principle():
    """retrieval + principle-quality → PRINCIPLE (assessment guard only applies to refinement)."""
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(ExecutionModel.PRINCIPLE)):
        result = get_execution_model("retrieval", skill_tags=["principle-quality"])
    assert result == ExecutionModel.PRINCIPLE


# ── Edge cases ────────────────────────────────────────────────────────────

def test_empty_skill_tags_falls_through_to_tree():
    """Empty list is falsy — treated same as no skill_tags."""
    result = get_execution_model("retrieval", skill_tags=[])
    assert result == ExecutionModel.TREE


def test_unknown_intent_defaults_to_tree():
    """Unrecognised intent strings (e.g. new intents) default to TREE."""
    result = get_execution_model("unknown_future_intent", skill_tags=None)
    assert result == ExecutionModel.TREE


# ── repo-analysis routing: generation only ─────────────────────────────

def test_repo_analysis_generation_routes_correctly():
    """generation + repo-analysis → REPO_ANALYSIS (primary path)."""
    result = get_execution_model("generation", skill_tags=["repo-analysis"])
    assert result == ExecutionModel.REPO_ANALYSIS


@pytest.mark.parametrize("intent,expected", [
    ("follow_up",  ExecutionModel.TREE),
    ("retrieval",  ExecutionModel.TREE),
])
def test_repo_analysis_non_generation_does_not_reroute(intent, expected):
    """Non-generation intents with stale repo-analysis tag fall through.

    Prevents the misroute where a follow-up like 'Is this compliant
    with our principles?' was re-routed through the full repo analysis
    pipeline instead of RAG.
    """
    result = get_execution_model(intent, skill_tags=["repo-analysis"])
    assert result == expected


def test_repo_analysis_refinement_does_not_reroute():
    """refinement + repo-analysis → falls through to registry, not REPO_ANALYSIS."""
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(ExecutionModel.TREE)):
        result = get_execution_model("refinement", skill_tags=["repo-analysis"])
    assert result == ExecutionModel.TREE


# ── Document analysis + KB concept fallback (Fix N) ──────────────────────

def test_document_no_kb_tags_no_query_routes_to_document_analysis():
    """Document upload without KB tags and no query → DOCUMENT_ANALYSIS."""
    result = get_execution_model(
        "retrieval", skill_tags=[], artifact_content_type="document/pdf",
    )
    assert result == ExecutionModel.DOCUMENT_ANALYSIS


def test_document_no_kb_tags_with_principle_query_routes_to_principle():
    """Document upload + query mentioning principles but no KB tags → PRINCIPLE.

    Safety net for weak models (Ollama 20B) that fail to set KB skill tags.
    Principle-specific queries go to PRINCIPLE agent (has list_principles +
    compliance evaluation mode), not TREE which misses ~30% of principles.
    """
    result = get_execution_model(
        "retrieval", skill_tags=[], artifact_content_type="document/pdf",
        query="Evaluate this document against the architectural principles",
    )
    assert result == ExecutionModel.PRINCIPLE


def test_document_no_kb_tags_with_adr_query_routes_to_tree():
    """Document upload + query mentioning ADRs but no KB tags → TREE.

    Non-principle KB concepts (ADRs, policies) go to TREE for hybrid search
    since no dedicated agent exists for them.
    """
    result = get_execution_model(
        "retrieval", skill_tags=[], artifact_content_type="document/pdf",
        query="Check this document against our ADRs and decisions",
    )
    assert result == ExecutionModel.TREE


def test_document_no_kb_tags_with_non_kb_query_routes_to_document_analysis():
    """Document upload + generic query without KB terms → DOCUMENT_ANALYSIS."""
    result = get_execution_model(
        "retrieval", skill_tags=[], artifact_content_type="document/pdf",
        query="Summarize this document",
    )
    assert result == ExecutionModel.DOCUMENT_ANALYSIS


def test_follow_up_with_document_no_tags_routes_to_tree():
    """follow_up + document + no tags → TREE (not DOCUMENT_ANALYSIS).

    Follow-ups need conversation history, which TREE provides.
    DOCUMENT_ANALYSIS is for standalone doc analysis without prior context.
    """
    result = get_execution_model(
        "follow_up", skill_tags=None,
        artifact_content_type="document/pdf",
        query="Translate the previous response to English",
    )
    assert result == ExecutionModel.TREE


def test_document_with_kb_tags_routes_past_document_analysis():
    """Document upload WITH KB skill tags → NOT DOCUMENT_ANALYSIS (falls through)."""
    with patch("aion.routing.get_skill_registry", return_value=_make_registry(ExecutionModel.PRINCIPLE)):
        result = get_execution_model(
            "retrieval", skill_tags=["principle-quality"],
            artifact_content_type="document/pdf",
        )
    assert result == ExecutionModel.PRINCIPLE


# ── GitHub URL structural fallback (Fix: github_refs as routing signal) ──

def test_github_refs_routes_to_repo_analysis_when_intent_is_retrieval():
    """github_refs + retrieval intent → REPO_ANALYSIS.

    Regression test: Persona misclassifies "Analyze the architecture of
    https://..." as retrieval. github_refs structural fallback overrides
    the wrong intent and routes to Repo Analysis Agent.
    """
    result = get_execution_model(
        "retrieval", skill_tags=[],
        github_refs=["Alliander/esa-ainstein-artifacts"],
        doc_refs=[],
    )
    assert result == ExecutionModel.REPO_ANALYSIS


def test_github_refs_does_not_override_inspect_intent():
    """github_refs + inspect intent → INSPECT (browse-only stays browse-only).

    A bare URL classified as inspect (e.g. "https://github.com/org/repo")
    should not trigger the full repo analysis pipeline.
    """
    result = get_execution_model(
        "inspect", skill_tags=[],
        github_refs=["Alliander/esa-ainstein-artifacts"],
        doc_refs=[],
    )
    assert result == ExecutionModel.INSPECT


def test_github_refs_does_not_override_principle_skill_tags():
    """github_refs + principle-quality skill_tags → PRINCIPLE, not REPO_ANALYSIS.

    Regression: follow-up query "evaluate this architecture against principles"
    in a conversation that previously analyzed a GitHub repo. Persona correctly
    tags principle-quality but also re-extracts github_refs from history.
    The github_refs fallback must NOT override the explicit skill_tags.
    """
    with patch("aion.routing.get_skill_registry",
               return_value=_make_registry(ExecutionModel.PRINCIPLE)):
        result = get_execution_model(
            "retrieval", skill_tags=["principle-quality"],
            github_refs=["Alliander/esa-ainstein-artifacts"], doc_refs=[],
        )
    assert result == ExecutionModel.PRINCIPLE


def test_github_refs_does_not_override_vocabulary_skill_tags():
    """github_refs + vocabulary skill_tags → VOCABULARY, not REPO_ANALYSIS."""
    with patch("aion.routing.get_skill_registry",
               return_value=_make_registry(ExecutionModel.VOCABULARY)):
        result = get_execution_model(
            "retrieval", skill_tags=["vocabulary"],
            github_refs=["Alliander/esa-ainstein-artifacts"], doc_refs=[],
        )
    assert result == ExecutionModel.VOCABULARY


def test_github_refs_fallback_still_works_without_skill_tags():
    """github_refs + no skill_tags → REPO_ANALYSIS (fallback preserved).

    Ensures the skill_tags guard didn't break the original safety net for
    Persona misclassification where intent=retrieval but no skill_tags are set.
    """
    result = get_execution_model(
        "retrieval", skill_tags=[],
        github_refs=["Alliander/esa-ainstein-artifacts"], doc_refs=[],
    )
    assert result == ExecutionModel.REPO_ANALYSIS


def test_github_refs_fallback_works_with_repo_analysis_tag_only():
    """github_refs + repo-analysis tag + non-generation intent → REPO_ANALYSIS.

    Stale repo-analysis tag from prior turn, but github_refs fallback
    should still fire since no OTHER skill tags are present.
    """
    result = get_execution_model(
        "retrieval", skill_tags=["repo-analysis"],
        github_refs=["Alliander/esa-ainstein-artifacts"], doc_refs=[],
    )
    assert result == ExecutionModel.REPO_ANALYSIS


def test_doc_refs_wins_over_github_refs():
    """doc_refs populated → KB routing wins, github_refs ignored.

    "What does ADR.21 say about github.com/...?" is a KB query that
    happens to mention a URL — doc_refs signal takes priority.
    """
    result = get_execution_model(
        "retrieval", skill_tags=[],
        github_refs=["Alliander/esa-ainstein-artifacts"],
        doc_refs=["ADR.21"],
    )
    assert result == ExecutionModel.TREE
