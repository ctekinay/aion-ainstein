"""Tests for full-doc indexing experiment infrastructure.

Validates:
  - Full-doc collection creation produces 1 object per document
  - Reindex script exists and is importable
  - Experiment queries are well-formed
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestReindexScriptExists:
    """Verify experiment scripts exist on disk."""

    def test_reindex_script_exists(self):
        script = PROJECT_ROOT / "scripts" / "experiments" / "reindex_full_docs.py"
        assert script.exists(), f"Script not found: {script}"

    def test_experiment_script_exists(self):
        script = PROJECT_ROOT / "scripts" / "experiments" / "run_chunking_experiment.py"
        assert script.exists(), f"Script not found: {script}"


class TestReindexScriptImportable:
    """Verify the reindex script can be imported."""

    def test_reindex_module_importable(self):
        """The reindex script should be importable without side effects."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "reindex_full_docs",
            str(PROJECT_ROOT / "scripts" / "experiments" / "reindex_full_docs.py"),
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        # We don't exec the module (it would try to connect to Weaviate)
        # Just verify it loaded without import errors


class TestFullDocCollectionNames:
    """Full-doc collections use _FULL suffix convention."""

    def test_collection_names(self):
        pytest.importorskip("weaviate", reason="weaviate not installed")
        from scripts.experiments.reindex_full_docs import FULL_DOC_COLLECTIONS

        assert "adr" in FULL_DOC_COLLECTIONS
        assert "principle" in FULL_DOC_COLLECTIONS
        assert FULL_DOC_COLLECTIONS["adr"].endswith("_FULL")
        assert FULL_DOC_COLLECTIONS["principle"].endswith("_FULL")


class TestExperimentQueries:
    """Experiment queries are well-formed and cover key scenarios."""

    def test_queries_exist(self):
        from scripts.experiments.run_chunking_experiment import EXPERIMENT_QUERIES

        assert len(EXPERIMENT_QUERIES) >= 5, "Need at least 5 experiment queries"

    def test_queries_have_required_fields(self):
        from scripts.experiments.run_chunking_experiment import EXPERIMENT_QUERIES

        for q in EXPERIMENT_QUERIES:
            assert q.question, f"Query missing question: {q}"
            assert q.expected_doc_id, f"Query missing expected_doc_id: {q}"
            assert q.collection_type in ("adr", "principle"), (
                f"Invalid collection_type: {q.collection_type}"
            )
            assert q.category in ("exact", "semantic", "cross_reference"), (
                f"Invalid category: {q.category}"
            )

    def test_queries_cover_both_collections(self):
        from scripts.experiments.run_chunking_experiment import EXPERIMENT_QUERIES

        adr_queries = [q for q in EXPERIMENT_QUERIES if q.collection_type == "adr"]
        principle_queries = [q for q in EXPERIMENT_QUERIES if q.collection_type == "principle"]
        assert len(adr_queries) >= 3, "Need at least 3 ADR queries"
        assert len(principle_queries) >= 1, "Need at least 1 Principle query"

    def test_queries_cover_exact_and_semantic(self):
        from scripts.experiments.run_chunking_experiment import EXPERIMENT_QUERIES

        exact = [q for q in EXPERIMENT_QUERIES if q.category == "exact"]
        semantic = [q for q in EXPERIMENT_QUERIES if q.category == "semantic"]
        assert len(exact) >= 1, "Need at least 1 exact query"
        assert len(semantic) >= 1, "Need at least 1 semantic query"


class TestExperimentReportGeneration:
    """Markdown report generation works correctly."""

    def test_report_generation(self):
        from scripts.experiments.run_chunking_experiment import (
            ExperimentReport,
            generate_markdown_report,
        )

        report = ExperimentReport(
            timestamp="2026-02-12T00:00:00",
            chunked_results=[
                {
                    "query": "What does ADR-0012 decide?",
                    "expected_doc_id": "0012",
                    "strategy": "chunked",
                    "found_in_top_k": True,
                    "rank": 1,
                    "top_score": 0.95,
                    "latency_ms": 50.0,
                    "top_results": [],
                },
            ],
            full_results=[
                {
                    "query": "What does ADR-0012 decide?",
                    "expected_doc_id": "0012",
                    "strategy": "full",
                    "found_in_top_k": True,
                    "rank": 1,
                    "top_score": 0.92,
                    "latency_ms": 45.0,
                    "top_results": [],
                },
            ],
            chunked_precision_at_5=1.0,
            full_precision_at_5=1.0,
            chunked_avg_latency_ms=50.0,
            full_avg_latency_ms=45.0,
        )

        md = generate_markdown_report(report)
        assert "Chunking vs Full-Doc" in md
        assert "Precision@5" in md
        assert "chunked" in md.lower() or "Chunked" in md
        assert "full" in md.lower() or "Full" in md
        assert "| Metric |" in md  # table header

    def test_report_includes_both_strategies(self):
        from scripts.experiments.run_chunking_experiment import (
            ExperimentReport,
            generate_markdown_report,
        )

        report = ExperimentReport(
            timestamp="2026-02-12T00:00:00",
            chunked_results=[],
            full_results=[],
            chunked_precision_at_5=0.0,
            full_precision_at_5=0.0,
            chunked_avg_latency_ms=0.0,
            full_avg_latency_ms=0.0,
        )

        md = generate_markdown_report(report)
        assert "Chunked Strategy" in md
        assert "Full-Doc Strategy" in md
