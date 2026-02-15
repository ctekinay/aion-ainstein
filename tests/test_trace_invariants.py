"""CI audit gates — hard invariants on QueryTrace objects.

These prevent the 'regex trap' regression: non-list queries must never
end up in deterministic list finalization.

Also includes TraceStore tests for request-scoped storage, eviction,
and concurrent trace isolation.
"""
import re
import time
from unittest.mock import patch

import pytest


def _is_list_tool(tc: dict) -> bool:
    """Check if a tool call is a list tool (by kind or name/shape fallback)."""
    if tc.get("tool_kind") == "list":
        return True
    if tc.get("result_shape") == "list_all":
        return True
    if tc.get("tool", "").startswith("list_"):
        return True
    return False


def check_invariant_a(trace: dict) -> tuple[bool, str]:
    """Invariant A: list tool → intent must be 'list' (Intent.LIST)."""
    list_tools = [tc for tc in trace.get("tool_calls", []) if _is_list_tool(tc)]
    if list_tools and trace.get("intent_action") != "list":
        return False, f"list tool used but intent={trace.get('intent_action')}"
    return True, ""


def check_invariant_b(trace: dict) -> tuple[bool, str]:
    """Invariant B: deterministic list finalization → intent must be 'list' (Intent.LIST)."""
    if trace.get("list_finalized_deterministically") and trace.get("intent_action") != "list":
        return False, f"list finalized deterministically but intent={trace.get('intent_action')}"
    return True, ""


def check_invariant_c(trace: dict) -> tuple[bool, str]:
    """Invariant C: fallback must not produce list tools."""
    if trace.get("fallback_used"):
        list_tools = [tc for tc in trace.get("tool_calls", []) if _is_list_tool(tc)]
        if list_tools:
            return False, f"fallback used list tool: {list_tools}"
    return True, ""


def check_invariant_d(trace: dict) -> tuple[bool, str]:
    """Invariant D: id_only constraint → output is single resolved canonical token.

    Accepts messy-repo variants: ADR.12, ADR.0012, PCP.22, PCP.0022D, ADR.0025D.
    Does NOT use 'DAR.' prefix — DARs are ADR.####D or PCP.####D in this ontology.
    If resolved_id is available in trace (from retrieval), verifies exact match.
    Falls back to pattern-only check. Case-insensitive.
    """
    if "id_only" in trace.get("intent_constraints", []):
        output = trace.get("final_output", "").strip().upper()
        # If trace has a resolved_id from retrieval, prefer exact match
        resolved = trace.get("resolved_id", "").strip().upper()
        if resolved and output == resolved:
            return True, ""
        if not re.match(r'^(ADR|PCP)\.\d{1,4}D?$', output):
            return False, f"id_only constraint but output is: {trace.get('final_output', '')[:100]}"
    return True, ""


def check_invariant_e(trace: dict) -> tuple[bool, str]:
    """Invariant E: response_mode == deterministic_list implies intent is list.

    Catches cases where list finalization happens but list_finalized_deterministically
    wasn't set due to a bug. Uses response_mode as the single truth field.
    """
    if trace.get("response_mode") == "deterministic_list" and trace.get("intent_action") != "list":
        return False, f"response_mode=deterministic_list but intent={trace.get('intent_action')}"
    return True, ""


def check_all_invariants(trace: dict) -> list[tuple[str, bool, str]]:
    """Run all invariants, return list of (name, passed, message)."""
    results = []
    for name, fn in [("A", check_invariant_a), ("B", check_invariant_b),
                      ("C", check_invariant_c), ("D", check_invariant_d),
                      ("E", check_invariant_e)]:
        passed, msg = fn(trace)
        results.append((name, passed, msg))
    return results


class TestTraceInvariantsUnit:
    """Unit tests for invariant checking functions (no RAG system needed)."""

    def test_invariant_a_passes_for_list_intent(self):
        trace = {"intent_action": "list", "tool_calls": [{"tool": "list_all_adrs", "tool_kind": "list", "result_shape": "list_all"}]}
        ok, _ = check_invariant_a(trace)
        assert ok

    def test_invariant_a_fails_for_non_list_intent(self):
        trace = {"intent_action": "semantic_answer", "tool_calls": [{"tool": "list_all_adrs", "tool_kind": "list", "result_shape": "list_all"}]}
        ok, msg = check_invariant_a(trace)
        assert not ok
        assert "list tool used" in msg

    def test_invariant_a_catches_list_tool_by_name_prefix(self):
        """Catches list tools even when tool_kind/result_shape not set."""
        trace = {"intent_action": "semantic_answer", "tool_calls": [{"tool": "list_approval_records"}]}
        ok, _ = check_invariant_a(trace)
        assert not ok

    def test_invariant_b_passes_when_not_finalized(self):
        trace = {"list_finalized_deterministically": False, "intent_action": "semantic_answer"}
        ok, _ = check_invariant_b(trace)
        assert ok

    def test_invariant_b_fails_for_non_list_finalization(self):
        trace = {"list_finalized_deterministically": True, "intent_action": "lookup_doc"}
        ok, msg = check_invariant_b(trace)
        assert not ok

    def test_invariant_c_passes_no_fallback(self):
        trace = {"fallback_used": False, "tool_calls": [{"tool": "list_all_adrs", "tool_kind": "list"}]}
        ok, _ = check_invariant_c(trace)
        assert ok

    def test_invariant_c_fails_fallback_with_list_tool(self):
        trace = {"fallback_used": True, "tool_calls": [{"tool": "list_all_adrs", "tool_kind": "list"}]}
        ok, msg = check_invariant_c(trace)
        assert not ok

    def test_invariant_d_passes_without_constraint(self):
        trace = {"intent_constraints": [], "final_output": "long text about stuff"}
        ok, _ = check_invariant_d(trace)
        assert ok

    def test_invariant_d_passes_for_canonical_id(self):
        trace = {"intent_constraints": ["id_only"], "final_output": "ADR.0025"}
        ok, _ = check_invariant_d(trace)
        assert ok

    def test_invariant_d_passes_for_dar_suffix(self):
        trace = {"intent_constraints": ["id_only"], "final_output": "PCP.0022D"}
        ok, _ = check_invariant_d(trace)
        assert ok

    def test_invariant_d_passes_for_short_id(self):
        trace = {"intent_constraints": ["id_only"], "final_output": "ADR.12"}
        ok, _ = check_invariant_d(trace)
        assert ok

    def test_invariant_d_fails_for_long_text(self):
        trace = {"intent_constraints": ["id_only"], "final_output": "The ADR.0025 document covers authentication"}
        ok, msg = check_invariant_d(trace)
        assert not ok
        assert "id_only constraint" in msg

    def test_invariant_d_passes_with_resolved_id_match(self):
        trace = {"intent_constraints": ["id_only"], "final_output": "ADR.0025", "resolved_id": "ADR.0025"}
        ok, _ = check_invariant_d(trace)
        assert ok

    def test_invariant_e_passes_for_list_mode_with_list_intent(self):
        trace = {"response_mode": "deterministic_list", "intent_action": "list"}
        ok, _ = check_invariant_e(trace)
        assert ok

    def test_invariant_e_fails_for_list_mode_with_non_list_intent(self):
        trace = {"response_mode": "deterministic_list", "intent_action": "semantic_answer"}
        ok, msg = check_invariant_e(trace)
        assert not ok
        assert "deterministic_list" in msg

    def test_invariant_e_passes_for_non_list_mode(self):
        trace = {"response_mode": "llm_synthesis", "intent_action": "semantic_answer"}
        ok, _ = check_invariant_e(trace)
        assert ok

    def test_all_invariants_returns_list(self):
        trace = {"intent_action": "semantic_answer", "tool_calls": [], "list_finalized_deterministically": False,
                 "fallback_used": False, "intent_constraints": [], "final_output": "test",
                 "response_mode": "llm_synthesis"}
        results = check_all_invariants(trace)
        assert len(results) == 5  # A, B, C, D, E
        assert all(r[1] for r in results)  # all pass

    def test_all_invariants_catches_violations(self):
        trace = {"intent_action": "semantic_answer",
                 "tool_calls": [{"tool": "list_all_adrs", "tool_kind": "list"}],
                 "list_finalized_deterministically": True,
                 "fallback_used": True,
                 "intent_constraints": [],
                 "final_output": "test",
                 "response_mode": "deterministic_list"}
        results = check_all_invariants(trace)
        # A fails (list tool, non-list intent), B fails (finalized, non-list),
        # C fails (fallback + list tool), E fails (deterministic_list, non-list)
        failures = [r for r in results if not r[1]]
        assert len(failures) == 4
        failed_names = {r[0] for r in failures}
        assert failed_names == {"A", "B", "C", "E"}


class TestTraceStore:
    """Tests for TraceStore: request-scoped storage with bounded eviction."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_elysia(self):
        """Skip if elysia_agents module unavailable."""
        pytest.importorskip("weaviate", reason="weaviate not installed")

    def _make_trace(self, request_id: str, intent: str = "semantic_answer") -> "QueryTrace":
        from src.elysia_agents import QueryTrace
        return QueryTrace(request_id=request_id, intent_action=intent)

    def _make_store(self, max_size: int = 10, ttl_seconds: float = 600.0):
        from src.elysia_agents import TraceStore
        return TraceStore(max_size=max_size, ttl_seconds=ttl_seconds)

    def test_store_and_retrieve(self):
        store = self._make_store()
        t = self._make_trace("req-001")
        store.store(t)
        assert store.get("req-001") is t

    def test_get_missing_returns_none(self):
        store = self._make_store()
        assert store.get("nonexistent") is None

    def test_max_size_eviction(self):
        """Oldest entries evicted when max_size exceeded."""
        store = self._make_store(max_size=3)
        for i in range(5):
            store.store(self._make_trace(f"req-{i:03d}"))
        assert len(store) == 3
        # Oldest two should be evicted
        assert store.get("req-000") is None
        assert store.get("req-001") is None
        # Newest three should remain
        assert store.get("req-002") is not None
        assert store.get("req-003") is not None
        assert store.get("req-004") is not None

    def test_ttl_eviction_on_get(self):
        """Expired entries return None on get."""
        store = self._make_store(ttl_seconds=0.05)
        store.store(self._make_trace("req-old"))
        time.sleep(0.06)
        assert store.get("req-old") is None

    def test_ttl_eviction_on_store(self):
        """Expired entries cleaned up during store."""
        store = self._make_store(ttl_seconds=0.05)
        store.store(self._make_trace("req-old"))
        time.sleep(0.06)
        store.store(self._make_trace("req-new"))
        assert len(store) == 1
        assert store.get("req-old") is None
        assert store.get("req-new") is not None

    def test_concurrent_trace_isolation(self):
        """Two traces with different request_ids are independently retrievable."""
        store = self._make_store()
        t1 = self._make_trace("req-aaa", intent="list")
        t2 = self._make_trace("req-bbb", intent="semantic_answer")
        store.store(t1)
        store.store(t2)
        retrieved_1 = store.get("req-aaa")
        retrieved_2 = store.get("req-bbb")
        assert retrieved_1 is t1
        assert retrieved_2 is t2
        assert retrieved_1.intent_action == "list"
        assert retrieved_2.intent_action == "semantic_answer"

    def test_overwrite_same_request_id(self):
        """Storing same request_id replaces the old trace."""
        store = self._make_store()
        t1 = self._make_trace("req-001", intent="list")
        t2 = self._make_trace("req-001", intent="semantic_answer")
        store.store(t1)
        store.store(t2)
        assert len(store) == 1
        assert store.get("req-001").intent_action == "semantic_answer"

    def test_empty_request_id_not_stored(self):
        """Traces with empty request_id are silently dropped."""
        store = self._make_store()
        store.store(self._make_trace(""))
        assert len(store) == 0

    def test_ttl_edge_just_before_expiry(self):
        """Entry just before TTL threshold is still retrievable."""
        store = self._make_store(ttl_seconds=0.10)
        store.store(self._make_trace("req-edge"))
        time.sleep(0.05)  # well under 0.10s
        assert store.get("req-edge") is not None

    def test_trace_fields_preserved(self):
        """All QueryTrace fields survive store/get roundtrip."""
        store = self._make_store()
        t = self._make_trace("req-full")
        t.intent_action = "lookup_doc"
        t.fallback_used = True
        t.fallback_reason = "timeout"
        t.response_mode = "llm_synthesis"
        t.collection_selected = "adr"
        t.primary_top_score = 0.85
        store.store(t)
        retrieved = store.get("req-full")
        d = retrieved.to_dict()
        assert d["request_id"] == "req-full"
        assert d["intent_action"] == "lookup_doc"
        assert d["fallback_used"] is True
        assert d["fallback_reason"] == "timeout"
        assert d["response_mode"] == "llm_synthesis"
        assert d["collection_selected"] == "adr"
        assert d["primary_top_score"] == 0.85
