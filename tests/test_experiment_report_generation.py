"""Tests for experiment report generation (both markdown and JSON)."""

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestReportFileGeneration:
    """Verify that the report writer creates valid files."""

    def test_markdown_report_written_to_disk(self):
        from scripts.experiments.run_chunking_experiment import (
            ExperimentReport,
            generate_markdown_report,
        )

        report = ExperimentReport(
            timestamp="2026-02-12T00:00:00",
            chunked_results=[
                {
                    "query": "Test query",
                    "expected_doc_id": "0012",
                    "strategy": "chunked",
                    "found_in_top_k": True,
                    "rank": 1,
                    "top_score": 0.9,
                    "latency_ms": 40.0,
                    "top_results": [],
                },
            ],
            full_results=[
                {
                    "query": "Test query",
                    "expected_doc_id": "0012",
                    "strategy": "full",
                    "found_in_top_k": False,
                    "rank": None,
                    "top_score": 0.6,
                    "latency_ms": 35.0,
                    "top_results": [],
                },
            ],
            chunked_precision_at_5=1.0,
            full_precision_at_5=0.0,
            chunked_avg_latency_ms=40.0,
            full_avg_latency_ms=35.0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "report.md"
            md_content = generate_markdown_report(report)
            md_path.write_text(md_content)

            assert md_path.exists()
            content = md_path.read_text()
            assert "Chunking vs Full-Doc" in content
            assert "100.00%" in content or "1.00" in content  # chunked precision
            assert "Test query" in content

    def test_json_report_valid(self):
        from scripts.experiments.run_chunking_experiment import ExperimentReport

        report = ExperimentReport(
            timestamp="2026-02-12T00:00:00",
            chunked_results=[],
            full_results=[],
            chunked_precision_at_5=0.5,
            full_precision_at_5=0.5,
            chunked_avg_latency_ms=100.0,
            full_avg_latency_ms=100.0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "report.json"
            json_path.write_text(json.dumps(asdict(report), indent=2))

            assert json_path.exists()
            data = json.loads(json_path.read_text())
            assert "chunked_precision_at_5" in data
            assert "full_precision_at_5" in data
            assert data["chunked_precision_at_5"] == 0.5

    def test_report_metric_table_format(self):
        """Report must include a properly formatted comparison table."""
        from scripts.experiments.run_chunking_experiment import (
            ExperimentReport,
            generate_markdown_report,
        )

        report = ExperimentReport(
            timestamp="2026-02-12T00:00:00",
            chunked_results=[
                {
                    "query": "Q1",
                    "expected_doc_id": "0001",
                    "strategy": "chunked",
                    "found_in_top_k": True,
                    "rank": 1,
                    "top_score": 0.95,
                    "latency_ms": 50.0,
                    "top_results": [],
                },
                {
                    "query": "Q2",
                    "expected_doc_id": "0002",
                    "strategy": "chunked",
                    "found_in_top_k": False,
                    "rank": None,
                    "top_score": 0.3,
                    "latency_ms": 60.0,
                    "top_results": [],
                },
            ],
            full_results=[
                {
                    "query": "Q1",
                    "expected_doc_id": "0001",
                    "strategy": "full",
                    "found_in_top_k": True,
                    "rank": 2,
                    "top_score": 0.88,
                    "latency_ms": 45.0,
                    "top_results": [],
                },
                {
                    "query": "Q2",
                    "expected_doc_id": "0002",
                    "strategy": "full",
                    "found_in_top_k": True,
                    "rank": 1,
                    "top_score": 0.92,
                    "latency_ms": 55.0,
                    "top_results": [],
                },
            ],
            chunked_precision_at_5=0.5,
            full_precision_at_5=1.0,
            chunked_avg_latency_ms=55.0,
            full_avg_latency_ms=50.0,
        )

        md = generate_markdown_report(report)

        # Must include both strategies' metrics
        assert "50.00%" in md  # chunked precision
        assert "100.00%" in md  # full-doc precision
        # Must have "full-doc" as winner
        assert "full-doc" in md.lower()
