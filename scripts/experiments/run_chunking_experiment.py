#!/usr/bin/env python3
"""Run chunking vs full-doc retrieval accuracy experiment.

Compares retrieval quality between:
  - Chunked collections (default): ArchitecturalDecision, Principle
  - Full-doc collections: ArchitecturalDecision_FULL, Principle_FULL

Outputs a markdown report to docs/experiments/chunking_vs_full.md

Usage:
    python scripts/experiments/run_chunking_experiment.py [--output PATH]
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# =============================================================================
# Gold Standard Test Queries (subset for experiment)
# =============================================================================

@dataclass
class TestQuery:
    """A test query with expected results."""
    question: str
    expected_doc_id: str       # e.g., "0025" for ADR.0025
    collection_type: str       # "adr" or "principle"
    category: str              # "exact", "semantic", "cross_reference"


EXPERIMENT_QUERIES = [
    TestQuery("What does ADR-0012 decide?", "0012", "adr", "exact"),
    TestQuery("What is the domain language decision?", "0012", "adr", "semantic"),
    TestQuery("OAuth decision for API authentication", "0029", "adr", "semantic"),
    TestQuery("Tell me about ADR.0025", "0025", "adr", "exact"),
    TestQuery("What decision was made about event-driven architecture?", "0030", "adr", "semantic"),
    TestQuery("API design principles", "0010", "principle", "semantic"),
    TestQuery("Security principles for ESA", "0003", "principle", "semantic"),
]


# =============================================================================
# Experiment Runner
# =============================================================================

@dataclass
class RetrievalResult:
    """Result of a single retrieval test."""
    query: str
    expected_doc_id: str
    strategy: str               # "chunked" or "full"
    found_in_top_k: bool
    rank: Optional[int]         # position in results (1-indexed), None if not found
    top_score: float
    latency_ms: float
    top_results: list = field(default_factory=list)  # [{title, score, doc_id}, ...]


@dataclass
class ExperimentReport:
    """Full experiment report."""
    timestamp: str
    chunked_results: list       # list of RetrievalResult
    full_results: list          # list of RetrievalResult
    chunked_precision_at_5: float
    full_precision_at_5: float
    chunked_avg_latency_ms: float
    full_avg_latency_ms: float


def run_retrieval_test(
    client,
    query: TestQuery,
    collection_name: str,
    strategy: str,
    k: int = 5,
) -> RetrievalResult:
    """Run a single retrieval test against a collection."""
    from src.weaviate.embeddings import embed_text
    from weaviate.classes.query import MetadataQuery

    collection = client.collections.get(collection_name)

    start = time.perf_counter()
    try:
        query_vector = embed_text(query.question)
        results = collection.query.hybrid(
            query=query.question,
            vector=query_vector,
            limit=k,
            alpha=settings.alpha_default,
            return_metadata=MetadataQuery(score=True),
        )
        latency_ms = (time.perf_counter() - start) * 1000
    except Exception as e:
        logger.error(f"Retrieval failed for '{query.question}' on {collection_name}: {e}")
        return RetrievalResult(
            query=query.question,
            expected_doc_id=query.expected_doc_id,
            strategy=strategy,
            found_in_top_k=False,
            rank=None,
            top_score=0.0,
            latency_ms=0.0,
        )

    # Check if expected doc is in top-k results
    top_results = []
    found_rank = None
    for i, obj in enumerate(results.objects):
        props = dict(obj.properties)
        score = obj.metadata.score if obj.metadata else 0.0
        doc_id = props.get("adr_number") or props.get("principle_number", "")
        title = props.get("title", "")

        top_results.append({
            "title": title,
            "score": float(score) if score else 0.0,
            "doc_id": doc_id,
        })

        if doc_id == query.expected_doc_id and found_rank is None:
            found_rank = i + 1

    top_score = top_results[0]["score"] if top_results else 0.0

    return RetrievalResult(
        query=query.question,
        expected_doc_id=query.expected_doc_id,
        strategy=strategy,
        found_in_top_k=found_rank is not None,
        rank=found_rank,
        top_score=top_score,
        latency_ms=latency_ms,
        top_results=top_results,
    )


def run_experiment(client, queries: list, k: int = 5) -> ExperimentReport:
    """Run the full chunking vs full-doc experiment."""
    from datetime import datetime

    chunked_results = []
    full_results = []

    # Collection name mapping
    chunked_collections = {"adr": "ArchitecturalDecision", "principle": "Principle"}
    full_collections = {"adr": "ArchitecturalDecision_FULL", "principle": "Principle_FULL"}

    for query in queries:
        # Test chunked
        chunked_collection = chunked_collections.get(query.collection_type)
        if chunked_collection and client.collections.exists(chunked_collection):
            result = run_retrieval_test(client, query, chunked_collection, "chunked", k)
            chunked_results.append(result)
            logger.info(
                f"[chunked] {query.question[:50]}... → "
                f"found={result.found_in_top_k}, rank={result.rank}, latency={result.latency_ms:.0f}ms"
            )

        # Test full-doc
        full_collection = full_collections.get(query.collection_type)
        if full_collection and client.collections.exists(full_collection):
            result = run_retrieval_test(client, query, full_collection, "full", k)
            full_results.append(result)
            logger.info(
                f"[full]    {query.question[:50]}... → "
                f"found={result.found_in_top_k}, rank={result.rank}, latency={result.latency_ms:.0f}ms"
            )

    # Compute metrics
    chunked_hits = sum(1 for r in chunked_results if r.found_in_top_k)
    full_hits = sum(1 for r in full_results if r.found_in_top_k)

    chunked_p_at_k = chunked_hits / len(chunked_results) if chunked_results else 0.0
    full_p_at_k = full_hits / len(full_results) if full_results else 0.0

    chunked_avg_latency = (
        sum(r.latency_ms for r in chunked_results) / len(chunked_results)
        if chunked_results else 0.0
    )
    full_avg_latency = (
        sum(r.latency_ms for r in full_results) / len(full_results)
        if full_results else 0.0
    )

    return ExperimentReport(
        timestamp=datetime.utcnow().isoformat(),
        chunked_results=[asdict(r) for r in chunked_results],
        full_results=[asdict(r) for r in full_results],
        chunked_precision_at_5=chunked_p_at_k,
        full_precision_at_5=full_p_at_k,
        chunked_avg_latency_ms=chunked_avg_latency,
        full_avg_latency_ms=full_avg_latency,
    )


def generate_markdown_report(report: ExperimentReport) -> str:
    """Generate a markdown report from experiment results."""
    lines = [
        "# Chunking vs Full-Doc Embedding Experiment",
        "",
        f"**Timestamp:** {report.timestamp}",
        "",
        "## Summary",
        "",
        "| Metric | Chunked | Full-Doc |",
        "|--------|---------|----------|",
        f"| Precision@5 | {report.chunked_precision_at_5:.2%} | {report.full_precision_at_5:.2%} |",
        f"| Avg Latency | {report.chunked_avg_latency_ms:.0f}ms | {report.full_avg_latency_ms:.0f}ms |",
        f"| Queries Tested | {len(report.chunked_results)} | {len(report.full_results)} |",
        "",
        "## Per-Query Results",
        "",
        "### Chunked Strategy",
        "",
        "| Query | Expected | Found | Rank | Score | Latency |",
        "|-------|----------|-------|------|-------|---------|",
    ]

    for r in report.chunked_results:
        found = "Yes" if r["found_in_top_k"] else "No"
        rank = str(r["rank"]) if r["rank"] else "-"
        lines.append(
            f"| {r['query'][:50]} | {r['expected_doc_id']} | {found} | {rank} | "
            f"{r['top_score']:.3f} | {r['latency_ms']:.0f}ms |"
        )

    lines.extend([
        "",
        "### Full-Doc Strategy",
        "",
        "| Query | Expected | Found | Rank | Score | Latency |",
        "|-------|----------|-------|------|-------|---------|",
    ])

    for r in report.full_results:
        found = "Yes" if r["found_in_top_k"] else "No"
        rank = str(r["rank"]) if r["rank"] else "-"
        lines.append(
            f"| {r['query'][:50]} | {r['expected_doc_id']} | {found} | {rank} | "
            f"{r['top_score']:.3f} | {r['latency_ms']:.0f}ms |"
        )

    lines.extend([
        "",
        "## Conclusion",
        "",
        "*(Fill in after reviewing results)*",
        "",
    ])

    if report.chunked_precision_at_5 > report.full_precision_at_5:
        lines.append("Based on precision@5, **chunked** strategy performed better.")
    elif report.full_precision_at_5 > report.chunked_precision_at_5:
        lines.append("Based on precision@5, **full-doc** strategy performed better.")
    else:
        lines.append("Based on precision@5, both strategies performed **equally**.")

    if report.chunked_avg_latency_ms and report.full_avg_latency_ms:
        faster = "full-doc" if report.full_avg_latency_ms < report.chunked_avg_latency_ms else "chunked"
        ratio = max(report.chunked_avg_latency_ms, report.full_avg_latency_ms) / min(report.chunked_avg_latency_ms, report.full_avg_latency_ms)
        lines.append(f"Latency: **{faster}** was {ratio:.1f}x faster on average.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run chunking vs full-doc experiment")
    parser.add_argument(
        "--output", "-o",
        default="docs/experiments/chunking_vs_full.md",
        help="Output path for markdown report",
    )
    args = parser.parse_args()

    from src.weaviate.client import get_weaviate_client

    logger.info("Starting chunking experiment...")
    client = get_weaviate_client()

    try:
        report = run_experiment(client, EXPERIMENT_QUERIES)

        # Write markdown report
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        md = generate_markdown_report(report)
        output_path.write_text(md)
        logger.info(f"Report written to {output_path}")

        # Also write JSON for programmatic access
        json_path = output_path.with_suffix(".json")
        json_path.write_text(json.dumps(asdict(report), indent=2))
        logger.info(f"JSON data written to {json_path}")

        # Print summary
        print("\n=== Experiment Summary ===")
        print(f"Chunked Precision@5: {report.chunked_precision_at_5:.2%}")
        print(f"Full-Doc Precision@5: {report.full_precision_at_5:.2%}")
        print(f"Chunked Avg Latency: {report.chunked_avg_latency_ms:.0f}ms")
        print(f"Full-Doc Avg Latency: {report.full_avg_latency_ms:.0f}ms")

    finally:
        client.close()


if __name__ == "__main__":
    main()
