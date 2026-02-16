"""
Failure analysis tools for identifying and categorizing retrieval failures.
"""

from typing import List, Dict, Set
from dataclasses import dataclass
from collections import defaultdict
import json


@dataclass
class FailureCase:
    query_id: str
    query: str
    category: str
    failure_type: str
    expected_docs: List[str]
    retrieved_docs: List[str]
    confidence: float
    notes: str


def classify_failure(result: Dict) -> str:
    """
    Classify the type of failure.

    Failure types:
    - "complete_miss": No relevant documents in top 10
    - "partial_miss": Some relevant documents missing from top 10
    - "ranking_error": Relevant documents present but poorly ranked
    - "type_misclassification": Query type incorrectly detected
    - "low_confidence": Good results but low confidence score
    - "false_positive": Irrelevant documents ranked highly
    """
    relevant = set(result.get("relevant_ids", []))
    retrieved = result.get("retrieved_ids", [])[:10]
    retrieved_set = set(retrieved)

    if not relevant:
        return "no_ground_truth"

    hits = retrieved_set & relevant

    if len(hits) == 0:
        return "complete_miss"

    if len(hits) < len(relevant):
        # Check if missing docs are just ranked lower
        all_retrieved = set(result.get("retrieved_ids", []))
        if relevant.issubset(all_retrieved):
            return "ranking_error"
        return "partial_miss"

    # Check ranking quality
    first_relevant_rank = None
    for i, doc_id in enumerate(retrieved):
        if doc_id in relevant:
            first_relevant_rank = i
            break

    if first_relevant_rank and first_relevant_rank > 2:
        return "ranking_error"

    # Check query type
    if result.get("expected_query_type") != result.get("detected_query_type"):
        return "type_misclassification"

    # Check confidence
    if result.get("confidence", 1.0) < 0.4:
        return "low_confidence"

    return "success"


def analyze_failures(results: List[Dict], threshold_recall: float = 0.8) -> Dict:
    """
    Analyze failures across all results.

    Returns breakdown of failure types and problematic queries.
    """
    failure_counts = defaultdict(int)
    failure_cases = defaultdict(list)

    for result in results:
        failure_type = classify_failure(result)
        failure_counts[failure_type] += 1

        if failure_type != "success":
            failure_cases[failure_type].append(
                {
                    "query_id": result["query_id"],
                    "query": result["query"],
                    "category": result.get("category"),
                    "relevant_ids": result.get("relevant_ids", []),
                    "retrieved_ids": result.get("retrieved_ids", [])[:10],
                    "confidence": result.get("confidence"),
                    "detected_type": result.get("detected_query_type"),
                    "expected_type": result.get("expected_query_type"),
                }
            )

    return {
        "total_queries": len(results),
        "failure_counts": dict(failure_counts),
        "failure_rate": 1 - (failure_counts["success"] / len(results)) if results else 0,
        "failure_cases": dict(failure_cases),
    }


def generate_failure_report(analysis: Dict) -> str:
    """Generate a human-readable failure report."""
    lines = []
    lines.append("=" * 60)
    lines.append(" FAILURE ANALYSIS REPORT")
    lines.append("=" * 60)

    lines.append(f"\nTotal Queries: {analysis['total_queries']}")
    lines.append(f"Overall Failure Rate: {analysis['failure_rate']:.1%}")

    lines.append("\n FAILURE BREAKDOWN:")
    for failure_type, count in sorted(analysis["failure_counts"].items()):
        pct = count / analysis["total_queries"] * 100
        lines.append(f"   {failure_type}: {count} ({pct:.1f}%)")

    lines.append("\n SAMPLE FAILURES BY TYPE:")
    for failure_type, cases in analysis["failure_cases"].items():
        lines.append(f"\n  [{failure_type}]")
        for case in cases[:3]:  # Show top 3 examples
            lines.append(f"    Query: {case['query'][:50]}...")
            lines.append(f"    Category: {case['category']}")
            lines.append(f"    Expected: {case['relevant_ids'][:3]}")
            lines.append(f"    Retrieved: {case['retrieved_ids'][:3]}")
            lines.append("")

    return "\n".join(lines)


def suggest_improvements(analysis: Dict) -> List[str]:
    """Suggest improvements based on failure analysis."""
    suggestions = []

    counts = analysis["failure_counts"]
    total = analysis["total_queries"]

    # Complete misses
    if counts.get("complete_miss", 0) / total > 0.1:
        suggestions.append(
            "HIGH COMPLETE MISS RATE: Consider:\n"
            "  - Reviewing chunking strategy (chunks may be too small/large)\n"
            "  - Checking embedding model quality for your domain\n"
            "  - Adjusting alpha toward more lexical search (lower alpha)"
        )

    # Ranking errors
    if counts.get("ranking_error", 0) / total > 0.15:
        suggestions.append(
            "HIGH RANKING ERROR RATE: Consider:\n"
            "  - Adding a reranker (cross-encoder)\n"
            "  - Tuning alpha per query type\n"
            "  - Improving chunk context (add more document metadata)"
        )

    # Type misclassification
    if counts.get("type_misclassification", 0) / total > 0.1:
        suggestions.append(
            "HIGH TYPE MISCLASSIFICATION: Consider:\n"
            "  - Expanding semantic trigger terms in config\n"
            "  - Adjusting query type detection heuristics\n"
            "  - Adding more domain-specific patterns"
        )

    # Low confidence
    if counts.get("low_confidence", 0) / total > 0.2:
        suggestions.append(
            "HIGH LOW CONFIDENCE RATE: Consider:\n"
            "  - Reviewing embedding model fit for your content\n"
            "  - Checking chunk quality (contextual prefixes)\n"
            "  - Adjusting confidence threshold"
        )

    if not suggestions:
        suggestions.append("No major issues detected. Consider fine-tuning for edge cases.")

    return suggestions
