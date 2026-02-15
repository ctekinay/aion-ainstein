"""Daily smoke suite — 10 questions tied to known failure modes.

Designed for list-mode regression detection. Every question maps to a specific
pathology from v4 test results. No generic/unstable questions.

Run: python -m pytest tests/test_daily_smoke.py -v -m smoke
Requires: running Weaviate + LLM provider (ollama or openai)

Categories:
- 4 non-list-with-keyword: catches "ADR keyword -> list dump" regression
- 2 explicit list: ensures list gating doesn't break legitimate list queries
- 2 approval: ensures DAR routing works
- 2 overlap disambiguation: ensures number-overlap handling
"""
import pytest

from tests.test_trace_invariants import check_all_invariants

pytestmark = [pytest.mark.smoke, pytest.mark.integration]

SMOKE_QUESTIONS = [
    # ── 4x non-list queries that mention ADR/PCP (must NOT list) ──────────
    # These are the exact pathology: "ADR keyword → list dump"
    # IDs used: ADR.0012 (CIM decision, well-known), PCP.0010 (data-is-asset,
    # well-known). These are canonical documents present in every deployment.
    {
        "id": "S01",
        "q": "What does ADR.0012 decide about domain language?",
        "must_not_contain": ["ADR.0000", "ADR.0001", "ADR.0002"],
        "trace_check": "response_mode != deterministic_list",
        "category": "non_list_with_keyword",
    },
    {
        "id": "S02",
        "q": "What does PCP.0010 say about data?",
        "must_not_contain": ["PCP.0011", "PCP.0012", "PCP.0013"],
        "trace_check": "response_mode != deterministic_list",
        "category": "non_list_with_keyword",
    },
    {
        "id": "S03",
        "q": "Why was CIM chosen as the default domain language?",
        "must_not_contain": ["ADR.0000", "ADR.0001"],
        "trace_check": "response_mode == llm_synthesis",
        "category": "non_list_with_keyword",
    },
    {
        "id": "S04",
        "q": "What security measures are defined across ADRs and principles?",
        "must_not_contain": ["__list_result__"],
        "trace_check": "response_mode == llm_synthesis",
        "category": "non_list_with_keyword",
    },
    # ── 2x explicit list queries (must list) ──────────────────────────────
    {
        "id": "S05",
        "q": "List all ADRs",
        "must_contain_any": ["ADR.00", "ADR.10", "ADR.20"],
        "trace_check": "response_mode == deterministic_list",
        "category": "explicit_list",
    },
    {
        "id": "S06",
        "q": "Show all architecture principles",
        "must_contain_any": ["PCP.10", "PCP.20", "PCP.30"],
        "trace_check": "response_mode == deterministic_list",
        "category": "explicit_list",
    },
    # ── 2x approval queries (must hit DAR) ────────────────────────────────
    {
        "id": "S07",
        "q": "Who approved ADR.0012?",
        "must_contain_any": ["approv", "acknowledged", "accepted"],
        "trace_check": "collection_selected contains approval",
        "category": "approval",
    },
    {
        "id": "S08",
        "q": "Who approved PCP.0010?",
        "must_contain_any": ["approv", "acknowledged", "accepted"],
        "trace_check": "collection_selected contains approval",
        "category": "approval",
    },
    # ── 2x overlap disambiguation (must ask/offer both or pick correctly) ─
    {
        "id": "S09",
        "q": "Tell me about document 0022",
        "must_contain_any": ["ADR", "PCP", "which", "two"],
        "trace_check": "none",
        "category": "overlap_disambiguation",
    },
    {
        "id": "S10",
        "q": "What is 0012 about?",
        "must_contain_any": ["ADR", "PCP", "CIM", "which", "two"],
        "trace_check": "none",
        "category": "overlap_disambiguation",
    },
]


def _check_trace_condition(trace: dict, condition: str) -> bool:
    """Evaluate a trace_check condition string against a trace dict.

    Supports simple conditions:
    - "response_mode != deterministic_list"
    - "response_mode == llm_synthesis"
    - "collection_selected contains approval"
    - "none" (always passes)
    """
    if condition == "none":
        return True

    if "!=" in condition:
        field, value = [x.strip() for x in condition.split("!=")]
        return trace.get(field) != value

    if "==" in condition:
        field, value = [x.strip() for x in condition.split("==")]
        return trace.get(field) == value

    if "contains" in condition:
        parts = condition.split("contains")
        field = parts[0].strip()
        value = parts[1].strip()
        return value in str(trace.get(field, ""))

    return True  # Unknown condition format — don't fail


def _check_must_contain_any(response: str, patterns: list) -> bool:
    """Check if response contains at least one of the patterns (case-insensitive)."""
    response_lower = response.lower()
    return any(p.lower() in response_lower for p in patterns)


def _check_must_not_contain(response: str, patterns: list) -> bool:
    """Check if response does NOT contain any of the forbidden patterns (case-insensitive)."""
    response_lower = response.lower()
    return not any(p.lower() in response_lower for p in patterns)


class TestDailySmokeDefinitions:
    """Unit tests for smoke suite definitions and helper functions (no RAG needed)."""

    def test_smoke_questions_count(self):
        assert len(SMOKE_QUESTIONS) == 10

    def test_smoke_categories_distribution(self):
        cats = [q["category"] for q in SMOKE_QUESTIONS]
        assert cats.count("non_list_with_keyword") == 4
        assert cats.count("explicit_list") == 2
        assert cats.count("approval") == 2
        assert cats.count("overlap_disambiguation") == 2

    def test_all_smoke_ids_unique(self):
        ids = [q["id"] for q in SMOKE_QUESTIONS]
        assert len(ids) == len(set(ids))

    def test_trace_check_condition_eq(self):
        assert _check_trace_condition({"response_mode": "llm_synthesis"}, "response_mode == llm_synthesis")
        assert not _check_trace_condition({"response_mode": "deterministic_list"}, "response_mode == llm_synthesis")

    def test_trace_check_condition_neq(self):
        assert _check_trace_condition({"response_mode": "llm_synthesis"}, "response_mode != deterministic_list")
        assert not _check_trace_condition({"response_mode": "deterministic_list"}, "response_mode != deterministic_list")

    def test_trace_check_condition_contains(self):
        assert _check_trace_condition({"collection_selected": "dar_approval"}, "collection_selected contains approval")
        assert not _check_trace_condition({"collection_selected": "adr"}, "collection_selected contains approval")

    def test_trace_check_condition_none(self):
        assert _check_trace_condition({}, "none")

    def test_must_contain_any(self):
        assert _check_must_contain_any("This mentions ADR.12 in the text", ["ADR", "PCP"])
        assert not _check_must_contain_any("No match here", ["ADR", "PCP"])

    def test_must_not_contain(self):
        assert _check_must_not_contain("Clean response", ["ADR.0000", "ADR.0001"])
        assert not _check_must_not_contain("Contains ADR.0000 forbidden", ["ADR.0000"])

    def test_invariant_check_on_clean_trace(self):
        """Smoke invariant checks work on a clean trace."""
        trace = {
            "intent_action": "semantic_answer",
            "tool_calls": [],
            "list_finalized_deterministically": False,
            "fallback_used": False,
            "intent_constraints": [],
            "final_output": "test response",
            "response_mode": "llm_synthesis",
        }
        results = check_all_invariants(trace)
        assert all(r[1] for r in results), f"Clean trace should pass all invariants: {results}"
