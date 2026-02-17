"""Parallel-run parity test — old scoring gate vs new embedding classifier.

Runs both routers on a gold query set and compares their intent decisions.
Disagreements are logged for analysis. The test passes if disagreements are
within an expected exceptions list.

This is a TRANSITIONAL test — delete in Week 3 when the old router is removed.

Uses fake embeddings (hermetic) to validate classification logic without Ollama.
"""

import pytest

from src.agents.architecture_agent import (
    _extract_signals,
    _score_intents,
    _select_winner,
)
from src.classifiers.embedding_classifier import EmbeddingClassifier


# =============================================================================
# Fake embeddings — deterministic intent-aligned vectors
# =============================================================================

# 8D orthogonal-ish unit vectors per intent
_INTENT_VECTORS = {
    "list":            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "count":           [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "lookup_doc":      [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "semantic_answer": [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0],
    "compare":         [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
    "conversational":  [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
}


# Gold queries mapped to their expected embedding vector.
# This simulates what real Ollama embeddings would produce for these queries.
_GOLD_QUERY_VECTORS: dict[str, str] = {
    # List queries
    "List all ADRs": "list",
    "Show me all decisions": "list",
    "Enumerate all principles": "list",
    "What ADRs exist?": "list",
    # Count queries
    "How many ADRs are there?": "count",
    "Total count of decisions": "count",
    "Count of principles": "count",
    # Lookup queries
    "What does ADR.0012 decide?": "lookup_doc",
    "Show me ADR 12 decision": "lookup_doc",
    "Tell me about ADR.12": "lookup_doc",
    "Quote ADR.12": "lookup_doc",
    # Semantic queries
    "What principles do we have about interoperability?": "semantic_answer",
    "Summarize our approach to CIM adoption": "semantic_answer",
    "What security patterns are used?": "semantic_answer",
    "List principles on interoperability": "semantic_answer",
    "What are the ESA architecture principles?": "semantic_answer",
    # Compare queries
    "Compare ADR.12 and ADR.13": "compare",
    "I would like to see the connection between ADR.12 and PCP.12": "compare",
    "What's the difference between 22 and 12?": "compare",
    "Differences between ADR.12 and PCP.22": "compare",
    # Conversational queries
    "My cat sat on ADR.12": "conversational",
    "I wish I had written ADR.12": "conversational",
    "ADR.12 reminds me of my college days": "conversational",
    "I like ADR.12": "conversational",
}


def _fake_embed(text: str) -> list[float]:
    """Map gold queries to intent-aligned vectors."""
    intent = _GOLD_QUERY_VECTORS.get(text)
    if intent:
        return list(_INTENT_VECTORS[intent])
    # Unknown: weak conversational direction
    return [0.05, 0.05, 0.05, 0.05, 0.05, 0.1, 0.0, 0.0]


def _fake_embed_batch(texts: list[str]) -> list[list[float]]:
    return [_fake_embed(t) for t in texts]


# Prototype bank — must include all gold queries so centroids align
_PROTOTYPES = {
    "list": [
        "List all ADRs", "Show me all decisions", "Enumerate all principles",
        "What ADRs exist?", "Which decisions do we have?",
        "Show all policies", "Give me every ADR",
        "What principles are defined?", "Show me every principle",
        "What decisions exist?",
    ],
    "count": [
        "How many ADRs are there?", "Total count of decisions",
        "Count of principles", "How many principles do we have?",
        "Number of ADRs", "How many policies exist?",
        "Total number of principles", "How many policies are there?",
        "Count the decisions", "How many DARs exist?",
    ],
    "lookup_doc": [
        "What does ADR.0012 decide?", "ADR-12 quote the decision",
        "Show me ADR 12 decision", "Show PCP.22 decision",
        "PCP.22 what does it state?", "Tell me about ADR.12",
        "Give me ADR.12", "What does 0022 decide?",
        "Show me document 22", "What does 22 decide?",
        "Quote ADR.12", "Decision drivers of ADR.12",
    ],
    "semantic_answer": [
        "What principles do we have about interoperability?",
        "Summarize our approach to CIM adoption",
        "What security patterns are used?",
        "Describe the deployment strategy",
        "Explain the data governance model",
        "What conventions do we use for ADRs?",
        "List all principles about interoperability",
        "List ADRs regarding security",
        "List principles related to CIM",
        "List principles on interoperability",
        "Show ADRs about data governance",
        "How do we handle semantic interoperability in ESA?",
        "What are the ESA architecture principles?",
    ],
    "compare": [
        "Compare 22 and ADR.12", "Compare ADR.12 and ADR.13",
        "What's the difference between 22 and 12?",
        "How does PCP.01 relate to ADR.05?",
        "Differences between ADR.12 and PCP.22",
        "ADR.12 versus PCP.22", "ADR.12 vs ADR.13",
        "I would like to see the connection between ADR.12 and PCP.12",
        "How are ADR.12 and PCP.12 related?",
        "What links ADR.12 to PCP.12?",
        "What's the overlap between ADR.12 and PCP.12?",
    ],
    "conversational": [
        "I wish I had written ADR.12",
        "ADR.12 reminds me of my college days",
        "ADR.12 is the bane of my existence",
        "My cat sat on ADR.12",
        "ADR.25 walks into a bar",
        "Is ADR.12 even real",
        "ADR.12 spaghetti carbonara recipe",
        "I named my dog ADR.5",
        "Someone told me about ADR.5",
        "I like ADR.12",
        "ADRs are boring documents",
    ],
}


@pytest.fixture(scope="module")
def classifier():
    """Create classifier with fake embeddings (reused across all tests)."""
    return EmbeddingClassifier(
        embed_fn=_fake_embed,
        embed_batch_fn=_fake_embed_batch,
        prototypes=_PROTOTYPES,
    )


def _get_old_router_intent(query: str) -> str:
    """Run old scoring gate and return winning intent."""
    signals = _extract_signals(query)
    scores = _score_intents(signals)
    winner, threshold_met, margin_ok = _select_winner(scores)

    if threshold_met and margin_ok and winner:
        return winner

    # Fallback paths
    if signals.has_doc_ref and not signals.has_retrieval_verb:
        return "conversational"
    return "semantic_answer"  # default fallback


# =============================================================================
# Known exceptions: queries where we EXPECT the classifier to disagree
# because the old router is WRONG (that's why we're replacing it)
# =============================================================================

_KNOWN_EXCEPTIONS: dict[str, tuple[str, str]] = {
    # Old router has no "compare" intent — routes doc-ref comparisons to lookup_doc
    # (has_retrieval_verb=True because "compare"/"connection"/"between" are retrieval verbs).
    # The classifier correctly identifies these as compare intent.
    "Compare ADR.12 and ADR.13": ("lookup_doc", "compare"),
    "I would like to see the connection between ADR.12 and PCP.12": ("lookup_doc", "compare"),
    "Differences between ADR.12 and PCP.22": ("lookup_doc", "compare"),
    # Bare-number compare: old router sees retrieval verb + no doc ref → semantic_answer
    "What's the difference between 22 and 12?": ("semantic_answer", "compare"),
}


# =============================================================================
# Tests
# =============================================================================

class TestParallelRunParity:
    """Compare old scoring gate vs new embedding classifier on gold queries."""

    @pytest.mark.parametrize("query,expected_classifier_intent", list(_GOLD_QUERY_VECTORS.items()))
    def test_classifier_intent(self, classifier, query, expected_classifier_intent):
        """Verify the classifier produces the expected intent."""
        result = classifier.classify(query)
        assert result.intent == expected_classifier_intent, (
            f"Classifier mismatch for '{query}': "
            f"expected {expected_classifier_intent}, got {result.intent}"
        )

    @pytest.mark.parametrize("query,expected_classifier_intent", list(_GOLD_QUERY_VECTORS.items()))
    def test_parity_or_known_exception(self, classifier, query, expected_classifier_intent):
        """Old and new routers agree, or disagreement is in the known exceptions list."""
        old_intent = _get_old_router_intent(query)
        new_intent = classifier.classify(query).intent

        if old_intent == new_intent:
            return  # Agreement — pass

        # Disagreement — must be a known exception
        assert query in _KNOWN_EXCEPTIONS, (
            f"UNEXPECTED DISAGREEMENT for '{query}':\n"
            f"  Old router: {old_intent}\n"
            f"  Classifier: {new_intent}\n"
            f"  Add to _KNOWN_EXCEPTIONS if this is expected."
        )
        expected_old, expected_new = _KNOWN_EXCEPTIONS[query]
        assert old_intent == expected_old, (
            f"Known exception mismatch for '{query}': "
            f"expected old={expected_old}, got old={old_intent}"
        )
        assert new_intent == expected_new, (
            f"Known exception mismatch for '{query}': "
            f"expected new={expected_new}, got new={new_intent}"
        )


class TestParityStats:
    """Summary statistics for parity analysis."""

    def test_disagreement_count(self, classifier):
        """Count total disagreements and verify <= threshold."""
        disagreements = []
        for query, expected in _GOLD_QUERY_VECTORS.items():
            old = _get_old_router_intent(query)
            new = classifier.classify(query).intent
            if old != new:
                disagreements.append((query, old, new))

        # All disagreements should be in the known exceptions list
        unexpected = [
            (q, old, new) for q, old, new in disagreements
            if q not in _KNOWN_EXCEPTIONS
        ]
        assert len(unexpected) == 0, (
            f"{len(unexpected)} unexpected disagreements:\n"
            + "\n".join(f"  '{q}': old={old}, new={new}" for q, old, new in unexpected)
        )

        # Informational: log disagreement rate
        total = len(_GOLD_QUERY_VECTORS)
        rate = len(disagreements) / total * 100
        print(f"\nParity: {total - len(disagreements)}/{total} agree ({rate:.0f}% disagree)")
        print(f"Known exceptions: {len(disagreements)}")
        for q, old, new in disagreements:
            print(f"  '{q}': old={old} → new={new}")
