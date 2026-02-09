"""
RAG Quality Diagnostic Framework

Comprehensive tool for diagnosing RAG pipeline issues across all layers:
- Retrieval: Document matching, relevance scoring
- Chunking: Document size analysis
- Hybrid Search: Alpha tuning experiments
- Generation: Hallucination detection, grounding checks

Usage:
    python -m src.diagnostics.rag_diagnostics --analyze-chunks
    python -m src.diagnostics.rag_diagnostics --test-retrieval
    python -m src.diagnostics.rag_diagnostics --tune-alpha
    python -m src.diagnostics.rag_diagnostics --full-diagnostic
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.weaviate.client import get_weaviate_client
from src.weaviate.embeddings import embed_text
from src.config import settings
from weaviate.classes.query import MetadataQuery, HybridFusion


# Gold standard test questions with expected retrieval targets
DIAGNOSTIC_QUESTIONS = [
    # Simple retrieval (should find exact match)
    {
        "id": "R1",
        "question": "What does ADR-0012 decide?",
        "expected_collection": "ArchitecturalDecision",
        "expected_title_contains": "ADR-0012",
        "difficulty": "easy",
    },
    {
        "id": "R2",
        "question": "What is the status of ADR-0027?",
        "expected_collection": "ArchitecturalDecision",
        "expected_title_contains": "ADR-0027",
        "difficulty": "easy",
    },
    # Semantic retrieval (should find by meaning)
    {
        "id": "R3",
        "question": "What is Demandable Capacity?",
        "expected_collection": "Vocabulary",
        "expected_label_contains": "Demandable Capacity",
        "difficulty": "easy",
    },
    {
        "id": "R4",
        "question": "What decision was made about the domain language standard?",
        "expected_collection": "ArchitecturalDecision",
        "expected_title_contains": "CIM",  # ADR-0012
        "difficulty": "medium",
    },
    # Negative tests (should NOT find anything relevant)
    {
        "id": "N1",
        "question": "What does ADR-0050 decide?",
        "expected_collection": None,  # Should not find
        "expect_no_results": True,
        "difficulty": "negative",
    },
    {
        "id": "N2",
        "question": "What is GraphQL in our architecture?",
        "expected_collection": None,
        "expect_no_results": True,
        "difficulty": "negative",
    },
]


class RAGDiagnostics:
    """Comprehensive RAG pipeline diagnostics."""

    def __init__(self, verbose: bool = False):
        self.client = get_weaviate_client()
        self.verbose = verbose
        self.collections = [
            "Vocabulary",
            "ArchitecturalDecision",
            "Principle",
            "PolicyDocument"
        ]

    def close(self):
        """Close the Weaviate client connection."""
        if self.client:
            self.client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures client is closed."""
        self.close()
        return False

    def analyze_chunks(self) -> dict:
        """Analyze document/chunk sizes across all collections.

        Returns statistics about document sizes which affect embedding quality.
        Large documents (>2000 chars) may not embed well.
        """
        print("\n" + "="*70)
        print("CHUNK/DOCUMENT SIZE ANALYSIS")
        print("="*70)

        results = {}

        for coll_name in self.collections:
            if not self.client.collections.exists(coll_name):
                continue

            collection = self.client.collections.get(coll_name)

            # Determine text field based on collection
            text_field = {
                "Vocabulary": "content",
                "ArchitecturalDecision": "full_text",
                "Principle": "full_text",
                "PolicyDocument": "full_text",
            }.get(coll_name, "content")

            # Fetch all documents
            all_docs = collection.query.fetch_objects(limit=1000)

            sizes = []
            for obj in all_docs.objects:
                text = obj.properties.get(text_field, "") or ""
                sizes.append(len(text))

            if not sizes:
                continue

            stats = {
                "count": len(sizes),
                "min_chars": min(sizes),
                "max_chars": max(sizes),
                "avg_chars": int(sum(sizes) / len(sizes)),
                "median_chars": sorted(sizes)[len(sizes)//2],
                "over_2000": sum(1 for s in sizes if s > 2000),
                "over_5000": sum(1 for s in sizes if s > 5000),
                "over_10000": sum(1 for s in sizes if s > 10000),
            }
            results[coll_name] = stats

            print(f"\n{coll_name}:")
            print(f"  Documents: {stats['count']}")
            print(f"  Size range: {stats['min_chars']} - {stats['max_chars']} chars")
            print(f"  Average: {stats['avg_chars']} chars, Median: {stats['median_chars']} chars")
            print(f"  Large docs (>2000): {stats['over_2000']} ({stats['over_2000']/stats['count']*100:.0f}%)")
            print(f"  Very large (>5000): {stats['over_5000']} ({stats['over_5000']/stats['count']*100:.0f}%)")
            if stats['over_10000']:
                print(f"  Huge (>10000): {stats['over_10000']} - CHUNKING RECOMMENDED")

        return results

    def test_retrieval(self, questions: list = None) -> dict:
        """Test retrieval quality for diagnostic questions.

        Checks if the correct documents are retrieved for each question.
        """
        print("\n" + "="*70)
        print("RETRIEVAL QUALITY TEST")
        print("="*70)

        questions = questions or DIAGNOSTIC_QUESTIONS
        results = {"passed": 0, "failed": 0, "details": []}

        for q in questions:
            print(f"\n[{q['id']}] {q['question']}")

            # Get query embedding
            try:
                query_vector = embed_text(q["question"])
            except Exception as e:
                print(f"  ERROR: Could not compute embedding: {e}")
                results["failed"] += 1
                continue

            # Search expected collection or all collections
            target_collections = [q["expected_collection"]] if q.get("expected_collection") else self.collections

            found_match = False
            top_results = []

            for coll_name in target_collections:
                if not coll_name or not self.client.collections.exists(coll_name):
                    continue

                collection = self.client.collections.get(coll_name)

                search_results = collection.query.hybrid(
                    query=q["question"],
                    vector=query_vector,
                    alpha=settings.alpha_default,
                    limit=5,
                    fusion_type=HybridFusion.RELATIVE_SCORE,
                    return_metadata=MetadataQuery(score=True, distance=True),
                )

                for rank, obj in enumerate(search_results.objects[:3]):
                    title = obj.properties.get("title", obj.properties.get("pref_label", ""))
                    score = obj.metadata.score

                    top_results.append({
                        "collection": coll_name,
                        "rank": rank + 1,
                        "title": title[:60],
                        "score": score,
                    })

                    # Check if this matches expected
                    if q.get("expected_title_contains") and q["expected_title_contains"].lower() in title.lower():
                        found_match = True
                    if q.get("expected_label_contains") and q["expected_label_contains"].lower() in title.lower():
                        found_match = True

            # Evaluate
            test_detail = {
                "id": q["id"],
                "question": q["question"],
                "top_results": top_results[:3],
            }

            if q.get("expect_no_results"):
                # For negative tests, high scores are BAD
                top_score = max([r["score"] for r in top_results]) if top_results else 0
                if top_score < 0.5:  # Threshold for "no good match"
                    print(f"  ✅ PASS: Top score {top_score:.3f} < 0.5 (correctly found no match)")
                    results["passed"] += 1
                    test_detail["passed"] = True
                else:
                    print(f"  ❌ FAIL: Top score {top_score:.3f} >= 0.5 (should not have found match)")
                    results["failed"] += 1
                    test_detail["passed"] = False
            else:
                if found_match and top_results:
                    top = top_results[0]
                    print(f"  ✅ PASS: Found '{top['title']}' (score: {top['score']:.3f})")
                    results["passed"] += 1
                    test_detail["passed"] = True
                else:
                    print(f"  ❌ FAIL: Did not find expected document")
                    for r in top_results[:3]:
                        print(f"    Got: [{r['collection']}] {r['title']} (score: {r['score']:.3f})")
                    results["failed"] += 1
                    test_detail["passed"] = False

            results["details"].append(test_detail)

        print(f"\n{'='*70}")
        print(f"RETRIEVAL SUMMARY: {results['passed']}/{results['passed']+results['failed']} passed")
        print(f"{'='*70}")

        return results

    def tune_alpha(self, test_question: str = None, collection: str = "ArchitecturalDecision") -> dict:
        """Test different alpha values to find optimal hybrid search balance.

        Alpha controls keyword (BM25) vs vector balance:
        - 0.0 = 100% keyword/BM25
        - 0.5 = balanced
        - 1.0 = 100% vector
        """
        print("\n" + "="*70)
        print("ALPHA TUNING EXPERIMENT")
        print("="*70)

        test_question = test_question or "What decision was made about domain language?"
        alphas = [0.0, 0.3, 0.5, 0.7, 0.8, 1.0]

        print(f"\nQuestion: {test_question}")
        print(f"Collection: {collection}")
        print(f"\nTesting alpha values: {alphas}")

        if not self.client.collections.exists(collection):
            print(f"ERROR: Collection {collection} does not exist")
            return {}

        coll = self.client.collections.get(collection)
        query_vector = embed_text(test_question)

        results = {}

        for alpha in alphas:
            search_results = coll.query.hybrid(
                query=test_question,
                vector=query_vector,
                alpha=alpha,
                limit=5,
                fusion_type=HybridFusion.RELATIVE_SCORE,
                return_metadata=MetadataQuery(score=True, explain_score=True),
            )

            print(f"\n--- Alpha = {alpha} ---")
            top_docs = []
            for rank, obj in enumerate(search_results.objects[:5]):
                title = obj.properties.get("title", "")[:50]
                score = obj.metadata.score
                top_docs.append({"rank": rank+1, "title": title, "score": score})
                print(f"  {rank+1}. [{score:.3f}] {title}")

            results[f"alpha_{alpha}"] = top_docs

        return results

    def check_grounding(self, question: str, response: str, context: list) -> dict:
        """Check if a response is grounded in the provided context.

        Detects potential hallucinations by checking if key claims in the
        response can be found in the context.
        """
        print("\n" + "="*70)
        print("GROUNDING CHECK")
        print("="*70)

        # Build searchable context text
        context_text = ""
        for item in context:
            if isinstance(item, dict):
                context_text += " " + str(item.get("content", ""))
                context_text += " " + str(item.get("title", ""))
                context_text += " " + str(item.get("definition", ""))
                context_text += " " + str(item.get("decision", ""))
        context_text = context_text.lower()

        # Extract potential claims from response (simple heuristic)
        response_lower = response.lower()

        # Look for ADR references
        import re
        adr_refs = re.findall(r'adr[- ]?0*(\d+)', response_lower)

        grounding_issues = []

        for adr_num in adr_refs:
            adr_pattern = f"adr-{adr_num.zfill(4)}"
            if adr_pattern not in context_text and f"adr{adr_num}" not in context_text:
                grounding_issues.append(f"ADR-{adr_num.zfill(4)} mentioned but not in context")

        # Check if response is about something not in context
        if not context_text.strip():
            grounding_issues.append("Empty context - any substantive answer is hallucination")

        result = {
            "question": question,
            "response_length": len(response),
            "context_length": len(context_text),
            "grounding_issues": grounding_issues,
            "potentially_hallucinated": len(grounding_issues) > 0,
        }

        print(f"\nQuestion: {question[:60]}...")
        print(f"Response length: {result['response_length']} chars")
        print(f"Context length: {result['context_length']} chars")

        if grounding_issues:
            print(f"\n⚠️  POTENTIAL HALLUCINATION DETECTED:")
            for issue in grounding_issues:
                print(f"  - {issue}")
        else:
            print(f"\n✅ Response appears grounded in context")

        return result

    async def run_full_diagnostic(self, save_report: bool = True) -> dict:
        """Run complete diagnostic suite."""
        print("\n" + "="*70)
        print("   FULL RAG DIAGNOSTIC SUITE")
        print("="*70)
        print(f"Started: {datetime.now().isoformat()}")

        report = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "llm_provider": settings.llm_provider,
                "ollama_model": settings.ollama_model,
                "openai_model": settings.openai_chat_model,
                "alpha_default": settings.alpha_default,
            },
            "diagnostics": {},
        }

        # 1. Chunk Analysis
        print("\n\n[1/3] CHUNK SIZE ANALYSIS")
        report["diagnostics"]["chunk_analysis"] = self.analyze_chunks()

        # 2. Retrieval Quality
        print("\n\n[2/3] RETRIEVAL QUALITY")
        report["diagnostics"]["retrieval_quality"] = self.test_retrieval()

        # 3. Alpha Tuning
        print("\n\n[3/3] ALPHA TUNING")
        report["diagnostics"]["alpha_tuning"] = self.tune_alpha()

        # Summary
        print("\n\n" + "="*70)
        print("DIAGNOSTIC SUMMARY")
        print("="*70)

        chunk = report["diagnostics"]["chunk_analysis"]
        retrieval = report["diagnostics"]["retrieval_quality"]

        print(f"\n1. CHUNK ANALYSIS:")
        total_large = sum(c.get("over_5000", 0) for c in chunk.values())
        total_docs = sum(c.get("count", 0) for c in chunk.values())
        if total_large > 0:
            print(f"   ⚠️  {total_large}/{total_docs} documents >5000 chars - consider chunking")
        else:
            print(f"   ✅ All {total_docs} documents are reasonably sized")

        print(f"\n2. RETRIEVAL QUALITY:")
        passed = retrieval.get("passed", 0)
        total = passed + retrieval.get("failed", 0)
        pct = passed/total*100 if total else 0
        status = "✅" if pct >= 80 else "⚠️" if pct >= 60 else "❌"
        print(f"   {status} {passed}/{total} tests passed ({pct:.0f}%)")

        print(f"\n3. RECOMMENDATIONS:")
        # Generate recommendations based on findings
        recommendations = []

        if total_large > 0:
            recommendations.append("- Implement document chunking (target: 500-1500 chars)")

        if pct < 80:
            recommendations.append("- Investigate failed retrieval tests")
            recommendations.append("- Consider alpha tuning for specific query types")

        # Check alpha tuning results
        alpha_results = report["diagnostics"].get("alpha_tuning", {})
        if alpha_results:
            recommendations.append(f"- Review alpha tuning results for optimal values")

        if not recommendations:
            recommendations.append("- RAG pipeline appears healthy!")

        for rec in recommendations:
            print(f"   {rec}")

        # Save report
        if save_report:
            output_dir = Path("diagnostic_reports")
            output_dir.mkdir(exist_ok=True)
            filename = f"rag_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = output_dir / filename
            with open(filepath, "w") as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\n📄 Report saved to: {filepath}")

        return report


def main():
    parser = argparse.ArgumentParser(description="RAG Quality Diagnostics")
    parser.add_argument("--analyze-chunks", action="store_true",
                        help="Analyze document/chunk sizes")
    parser.add_argument("--test-retrieval", action="store_true",
                        help="Test retrieval quality")
    parser.add_argument("--tune-alpha", action="store_true",
                        help="Run alpha tuning experiment")
    parser.add_argument("--full-diagnostic", action="store_true",
                        help="Run complete diagnostic suite")
    parser.add_argument("--question", "-q", type=str,
                        help="Custom question for testing")
    parser.add_argument("--collection", "-c", type=str, default="ArchitecturalDecision",
                        help="Collection to test")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    parser.add_argument("--no-save", action="store_true",
                        help="Don't save report to file")

    args = parser.parse_args()

    with RAGDiagnostics(verbose=args.verbose) as diag:
        if args.analyze_chunks:
            diag.analyze_chunks()
        elif args.test_retrieval:
            diag.test_retrieval()
        elif args.tune_alpha:
            diag.tune_alpha(
                test_question=args.question,
                collection=args.collection
            )
        elif args.full_diagnostic:
            asyncio.run(diag.run_full_diagnostic(save_report=not args.no_save))
        else:
            parser.print_help()
            print("\nExamples:")
            print("  python -m src.diagnostics.rag_diagnostics --analyze-chunks")
            print("  python -m src.diagnostics.rag_diagnostics --test-retrieval")
            print('  python -m src.diagnostics.rag_diagnostics --tune-alpha -q "What is CIM?"')
            print("  python -m src.diagnostics.rag_diagnostics --full-diagnostic")


if __name__ == "__main__":
    main()
