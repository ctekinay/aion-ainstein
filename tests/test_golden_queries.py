"""Layer 1: Golden Query Tests — parametrized pytest wrapper.

Wraps the 25 gold standard questions from test_runner.py in pytest
with keyword scoring, abstention detection, and hallucination checks.

Requires Weaviate + Ollama (or OpenAI). Skips if services unavailable.
Run with: pytest -m functional tests/test_golden_queries.py

For parallel execution of stateless queries:
    pytest -m functional tests/test_golden_queries.py -n4
"""

import asyncio
import os

import pytest

from aion.evaluation.test_runner import (
    TEST_QUESTIONS,
    calculate_keyword_score,
    check_no_answer,
    detect_hallucination,
    init_rag_system,
    query_rag,
    suppress_output,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Minimum keyword score for a passing test (per category)
CATEGORY_THRESHOLDS = {
    "Vocabulary": 0.5,
    "ADR": 0.5,
    "Principle": 0.5,
    "Policy": 0.4,
    "Cross-Domain": 0.3,
    "Comparative": 0.3,
    "Temporal": 0.3,
    "Disambiguation": 0.5,
    "Negative": 1.0,  # Must correctly abstain
}

# Latency limits (ms)
LATENCY_LIMITS = {
    "ollama": 30_000,
    "openai": 15_000,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rag_system():
    """Initialize RAG system once per module."""
    provider = os.environ.get("RAG_PROVIDER", "ollama")
    model = os.environ.get("FAST_MODEL")

    loop = asyncio.new_event_loop()
    success = loop.run_until_complete(init_rag_system(provider=provider, model=model))
    if not success:
        pytest.skip("Could not initialize RAG system")
    yield provider
    loop.close()


def _run_query(question: str) -> dict:
    """Run a single query against the RAG system."""
    loop = asyncio.new_event_loop()
    try:
        with suppress_output():
            return loop.run_until_complete(query_rag(question))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Parametrized test IDs
# ---------------------------------------------------------------------------

_test_ids = [q["id"] for q in TEST_QUESTIONS]
_negative_ids = {q["id"] for q in TEST_QUESTIONS if q.get("expect_no_answer")}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.functional
class TestGoldenQueries:
    """Validates RAG system answers against 25 gold standard questions."""

    @pytest.mark.parametrize(
        "question",
        [q for q in TEST_QUESTIONS if not q.get("expect_no_answer")],
        ids=[q["id"] for q in TEST_QUESTIONS if not q.get("expect_no_answer")],
    )
    def test_retrieval_keyword_score(self, rag_system, question):
        """Response contains expected keywords above category threshold."""
        result = _run_query(question["question"])

        assert not result.get("error"), f"Query failed: {result['error']}"

        score = calculate_keyword_score(result["response"], question["expected_keywords"])
        threshold = CATEGORY_THRESHOLDS.get(question["category"], 0.4)

        assert score >= threshold, (
            f"[{question['id']}] Keyword score {score:.2f} < {threshold:.2f}. "
            f"Missing keywords from: {question['expected_keywords']}"
        )

    @pytest.mark.parametrize(
        "question",
        [q for q in TEST_QUESTIONS if q.get("expect_no_answer")],
        ids=[q["id"] for q in TEST_QUESTIONS if q.get("expect_no_answer")],
    )
    def test_negative_abstention(self, rag_system, question):
        """System correctly abstains on questions about non-existent content."""
        result = _run_query(question["question"])

        assert not result.get("error"), f"Query failed: {result['error']}"
        assert check_no_answer(result["response"]), (
            f"[{question['id']}] Expected abstention but got substantive response: "
            f"{result['response'][:200]}..."
        )

    @pytest.mark.parametrize(
        "question",
        [q for q in TEST_QUESTIONS if not q.get("expect_no_answer")],
        ids=[q["id"] for q in TEST_QUESTIONS if not q.get("expect_no_answer")],
    )
    def test_no_hallucination(self, rag_system, question):
        """Response doesn't reference unsupported sources."""
        result = _run_query(question["question"])

        if result.get("error"):
            pytest.skip(f"Query failed: {result['error']}")

        hallucination = detect_hallucination(
            result["response"],
            result.get("sources", []),
            question["id"],
        )
        assert not hallucination["is_hallucination"], (
            f"[{question['id']}] Hallucination detected: {hallucination['issues']}"
        )

    @pytest.mark.parametrize(
        "question",
        TEST_QUESTIONS,
        ids=[q["id"] for q in TEST_QUESTIONS],
    )
    def test_latency_within_budget(self, rag_system, question):
        """Response time within acceptable budget for the provider."""
        result = _run_query(question["question"])

        if result.get("error"):
            pytest.skip(f"Query failed: {result['error']}")

        limit = LATENCY_LIMITS.get(rag_system, 30_000)
        assert result["latency_ms"] < limit, (
            f"[{question['id']}] Latency {result['latency_ms']}ms > {limit}ms limit"
        )
