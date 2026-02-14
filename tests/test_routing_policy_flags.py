"""Tests for routing policy flags and their effect on routing behavior."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.config import Settings, invalidate_config_caches

PROJECT_ROOT = Path(__file__).parent.parent


class TestRoutingPolicyLoading:
    """Verify routing_policy.yaml loads correctly."""

    def test_routing_policy_file_exists(self):
        policy_file = PROJECT_ROOT / "config" / "routing_policy.yaml"
        assert policy_file.exists(), "config/routing_policy.yaml must exist"

    def test_routing_policy_loads_defaults(self):
        invalidate_config_caches()
        s = Settings()
        policy = s.get_routing_policy()
        assert "intent_router_enabled" in policy
        assert "intent_router_mode" in policy
        assert "followup_binding_enabled" in policy
        assert "abstain_gate_enabled" in policy
        assert "tree_enabled" in policy
        assert "debug_headers_enabled" in policy

    def test_routing_policy_default_values(self):
        invalidate_config_caches()
        s = Settings()
        policy = s.get_routing_policy()
        assert policy["intent_router_enabled"] is True
        assert policy["intent_router_mode"] == "llm"
        assert policy["tree_enabled"] is True
        assert policy["debug_headers_enabled"] is False

    def test_intent_router_env_override(self):
        invalidate_config_caches()
        s = Settings(ainstein_intent_router=True, ainstein_intent_router_mode="llm")
        policy = s.get_routing_policy()
        assert policy["intent_router_enabled"] is True
        assert policy["intent_router_mode"] == "llm"


class TestIntentRouterRouting:
    """Intent router classifies queries correctly."""

    def test_comparative_routes_to_compare_concepts(self):
        from src.intent_router import heuristic_classify, Intent

        d = heuristic_classify("What's the difference between an ADR and a PCP?")
        assert d.intent == Intent.COMPARE_CONCEPTS

    def test_count_comparison_routes_to_compare_counts(self):
        from src.intent_router import heuristic_classify, Intent

        d = heuristic_classify("Do we have more DARs for ADRs than PCPs?")
        assert d.intent == Intent.COMPARE_COUNTS

    def test_semantic_question_routes_to_semantic_answer(self):
        from src.intent_router import heuristic_classify, Intent

        d = heuristic_classify("What architecture decisions affect API design?")
        assert d.intent == Intent.SEMANTIC_ANSWER

    def test_list_adrs_routes_to_list(self):
        from src.intent_router import heuristic_classify, Intent

        d = heuristic_classify("List all ADRs")
        assert d.intent == Intent.LIST


class TestAbstainGateToggle:
    """Abstain gate can be disabled safely."""

    def test_abstain_gate_flag_exists(self):
        invalidate_config_caches()
        s = Settings()
        policy = s.get_routing_policy()
        assert "abstain_gate_enabled" in policy
        assert isinstance(policy["abstain_gate_enabled"], bool)

    def test_abstain_gate_default_is_false(self):
        invalidate_config_caches()
        s = Settings()
        policy = s.get_routing_policy()
        assert policy["abstain_gate_enabled"] is False


class TestDebugHeadersFlag:
    """Debug headers can be enabled for dev environments."""

    def test_debug_headers_default_off(self):
        invalidate_config_caches()
        s = Settings()
        policy = s.get_routing_policy()
        assert policy["debug_headers_enabled"] is False

    def test_debug_headers_env_override(self):
        invalidate_config_caches()
        s = Settings(ainstein_debug_headers=True)
        policy = s.get_routing_policy()
        assert policy["debug_headers_enabled"] is True


class TestDebugFooter:
    """_maybe_add_debug_footer appends routing info when enabled."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_weaviate(self):
        """Skip these tests if weaviate is not installed (CI/lightweight env)."""
        pytest.importorskip("weaviate", reason="weaviate not installed")

    def test_footer_added_when_enabled(self):
        from src.elysia_agents import _maybe_add_debug_footer
        route_log = {
            "route_selected": "compare_concepts",
            "intent": "compare_concepts",
            "confidence": 0.88,
            "collections_queried": ["adr", "principle"],
        }
        result = _maybe_add_debug_footer("Hello", route_log, True)
        assert "route: compare_concepts" in result
        assert "intent_confidence: 0.88" in result

    def test_footer_not_added_when_disabled(self):
        from src.elysia_agents import _maybe_add_debug_footer
        route_log = {"route_selected": "list"}
        result = _maybe_add_debug_footer("Hello", route_log, False)
        assert result == "Hello"

    def test_footer_not_added_for_non_string(self):
        from src.elysia_agents import _maybe_add_debug_footer
        route_log = {"route_selected": "list"}
        result = _maybe_add_debug_footer(42, route_log, True)
        assert result == 42


class TestEmbedModeFlag:
    """Embed mode flag for chunking experiments."""

    def test_embed_mode_default_none(self):
        s = Settings()
        assert s.ainstein_embed_mode is None

    def test_embed_mode_override(self):
        s = Settings(ainstein_embed_mode="full")
        assert s.ainstein_embed_mode == "full"
