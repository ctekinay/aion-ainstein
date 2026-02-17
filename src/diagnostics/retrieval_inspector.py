"""
RAG Retrieval Inspector

Run diagnostic queries to inspect what documents are being retrieved
and how they're being scored. This helps identify retrieval quality issues.

Usage:
    python -m src.diagnostics.retrieval_inspector "What is a switchgear?"
    python -m src.diagnostics.retrieval_inspector --all-tests
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.weaviate.client import get_client
from src.weaviate.embeddings import embed_text
from src.config import settings
from weaviate.classes.query import MetadataQuery, HybridFusion


# Test questions for diagnostics
TEST_QUESTIONS = [
    ("Vocabulary", "What is a switchgear?"),
    ("Vocabulary", "Define transformer in the context of energy systems"),
    ("ADR", "What architecture decisions have been made about messaging?"),
    ("ADR", "Why was Kafka chosen?"),
    ("Principle", "What principles guide API design?"),
    ("Principle", "What are the security principles?"),
    ("Cross-domain", "How do our policies affect data architecture?"),
    ("Factual", "List all accepted ADRs"),
]


def inspect_retrieval(question: str, collection_name: str, limit: int = 10, alpha: float = None):
    """
    Inspect what documents are retrieved for a given question.

    Returns detailed information about each retrieved document including
    BM25 and vector scores.
    """
    # Use configured default if not specified
    if alpha is None:
        alpha = settings.alpha_default

    client = get_client()

    # Compute embedding client-side only for Ollama collections.
    # OpenAI collections use Weaviate's text2vec-openai vectorizer server-side.
    query_vector = None
    if settings.llm_provider == "ollama":
        query_vector = embed_text(question)

    # Check if collection exists
    if not client.collections.exists(collection_name):
        return {"error": f"Collection {collection_name} does not exist"}

    collection = client.collections.get(collection_name)

    # Perform hybrid search
    results = collection.query.hybrid(
        query=question,
        vector=query_vector,
        alpha=alpha,
        limit=limit,
        fusion_type=HybridFusion.RELATIVE_SCORE,
        return_metadata=MetadataQuery(score=True, explain_score=True, distance=True),
    )

    retrieved_docs = []
    for i, obj in enumerate(results.objects):
        doc_info = {
            "rank": i + 1,
            "uuid": str(obj.uuid),
            "score": obj.metadata.score,
            "distance": obj.metadata.distance,
            "explain_score": obj.metadata.explain_score,
            "properties": {}
        }

        # Get key properties based on collection type
        props = obj.properties
        if "title" in props:
            doc_info["properties"]["title"] = props.get("title", "")[:100]
        if "name" in props:
            doc_info["properties"]["name"] = props.get("name", "")[:100]
        if "content" in props:
            doc_info["properties"]["content_preview"] = props.get("content", "")[:300]
        if "definition" in props:
            doc_info["properties"]["definition_preview"] = props.get("definition", "")[:300]
        if "decision" in props:
            doc_info["properties"]["decision_preview"] = props.get("decision", "")[:300]
        if "doc_type" in props:
            doc_info["properties"]["doc_type"] = props.get("doc_type", "")
        if "status" in props:
            doc_info["properties"]["status"] = props.get("status", "")

        retrieved_docs.append(doc_info)

    return {
        "question": question,
        "collection": collection_name,
        "alpha": alpha,
        "limit": limit,
        "num_results": len(retrieved_docs),
        "results": retrieved_docs
    }


def inspect_all_collections(question: str, alpha: float = None, limit: int = 5):
    """Inspect retrieval across all collections for a question."""
    suffix = "_OpenAI" if settings.llm_provider == "openai" else ""
    collections = [
        f"Vocabulary{suffix}",
        f"ArchitecturalDecision{suffix}",
        f"Principle{suffix}",
        f"PolicyDocument{suffix}",
    ]

    all_results = {
        "question": question,
        "alpha": alpha,
        "collections": {}
    }

    for coll in collections:
        try:
            result = inspect_retrieval(question, coll, limit=limit, alpha=alpha)
            all_results["collections"][coll] = result
        except Exception as e:
            all_results["collections"][coll] = {"error": str(e)}

    return all_results


def compare_alpha_values(question: str, collection_name: str, alphas: list = None):
    """Compare retrieval results with different alpha values."""
    if alphas is None:
        alphas = [0.0, 0.3, 0.5, 0.7, 1.0]

    comparison = {
        "question": question,
        "collection": collection_name,
        "alpha_comparison": {}
    }

    for alpha in alphas:
        result = inspect_retrieval(question, collection_name, limit=5, alpha=alpha)
        # Extract just titles/names for comparison
        doc_ids = []
        for doc in result.get("results", []):
            title = doc["properties"].get("title") or doc["properties"].get("name") or str(doc["uuid"])[:8]
            doc_ids.append(f"{doc['rank']}. {title} (score: {doc['score']:.3f})")
        comparison["alpha_comparison"][f"alpha_{alpha}"] = doc_ids

    return comparison


def print_inspection_report(results: dict, verbose: bool = False):
    """Pretty print the inspection results."""
    print("\n" + "=" * 70)
    print(f"RETRIEVAL INSPECTION REPORT")
    print("=" * 70)
    print(f"\nQuestion: {results.get('question', 'N/A')}")

    if "collections" in results:
        # Multi-collection report
        for coll_name, coll_results in results["collections"].items():
            print(f"\n--- {coll_name} ---")
            if "error" in coll_results:
                print(f"  ERROR: {coll_results['error']}")
                continue

            print(f"  Alpha: {coll_results.get('alpha', 'N/A')}, Results: {coll_results.get('num_results', 0)}")

            for doc in coll_results.get("results", [])[:5]:
                title = doc["properties"].get("title") or doc["properties"].get("name") or "Untitled"
                score = doc.get("score", 0)
                doc_type = doc["properties"].get("doc_type", "")
                print(f"  {doc['rank']}. [{score:.3f}] {title[:50]} ({doc_type})")

                if verbose:
                    preview = (doc["properties"].get("content_preview") or
                              doc["properties"].get("definition_preview") or
                              doc["properties"].get("decision_preview") or "")
                    if preview:
                        print(f"      Preview: {preview[:100]}...")

    elif "alpha_comparison" in results:
        # Alpha comparison report
        print(f"\nCollection: {results.get('collection', 'N/A')}")
        print("\nTop 5 results at different alpha values:")
        for alpha_key, docs in results["alpha_comparison"].items():
            print(f"\n{alpha_key}:")
            for doc in docs:
                print(f"  {doc}")

    else:
        # Single collection report
        print(f"\nCollection: {results.get('collection', 'N/A')}")
        print(f"Alpha: {results.get('alpha', 'N/A')}")
        print(f"Results: {results.get('num_results', 0)}")

        for doc in results.get("results", []):
            title = doc["properties"].get("title") or doc["properties"].get("name") or "Untitled"
            score = doc.get("score", 0)
            print(f"\n{doc['rank']}. {title}")
            print(f"   Score: {score:.4f}, Distance: {doc.get('distance', 'N/A')}")

            if verbose and doc.get("explain_score"):
                print(f"   Explain: {doc['explain_score']}")

            preview = (doc["properties"].get("content_preview") or
                      doc["properties"].get("definition_preview") or
                      doc["properties"].get("decision_preview") or "")
            if preview:
                print(f"   Preview: {preview[:150]}...")


def run_all_tests(verbose: bool = False):
    """Run all test questions and generate a summary report."""
    print("\n" + "=" * 70)
    print("RUNNING ALL DIAGNOSTIC TESTS")
    print("=" * 70)

    for category, question in TEST_QUESTIONS:
        print(f"\n[{category}] {question}")
        print("-" * 50)

        results = inspect_all_collections(question, limit=3)

        for coll_name, coll_results in results["collections"].items():
            if "error" in coll_results:
                print(f"  {coll_name}: ERROR - {coll_results['error']}")
                continue

            num = coll_results.get("num_results", 0)
            if num > 0:
                top_doc = coll_results["results"][0]
                title = top_doc["properties"].get("title") or top_doc["properties"].get("name") or "?"
                score = top_doc.get("score", 0)
                print(f"  {coll_name}: {num} docs, top: [{score:.3f}] {title[:40]}")
            else:
                print(f"  {coll_name}: 0 docs")


def main():
    parser = argparse.ArgumentParser(description="RAG Retrieval Inspector")
    parser.add_argument("question", nargs="?", help="Question to inspect")
    parser.add_argument("--collection", "-c", help="Specific collection to query")
    parser.add_argument("--alpha", "-a", type=float, default=None, help=f"Hybrid search alpha (0-1), default from config: {settings.alpha_default}")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Number of results")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--compare-alpha", action="store_true", help="Compare different alpha values")
    parser.add_argument("--all-tests", action="store_true", help="Run all diagnostic tests")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.all_tests:
        run_all_tests(verbose=args.verbose)
        return

    if not args.question:
        parser.print_help()
        print("\nExample usage:")
        print('  python -m src.diagnostics.retrieval_inspector "What is a switchgear?"')
        print('  python -m src.diagnostics.retrieval_inspector "Why Kafka?" -c ArchitecturalDecision')
        print('  python -m src.diagnostics.retrieval_inspector "API principles" --compare-alpha')
        print('  python -m src.diagnostics.retrieval_inspector --all-tests')
        return

    if args.compare_alpha:
        default_coll = "ArchitecturalDecision_OpenAI" if settings.llm_provider == "openai" else "ArchitecturalDecision"
        collection = args.collection or default_coll
        results = compare_alpha_values(args.question, collection)
    elif args.collection:
        results = inspect_retrieval(args.question, args.collection, args.limit, args.alpha)
    else:
        results = inspect_all_collections(args.question, args.alpha, args.limit)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print_inspection_report(results, verbose=args.verbose)


if __name__ == "__main__":
    main()
