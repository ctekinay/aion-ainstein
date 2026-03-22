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


# ── generation and inspect are never overridden by skill_tags ─────────────

def test_generation_intent_ignores_skill_tags():
    """generation intent always routes to GENERATION regardless of skill_tags."""
    with patch("aion.routing.get_skill_registry") as mock_reg:
        result = get_execution_model("generation", skill_tags=["vocabulary"])
    assert result == ExecutionModel.GENERATION
    mock_reg.assert_not_called()


def test_inspect_intent_ignores_skill_tags():
    """inspect intent always routes to INSPECT regardless of skill_tags."""
    with patch("aion.routing.get_skill_registry") as mock_reg:
        result = get_execution_model("inspect", skill_tags=["archimate"])
    assert result == ExecutionModel.INSPECT
    mock_reg.assert_not_called()


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
    ("inspect",    ExecutionModel.INSPECT),
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
