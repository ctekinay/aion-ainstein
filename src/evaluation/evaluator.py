"""RAG Evaluation Framework for comparing Ollama vs OpenAI performance.

Provides structured evaluation of:
- Retrieval quality (recall, precision)
- Response latency
- Answer quality (term coverage, length)
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# Test case definitions
DEFAULT_TEST_CASES = [
    {
        "id": "vocab_cim",
        "question": "What is CIM in the context of power systems?",
        "expected_collections": ["vocabulary"],
        "required_terms": ["IEC", "common information model", "power"],
        "category": "vocabulary",
    },
    {
        "id": "vocab_iec",
        "question": "What IEC standards are defined in the vocabulary?",
        "expected_collections": ["vocabulary"],
        "required_terms": ["IEC", "61970", "61968"],
        "category": "vocabulary",
    },
    {
        "id": "adr_markdown",
        "question": "What is the decision about using markdown for ADRs?",
        "expected_collections": ["adr"],
        "required_terms": ["markdown", "decision", "record"],
        "category": "adr",
    },
    {
        "id": "adr_oauth",
        "question": "What authentication method is recommended by the architecture decisions?",
        "expected_collections": ["adr"],
        "required_terms": ["OAuth", "authentication", "authorization"],
        "category": "adr",
    },
    {
        "id": "adr_tls",
        "question": "How should data communication be secured according to ADRs?",
        "expected_collections": ["adr"],
        "required_terms": ["TLS", "secure", "communication"],
        "category": "adr",
    },
    {
        "id": "principle_data",
        "question": "What are the data governance principles?",
        "expected_collections": ["principle"],
        "required_terms": ["data", "governance", "principle"],
        "category": "principle",
    },
    {
        "id": "principle_consistency",
        "question": "What does the eventual consistency principle say?",
        "expected_collections": ["principle"],
        "required_terms": ["eventual", "consistency", "design"],
        "category": "principle",
    },
    {
        "id": "principle_ownership",
        "question": "Who is responsible for data ownership according to the principles?",
        "expected_collections": ["principle"],
        "required_terms": ["data", "ownership", "responsible"],
        "category": "principle",
    },
    {
        "id": "cross_domain_1",
        "question": "How do architecture decisions relate to data principles?",
        "expected_collections": ["adr", "principle"],
        "required_terms": ["architecture", "data", "principle"],
        "category": "cross_domain",
    },
    {
        "id": "general_1",
        "question": "What standards should be prioritized for data exchange?",
        "expected_collections": ["adr", "vocabulary"],
        "required_terms": ["standard", "data", "exchange"],
        "category": "general",
    },
]


@dataclass
class ProviderResult:
    """Results from a single provider for one test case."""

    provider: str
    question: str
    answer: str = ""
    sources: list = field(default_factory=list)
    retrieval_latency_ms: int = 0
    generation_latency_ms: int = 0
    total_latency_ms: int = 0
    error: Optional[str] = None
    context_truncated: bool = False

    # Quality metrics (computed after)
    term_recall: float = 0.0  # Fraction of required terms found in answer
    source_recall: float = 0.0  # Fraction of expected collections in sources
    answer_length: int = 0


@dataclass
class EvaluationResult:
    """Complete evaluation results comparing both providers."""

    test_case_id: str
    question: str
    category: str
    required_terms: list
    expected_collections: list
    ollama: Optional[ProviderResult] = None
    openai: Optional[ProviderResult] = None


class RAGEvaluator:
    """Evaluator for comparing RAG system performance between providers."""

    def __init__(
        self,
        test_cases: Optional[list[dict]] = None,
        base_url: str = "http://127.0.0.1:8081",
    ):
        """Initialize evaluator.

        Args:
            test_cases: List of test case dictionaries. Uses defaults if None.
            base_url: Base URL of the chat API server.
        """
        self.test_cases = test_cases or DEFAULT_TEST_CASES
        self.base_url = base_url
        self.results: list[EvaluationResult] = []

    async def run_single_query(
        self,
        question: str,
        provider: str,
        ollama_model: str = None,
        openai_model: str = None,
    ) -> ProviderResult:
        """Run a single query against the comparison endpoint.

        Args:
            question: The question to ask
            provider: Which provider's results to extract ("ollama" or "openai")
            ollama_model: Ollama model to use
            openai_model: OpenAI model to use

        Returns:
            ProviderResult with response and metrics
        """
        ollama_model = ollama_model or settings.ollama_model
        openai_model = openai_model or settings.openai_chat_model

        result = ProviderResult(provider=provider, question=question)

        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat/stream/compare",
                    json={
                        "message": question,
                        "ollama_model": ollama_model,
                        "openai_model": openai_model,
                    },
                )
                response.raise_for_status()

                # Parse SSE stream
                for line in response.text.split("\n"):
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])

                            if data.get("type") == "assistant" and data.get("provider") == provider:
                                result.answer = data.get("content", "")
                                result.sources = data.get("sources", [])

                                timing = data.get("timing", {})
                                result.retrieval_latency_ms = timing.get("retrieval_ms", 0)
                                result.generation_latency_ms = timing.get("latency_ms", 0)
                                result.context_truncated = timing.get("context_truncated", False)

                            elif data.get("type") == "error" and data.get("provider") == provider:
                                result.error = data.get("content", "Unknown error")
                                result.sources = data.get("sources", [])

                                timing = data.get("timing", {})
                                result.retrieval_latency_ms = timing.get("retrieval_ms", 0)

                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            result.error = str(e)
            logger.error(f"Query error for {provider}: {e}")

        result.total_latency_ms = int((time.time() - start_time) * 1000)
        result.answer_length = len(result.answer)

        return result

    def compute_metrics(
        self,
        result: ProviderResult,
        required_terms: list[str],
        expected_collections: list[str],
    ) -> None:
        """Compute quality metrics for a provider result.

        Args:
            result: The provider result to compute metrics for
            required_terms: List of terms that should appear in the answer
            expected_collections: List of collection types expected in sources
        """
        if result.error:
            return

        # Term recall: fraction of required terms found in answer
        answer_lower = result.answer.lower()
        found_terms = sum(1 for term in required_terms if term.lower() in answer_lower)
        result.term_recall = found_terms / len(required_terms) if required_terms else 0.0

        # Source recall: fraction of expected collections found in sources
        source_types = {s.get("type", "").lower() for s in result.sources}
        found_collections = sum(
            1 for coll in expected_collections
            if any(coll.lower() in st for st in source_types)
        )
        result.source_recall = (
            found_collections / len(expected_collections) if expected_collections else 0.0
        )

    async def run_test_case(self, test_case: dict) -> EvaluationResult:
        """Run a single test case against both providers.

        Args:
            test_case: Test case dictionary with question, expected_collections, required_terms

        Returns:
            EvaluationResult with both provider results
        """
        question = test_case["question"]
        required_terms = test_case.get("required_terms", [])
        expected_collections = test_case.get("expected_collections", [])

        logger.info(f"Running test case: {test_case['id']} - {question[:50]}...")

        # Run both providers in parallel
        ollama_task = asyncio.create_task(self.run_single_query(question, "ollama"))
        openai_task = asyncio.create_task(self.run_single_query(question, "openai"))

        ollama_result, openai_result = await asyncio.gather(ollama_task, openai_task)

        # Compute metrics
        self.compute_metrics(ollama_result, required_terms, expected_collections)
        self.compute_metrics(openai_result, required_terms, expected_collections)

        return EvaluationResult(
            test_case_id=test_case["id"],
            question=question,
            category=test_case.get("category", "general"),
            required_terms=required_terms,
            expected_collections=expected_collections,
            ollama=ollama_result,
            openai=openai_result,
        )

    async def run_all(self, categories: Optional[list[str]] = None) -> list[EvaluationResult]:
        """Run all test cases (optionally filtered by category).

        Args:
            categories: Optional list of categories to filter by

        Returns:
            List of EvaluationResult objects
        """
        self.results = []

        test_cases = self.test_cases
        if categories:
            test_cases = [tc for tc in test_cases if tc.get("category") in categories]

        logger.info(f"Running {len(test_cases)} test cases...")

        for test_case in test_cases:
            result = await self.run_test_case(test_case)
            self.results.append(result)

        return self.results

    def get_summary(self) -> dict:
        """Generate summary statistics from evaluation results.

        Returns:
            Dictionary with aggregate metrics
        """
        if not self.results:
            return {"error": "No results available"}

        ollama_metrics = {
            "total_cases": 0,
            "successful": 0,
            "errors": 0,
            "avg_term_recall": 0.0,
            "avg_source_recall": 0.0,
            "avg_retrieval_latency_ms": 0,
            "avg_generation_latency_ms": 0,
            "avg_total_latency_ms": 0,
            "context_truncations": 0,
        }

        openai_metrics = {
            "total_cases": 0,
            "successful": 0,
            "errors": 0,
            "avg_term_recall": 0.0,
            "avg_source_recall": 0.0,
            "avg_retrieval_latency_ms": 0,
            "avg_generation_latency_ms": 0,
            "avg_total_latency_ms": 0,
        }

        for result in self.results:
            # Ollama metrics
            if result.ollama:
                ollama_metrics["total_cases"] += 1
                if result.ollama.error:
                    ollama_metrics["errors"] += 1
                else:
                    ollama_metrics["successful"] += 1
                    ollama_metrics["avg_term_recall"] += result.ollama.term_recall
                    ollama_metrics["avg_source_recall"] += result.ollama.source_recall
                    ollama_metrics["avg_retrieval_latency_ms"] += result.ollama.retrieval_latency_ms
                    ollama_metrics["avg_generation_latency_ms"] += result.ollama.generation_latency_ms
                    ollama_metrics["avg_total_latency_ms"] += result.ollama.total_latency_ms
                    if result.ollama.context_truncated:
                        ollama_metrics["context_truncations"] += 1

            # OpenAI metrics
            if result.openai:
                openai_metrics["total_cases"] += 1
                if result.openai.error:
                    openai_metrics["errors"] += 1
                else:
                    openai_metrics["successful"] += 1
                    openai_metrics["avg_term_recall"] += result.openai.term_recall
                    openai_metrics["avg_source_recall"] += result.openai.source_recall
                    openai_metrics["avg_retrieval_latency_ms"] += result.openai.retrieval_latency_ms
                    openai_metrics["avg_generation_latency_ms"] += result.openai.generation_latency_ms
                    openai_metrics["avg_total_latency_ms"] += result.openai.total_latency_ms

        # Compute averages
        if ollama_metrics["successful"] > 0:
            n = ollama_metrics["successful"]
            ollama_metrics["avg_term_recall"] /= n
            ollama_metrics["avg_source_recall"] /= n
            ollama_metrics["avg_retrieval_latency_ms"] //= n
            ollama_metrics["avg_generation_latency_ms"] //= n
            ollama_metrics["avg_total_latency_ms"] //= n

        if openai_metrics["successful"] > 0:
            n = openai_metrics["successful"]
            openai_metrics["avg_term_recall"] /= n
            openai_metrics["avg_source_recall"] /= n
            openai_metrics["avg_retrieval_latency_ms"] //= n
            openai_metrics["avg_generation_latency_ms"] //= n
            openai_metrics["avg_total_latency_ms"] //= n

        return {
            "total_test_cases": len(self.results),
            "ollama": ollama_metrics,
            "openai": openai_metrics,
        }

    def export_results(self, output_path: Path) -> None:
        """Export detailed results to JSON file.

        Args:
            output_path: Path to write results file
        """
        export_data = {
            "summary": self.get_summary(),
            "results": [],
        }

        for result in self.results:
            result_dict = {
                "test_case_id": result.test_case_id,
                "question": result.question,
                "category": result.category,
                "required_terms": result.required_terms,
                "expected_collections": result.expected_collections,
            }

            if result.ollama:
                result_dict["ollama"] = asdict(result.ollama)
            if result.openai:
                result_dict["openai"] = asdict(result.openai)

            export_data["results"].append(result_dict)

        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Results exported to {output_path}")
