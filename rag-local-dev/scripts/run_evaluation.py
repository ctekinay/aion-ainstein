#!/usr/bin/env python3
"""
Evaluation script for RAG system.
Runs test queries and calculates metrics.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
import logging
import argparse
from typing import List, Dict, Any

from src.database.connection import get_db_connection
from src.embedding.factory import get_embedder
from src.search.retrieval_tool import RetrievalTool

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_test_queries(config: dict) -> List[Dict[str, Any]]:
    """Load test queries from YAML file."""
    test_file = config.get("evaluation", {}).get("test_queries_file", "src/evaluation/test_queries.yaml")
    test_path = Path(__file__).parent.parent / test_file

    if not test_path.exists():
        logger.error(f"Test queries file not found: {test_path}")
        return []

    with open(test_path) as f:
        data = yaml.safe_load(f)

    return data.get("queries", [])


def evaluate_query(tool: RetrievalTool, query_spec: dict, verbose: bool = False) -> dict:
    """
    Evaluate a single query.

    Returns:
        Dict with query, results, and evaluation metrics
    """
    query = query_spec["query"]
    expected_type = query_spec.get("type")
    expected_doc_types = query_spec.get("expected_doc_types", [])

    result = tool.search(
        query=query,
        doc_types=None,  # Don't filter to test retrieval quality
        max_chunks=10,
        include_terminology=True,
    )

    # Calculate metrics
    metrics = {
        "query": query,
        "expected_type": expected_type,
        "detected_type": result.query_type_detected,
        "type_match": expected_type == result.query_type_detected if expected_type else None,
        "confidence": result.confidence,
        "no_good_results": result.no_good_results,
        "result_count": len(result.chunks),
        "latency_ms": result.latency_ms,
        "top_score": result.chunks[0].score if result.chunks else 0,
    }

    # Check if expected document types are in results
    if expected_doc_types:
        found_types = set(c.document_type for c in result.chunks)
        metrics["expected_types_found"] = any(t in found_types for t in expected_doc_types)
        metrics["found_types"] = list(found_types)
    else:
        metrics["expected_types_found"] = None
        metrics["found_types"] = list(set(c.document_type for c in result.chunks))

    # Terminology check
    metrics["terminology_matches"] = len(result.terminology_matches)

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"Query: {query}")
        print(f"Expected type: {expected_type}, Detected: {result.query_type_detected}")
        print(f"Confidence: {result.confidence:.3f}, Results: {len(result.chunks)}")
        print(f"Latency: {result.latency_ms}ms")
        if result.chunks:
            print(f"Top result: {result.chunks[0].document_id} ({result.chunks[0].score:.3f})")
            print(f"  Type: {result.chunks[0].document_type}")
            print(f"  Section: {result.chunks[0].section_header}")

    return metrics


def calculate_aggregate_metrics(results: List[dict]) -> dict:
    """Calculate aggregate metrics from evaluation results."""
    total = len(results)

    if total == 0:
        return {}

    # Type detection accuracy
    type_checks = [r for r in results if r["type_match"] is not None]
    type_accuracy = sum(1 for r in type_checks if r["type_match"]) / len(type_checks) if type_checks else None

    # Average confidence
    avg_confidence = sum(r["confidence"] for r in results) / total

    # Good results rate
    good_results_rate = sum(1 for r in results if not r["no_good_results"]) / total

    # Expected types found rate
    type_found_checks = [r for r in results if r["expected_types_found"] is not None]
    expected_types_rate = sum(1 for r in type_found_checks if r["expected_types_found"]) / len(type_found_checks) if type_found_checks else None

    # Average latency
    avg_latency = sum(r["latency_ms"] for r in results) / total

    return {
        "total_queries": total,
        "type_detection_accuracy": type_accuracy,
        "average_confidence": avg_confidence,
        "good_results_rate": good_results_rate,
        "expected_types_found_rate": expected_types_rate,
        "average_latency_ms": avg_latency,
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run RAG evaluation")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed results")
    parser.add_argument("--query", "-q", help="Run single query instead of test suite")
    args = parser.parse_args()

    config = load_config()
    conn = get_db_connection(config)
    embedder = get_embedder(config)
    tool = RetrievalTool(conn, embedder, config)

    try:
        if args.query:
            # Single query mode
            result = tool.search(args.query, max_chunks=5)
            print(f"\nQuery: {args.query}")
            print(f"Type detected: {result.query_type_detected}")
            print(f"Confidence: {result.confidence:.3f}")
            print(f"Results: {len(result.chunks)}")
            print(f"Latency: {result.latency_ms}ms")

            if result.chunks:
                print("\nTop results:")
                for i, chunk in enumerate(result.chunks, 1):
                    print(f"  {i}. {chunk.document_id} ({chunk.score:.3f})")
                    print(f"     Type: {chunk.document_type}")
                    print(f"     Section: {chunk.section_header}")
                    print(f"     Preview: {chunk.content[:150]}...")

            if result.terminology_matches:
                print("\nTerminology matches:")
                for term in result.terminology_matches:
                    print(f"  - {term.pref_label} ({term.score:.3f})")
                    if term.definition:
                        print(f"    {term.definition[:100]}...")

            if result.suggested_refinements:
                print("\nSuggested refinements:")
                for ref in result.suggested_refinements:
                    print(f"  - {ref}")
        else:
            # Full test suite
            test_queries = load_test_queries(config)

            if not test_queries:
                logger.error("No test queries found")
                return

            logger.info(f"Running {len(test_queries)} test queries...")

            results = []
            for query_spec in test_queries:
                try:
                    result = evaluate_query(tool, query_spec, args.verbose)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error evaluating query '{query_spec['query']}': {e}")

            # Calculate and print aggregate metrics
            metrics = calculate_aggregate_metrics(results)

            print("\n" + "=" * 60)
            print("EVALUATION SUMMARY")
            print("=" * 60)
            print(f"Total queries: {metrics['total_queries']}")
            if metrics.get('type_detection_accuracy') is not None:
                print(f"Type detection accuracy: {metrics['type_detection_accuracy']:.1%}")
            print(f"Average confidence: {metrics['average_confidence']:.3f}")
            print(f"Good results rate: {metrics['good_results_rate']:.1%}")
            if metrics.get('expected_types_found_rate') is not None:
                print(f"Expected types found: {metrics['expected_types_found_rate']:.1%}")
            print(f"Average latency: {metrics['average_latency_ms']:.0f}ms")

            # Show failed queries
            failed = [r for r in results if r["no_good_results"]]
            if failed:
                print(f"\nQueries with poor results ({len(failed)}):")
                for r in failed:
                    print(f"  - {r['query']} (confidence: {r['confidence']:.3f})")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
