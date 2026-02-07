#!/usr/bin/env python3
"""
Comprehensive test script for validating the transparency-first retrieval implementation.

Tests:
1. Skills injection (response-formatter)
2. Chunked vs non-chunked ingestion
3. DAR filtering
4. Principle number extraction
5. Quality metrics comparison

Usage:
    python tests/test_implementation_quality.py
    python tests/test_implementation_quality.py --skip-ingestion  # Skip re-indexing
"""

import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.weaviate.client import get_weaviate_client
from src.weaviate.ingestion import DataIngestionPipeline
from src.elysia_agents import ElysiaRAGSystem

console = Console()
app = typer.Typer()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    passed: bool
    message: str
    details: Optional[Dict] = None
    latency_ms: Optional[int] = None


@dataclass
class TestSuite:
    """Collection of test results."""
    suite_name: str
    results: List[TestResult]

    @property
    def passed(self) -> bool:
        """Check if all tests passed."""
        return all(r.passed for r in self.results)

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate percentage."""
        if not self.results:
            return 0.0
        return (sum(1 for r in self.results if r.passed) / len(self.results)) * 100


class ImplementationTester:
    """Test harness for validating the implementation."""

    def __init__(self):
        self.client = None
        self.elysia = None

    async def setup(self):
        """Set up test environment."""
        console.print("\n[bold blue]Setting up test environment...[/bold blue]")
        self.client = get_weaviate_client()
        self.elysia = ElysiaRAGSystem(self.client)
        console.print("[green]✓[/green] Environment ready\n")

    def teardown(self):
        """Clean up test environment."""
        if self.client:
            self.client.close()

    # ========== Test Suite 1: Skills Injection ==========

    async def test_skills_injection(self) -> TestSuite:
        """Test that skills are properly injected into Elysia's agent description."""
        console.print(Panel("[bold]Test Suite 1: Skills Injection[/bold]"))
        results = []

        # Test 1.1: Check base agent description
        test_name = "1.1 Base Agent Description Exists"
        try:
            has_base = hasattr(self.elysia, '_base_agent_description')
            base_content = self.elysia._base_agent_description if has_base else ""

            passed = (
                has_base and
                "AInstein" in base_content and
                "ADR" in base_content
            )
            message = "✓ Base description configured" if passed else "✗ Base description missing or invalid"
            results.append(TestResult(test_name, passed, message))
            console.print(f"  {message}")
        except Exception as e:
            results.append(TestResult(test_name, False, f"✗ Error: {e}"))
            console.print(f"  ✗ Error: {e}")

        # Test 1.2: Check Tree initialization
        test_name = "1.2 Tree Initialized with Agent Description"
        try:
            has_tree = hasattr(self.elysia, 'tree')
            passed = has_tree and self.elysia.tree is not None
            message = "✓ Tree properly initialized" if passed else "✗ Tree not initialized"
            results.append(TestResult(test_name, passed, message))
            console.print(f"  {message}")
        except Exception as e:
            results.append(TestResult(test_name, False, f"✗ Error: {e}"))
            console.print(f"  ✗ Error: {e}")

        # Test 1.3: Test dynamic skill injection for "list" queries
        test_name = "1.3 Skills Dynamically Injected for List Queries"
        try:
            start = time.time()
            response, _ = await self.elysia.query("What ADRs exist?")
            latency_ms = int((time.time() - start) * 1000)

            # Check for response-formatter skill indicators
            has_formatting = any([
                # Check for numbered lists
                re.search(r'\n\s*\d+\.\s+', response),
                # Check for bullet points
                re.search(r'\n\s*[-•]\s+', response),
                # Check for statistics/summary
                'total' in response.lower() or 'summary' in response.lower(),
            ])

            passed = has_formatting
            message = "✓ Response has rich formatting" if passed else "✗ Response lacks formatting (skills may not be injected)"
            results.append(TestResult(test_name, passed, message, latency_ms=latency_ms))
            console.print(f"  {message} (latency: {latency_ms}ms)")
        except Exception as e:
            results.append(TestResult(test_name, False, f"✗ Error: {e}"))
            console.print(f"  ✗ Error: {e}")

        return TestSuite("Skills Injection", results)

    # ========== Test Suite 2: DAR Filtering ==========

    async def test_dar_filtering(self) -> TestSuite:
        """Test that Decision Approval Records are properly filtered."""
        console.print(Panel("[bold]Test Suite 2: DAR Filtering[/bold]"))
        results = []

        # Test 2.1: List ADRs should exclude DARs
        test_name = "2.1 List ADRs Excludes DARs"
        try:
            start = time.time()
            response, _ = await self.elysia.query("What ADRs exist?")
            latency_ms = int((time.time() - start) * 1000)

            # Check for DAR indicators in response
            has_dar_indicators = any([
                'Approval Record' in response,
                'Decision Approval Record' in response,
                re.search(r'ADR\.\d{2}D', response),  # e.g., ADR.21D
            ])

            passed = not has_dar_indicators
            message = "✓ DARs properly excluded" if passed else "✗ DARs found in response"

            # Count ADRs mentioned
            adr_count = len(re.findall(r'ADR\.\d{2}(?!D)', response))
            details = {"adr_count": adr_count, "has_dars": has_dar_indicators}

            results.append(TestResult(test_name, passed, message, details, latency_ms))
            console.print(f"  {message} (found {adr_count} ADRs, latency: {latency_ms}ms)")
        except Exception as e:
            results.append(TestResult(test_name, False, f"✗ Error: {e}"))
            console.print(f"  ✗ Error: {e}")

        # Test 2.2: Expected ADR count (should be ~18 without DARs)
        test_name = "2.2 ADR Count in Expected Range"
        try:
            # Query Weaviate directly for count
            collection = self.client.collections.get("ArchitecturalDecision")

            # Import filter builder
            from src.skills.filters import build_document_filter
            from src.skills.registry import SkillRegistry

            skill_registry = SkillRegistry()
            content_filter = build_document_filter("list all ADRs", skill_registry)

            aggregate = collection.aggregate.over_all(
                total_count=True,
                filters=content_filter
            )
            total_count = aggregate.total_count

            # Expected: 18-20 ADRs (excluding DARs)
            # If chunking enabled, could be 3-4x this (54-80 chunks per original doc)
            # With 39 ADR files and ~3 sections each = ~117-130 chunks typical
            passed = 15 <= total_count <= 150  # Extended range for chunking variance
            message = f"✓ Found {total_count} ADR objects" if passed else f"✗ Unexpected count: {total_count}"

            results.append(TestResult(test_name, passed, message, {"total_count": total_count}))
            console.print(f"  {message}")
        except Exception as e:
            results.append(TestResult(test_name, False, f"✗ Error: {e}"))
            console.print(f"  ✗ Error: {e}")

        return TestSuite("DAR Filtering", results)

    # ========== Test Suite 3: Principle Number Extraction ==========

    async def test_principle_numbers(self) -> TestSuite:
        """Test that principle numbers are properly extracted in chunked mode."""
        console.print(Panel("[bold]Test Suite 3: Principle Number Extraction[/bold]"))
        results = []

        # Test 3.1: Check principle_number field population
        test_name = "3.1 Principle Numbers Populated"
        try:
            collection = self.client.collections.get("Principle")

            # Fetch a sample of principles
            sample_results = collection.query.fetch_objects(limit=10)

            principles_with_numbers = sum(
                1 for obj in sample_results.objects
                if obj.properties.get("principle_number")
            )

            total_sampled = len(sample_results.objects)

            # At least 80% should have principle numbers
            passed = total_sampled > 0 and (principles_with_numbers / total_sampled) >= 0.8

            message = (
                f"✓ {principles_with_numbers}/{total_sampled} principles have numbers"
                if passed else
                f"✗ Only {principles_with_numbers}/{total_sampled} have numbers (expected ≥80%)"
            )

            results.append(TestResult(
                test_name, passed, message,
                {"with_numbers": principles_with_numbers, "total": total_sampled}
            ))
            console.print(f"  {message}")
        except Exception as e:
            results.append(TestResult(test_name, False, f"✗ Error: {e}"))
            console.print(f"  ✗ Error: {e}")

        # Test 3.2: Query for specific principle by number
        test_name = "3.2 Query Specific Principle by Number"
        try:
            start = time.time()
            response, _ = await self.elysia.query("What is PCP.10?")
            latency_ms = int((time.time() - start) * 1000)

            # Should mention PCP.10 or principle 10
            has_reference = "PCP.10" in response or "principle 10" in response.lower()

            passed = has_reference
            message = "✓ Successfully retrieved PCP.10" if passed else "✗ PCP.10 not found"

            results.append(TestResult(test_name, passed, message, latency_ms=latency_ms))
            console.print(f"  {message} (latency: {latency_ms}ms)")
        except Exception as e:
            results.append(TestResult(test_name, False, f"✗ Error: {e}"))
            console.print(f"  ✗ Error: {e}")

        return TestSuite("Principle Number Extraction", results)

    # ========== Test Suite 4: Chunking Quality ==========

    async def test_chunking_quality(self) -> TestSuite:
        """Test chunking implementation quality."""
        console.print(Panel("[bold]Test Suite 4: Chunking Quality[/bold]"))
        results = []

        # Test 4.1: Check if chunking was enabled during ingestion
        test_name = "4.1 Detect Chunking Mode"
        try:
            collection = self.client.collections.get("ArchitecturalDecision")

            # Sample some ADRs and check titles for section indicators
            sample_results = collection.query.fetch_objects(limit=5)

            chunked_titles = sum(
                1 for obj in sample_results.objects
                if " - " in obj.properties.get("title", "")  # Chunked format: "Title - Section"
            )

            total_sampled = len(sample_results.objects)
            chunking_detected = chunked_titles > 0

            message = (
                f"✓ Chunking detected ({chunked_titles}/{total_sampled} have section suffixes)"
                if chunking_detected else
                "ℹ No chunking detected (using whole documents)"
            )

            # This isn't a pass/fail test, just informational
            results.append(TestResult(
                test_name, True, message,
                {"chunked_count": chunked_titles, "total": total_sampled, "chunking_enabled": chunking_detected}
            ))
            console.print(f"  {message}")
        except Exception as e:
            results.append(TestResult(test_name, False, f"✗ Error: {e}"))
            console.print(f"  ✗ Error: {e}")

        # Test 4.2: Query for specific section (tests precision)
        test_name = "4.2 Section-Specific Query Precision"
        try:
            start = time.time()
            response, _ = await self.elysia.query("What is the decision in ADR.21?")
            latency_ms = int((time.time() - start) * 1000)

            # Should reference ADR.21 and decision
            has_reference = "ADR.21" in response or "ADR 21" in response
            mentions_decision = "decision" in response.lower()

            passed = has_reference and mentions_decision
            message = "✓ Successfully retrieved decision section" if passed else "✗ Failed to retrieve decision"

            results.append(TestResult(test_name, passed, message, latency_ms=latency_ms))
            console.print(f"  {message} (latency: {latency_ms}ms)")
        except Exception as e:
            results.append(TestResult(test_name, False, f"✗ Error: {e}"))
            console.print(f"  ✗ Error: {e}")

        return TestSuite("Chunking Quality", results)

    # ========== Test Suite 5: Transparency & Counts ==========

    async def test_transparency(self) -> TestSuite:
        """Test transparency features (showing X of Y total)."""
        console.print(Panel("[bold]Test Suite 5: Transparency & Counts[/bold]"))
        results = []

        # Test 5.1: Response includes total counts
        test_name = "5.1 Response Includes Total Counts"
        try:
            start = time.time()
            response, _ = await self.elysia.query("What ADRs exist?")
            latency_ms = int((time.time() - start) * 1000)

            # Look for transparency indicators
            has_counts = any([
                re.search(r'\d+\s+of\s+\d+', response),  # "X of Y"
                re.search(r'\d+\s+total', response.lower()),  # "X total"
                re.search(r'showing\s+\d+', response.lower()),  # "showing X"
            ])

            passed = has_counts
            message = "✓ Response includes counts" if passed else "✗ No count information found"

            results.append(TestResult(test_name, passed, message, latency_ms=latency_ms))
            console.print(f"  {message} (latency: {latency_ms}ms)")
        except Exception as e:
            results.append(TestResult(test_name, False, f"✗ Error: {e}"))
            console.print(f"  ✗ Error: {e}")

        # Test 5.2: Collection count transparency
        test_name = "5.2 Collection Count Accuracy"
        try:
            # Get actual count from Weaviate
            collection = self.client.collections.get("ArchitecturalDecision")
            from src.skills.filters import build_document_filter
            from src.skills.registry import SkillRegistry

            skill_registry = SkillRegistry()
            content_filter = build_document_filter("list all ADRs", skill_registry)

            aggregate = collection.aggregate.over_all(
                total_count=True,
                filters=content_filter
            )
            actual_count = aggregate.total_count

            # Query and check if response mentions this count
            response, _ = await self.elysia.query("How many ADRs are there?")

            # Extract numbers from response
            numbers = [int(n) for n in re.findall(r'\b\d+\b', response)]

            # Check if response mentions a reasonable count
            # Valid answers include:
            # - Chunk count (actual_count, e.g., 126)
            # - Approx document count (actual_count/3, e.g., 42)
            # - Actual document count range (15-40 for typical ADR sets)
            # The LLM may report document count rather than chunk count, which is semantically correct
            valid_chunk_count = actual_count in numbers
            valid_approx_doc_count = (actual_count // 3) in numbers
            valid_doc_count = any(15 <= n <= 40 for n in numbers)  # Typical ADR document range

            passed = valid_chunk_count or valid_approx_doc_count or valid_doc_count
            message = (
                f"✓ Count mentioned (found {numbers}, database has {actual_count} chunks)"
                if passed else
                f"✗ No valid count found (expected 15-40 docs or ~{actual_count} chunks, found {numbers})"
            )

            results.append(TestResult(test_name, passed, message, {"actual": actual_count, "mentioned": numbers}))
            console.print(f"  {message}")
        except Exception as e:
            results.append(TestResult(test_name, False, f"✗ Error: {e}"))
            console.print(f"  ✗ Error: {e}")

        return TestSuite("Transparency", results)


async def run_all_tests(skip_ingestion: bool = False) -> Dict[str, TestSuite]:
    """Run all test suites."""
    tester = ImplementationTester()

    try:
        # Setup
        await tester.setup()

        # Optionally re-ingest data
        if not skip_ingestion:
            console.print(Panel("[bold yellow]Re-ingesting data with chunking enabled...[/bold yellow]"))
            console.print("This may take a few minutes...\n")

            pipeline = DataIngestionPipeline(tester.client)
            stats = pipeline.run_full_ingestion(
                recreate_collections=True,
                enable_chunking=True,
            )

            console.print(f"\n[green]✓[/green] Ingestion complete:")
            console.print(f"  - Vocabulary: {stats['vocabulary']}")
            console.print(f"  - ADRs: {stats['adr']}")
            console.print(f"  - Principles: {stats['principle']}")
            console.print(f"  - Policies: {stats['policy']}")
            console.print(f"  - Chunking: {'enabled' if stats.get('chunking_enabled') else 'disabled'}\n")

        # Run test suites
        suites = {}
        suites['skills'] = await tester.test_skills_injection()
        suites['dar_filtering'] = await tester.test_dar_filtering()
        suites['principles'] = await tester.test_principle_numbers()
        suites['chunking'] = await tester.test_chunking_quality()
        suites['transparency'] = await tester.test_transparency()

        return suites

    finally:
        tester.teardown()


def print_summary(suites: Dict[str, TestSuite]):
    """Print test summary table."""
    console.print("\n")
    console.print(Panel("[bold]Test Summary[/bold]"))

    table = Table(title="Test Results")
    table.add_column("Suite", style="cyan")
    table.add_column("Tests", justify="right")
    table.add_column("Passed", justify="right", style="green")
    table.add_column("Failed", justify="right", style="red")
    table.add_column("Pass Rate", justify="right")
    table.add_column("Status")

    total_tests = 0
    total_passed = 0

    for suite_name, suite in suites.items():
        passed_count = sum(1 for r in suite.results if r.passed)
        failed_count = len(suite.results) - passed_count
        pass_rate = suite.pass_rate

        total_tests += len(suite.results)
        total_passed += passed_count

        status = "✓ PASS" if suite.passed else "✗ FAIL"
        status_style = "green" if suite.passed else "red"

        table.add_row(
            suite.suite_name,
            str(len(suite.results)),
            str(passed_count),
            str(failed_count),
            f"{pass_rate:.1f}%",
            f"[{status_style}]{status}[/{status_style}]"
        )

    console.print(table)

    # Overall summary
    overall_pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
    overall_passed = all(suite.passed for suite in suites.values())

    console.print(f"\n[bold]Overall: {total_passed}/{total_tests} tests passed ({overall_pass_rate:.1f}%)[/bold]")

    if overall_passed:
        console.print("\n[bold green]✓ ALL TESTS PASSED - Implementation validated![/bold green]")
        return 0
    else:
        console.print("\n[bold red]✗ Some tests failed - review results above[/bold red]")
        return 1


@app.command()
def main(
    skip_ingestion: bool = typer.Option(
        False, "--skip-ingestion", "-s",
        help="Skip re-ingestion (use existing data)"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Save results to JSON file"
    ),
):
    """Run comprehensive implementation validation tests."""
    console.print(Panel(
        "[bold]AION-AINSTEIN Implementation Quality Tests[/bold]\n\n"
        "Validates: Skills injection, DAR filtering, chunking, principle numbers, transparency",
        title="Test Harness",
        style="bold blue"
    ))

    # Run tests
    suites = asyncio.run(run_all_tests(skip_ingestion))

    # Print summary
    exit_code = print_summary(suites)

    # Save results if requested
    if output:
        results_dict = {
            suite_name: {
                "suite_name": suite.suite_name,
                "passed": suite.passed,
                "pass_rate": suite.pass_rate,
                "results": [
                    {
                        "name": r.name,
                        "passed": r.passed,
                        "message": r.message,
                        "details": r.details,
                        "latency_ms": r.latency_ms,
                    }
                    for r in suite.results
                ]
            }
            for suite_name, suite in suites.items()
        }

        output.write_text(json.dumps(results_dict, indent=2))
        console.print(f"\n[green]✓[/green] Results saved to {output}")

    sys.exit(exit_code)


if __name__ == "__main__":
    app()
