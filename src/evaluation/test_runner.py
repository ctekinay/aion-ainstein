#!/usr/bin/env python3
"""
Gold Standard RAG Test Runner

Runs the recommended 25 test questions against both Ollama and OpenAI
providers and generates a quality report.

Usage:
    python -m src.evaluation.test_runner
    python -m src.evaluation.test_runner --provider ollama
    python -m src.evaluation.test_runner --provider openai
    python -m src.evaluation.test_runner --quick  # Run only 10 questions
"""

import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Test questions - the recommended 25 from gold standard
TEST_QUESTIONS = [
    # Vocabulary (4)
    {"id": "V1", "category": "Vocabulary", "difficulty": "Easy",
     "question": "What is 'Demandable Capacity' in energy systems?",
     "expected_keywords": ["difference", "high", "low", "power", "limit"]},

    {"id": "V3", "category": "Vocabulary", "difficulty": "Easy",
     "question": "What is Agentic RAG according to the vocabulary?",
     "expected_keywords": ["agent", "RAG", "retrieval"]},

    {"id": "V6", "category": "Vocabulary", "difficulty": "Medium",
     "question": "What is a Business Actor in ArchiMate?",
     "expected_keywords": ["business", "actor", "archimate"]},

    {"id": "V8", "category": "Vocabulary", "difficulty": "Medium",
     "question": "What is defined in the IEC 61970 standard?",
     "expected_keywords": ["CIM", "Common Information Model", "energy"]},

    # ADR (6)
    {"id": "A1", "category": "ADR", "difficulty": "Easy",
     "question": "What decision was made about the domain language standard?",
     "expected_keywords": ["CIM", "IEC", "61970", "domain language"]},

    {"id": "A2", "category": "ADR", "difficulty": "Easy",
     "question": "What is the status of ADR-0027 about TLS security?",
     "expected_keywords": ["Accepted", "TLS"]},

    {"id": "A3", "category": "ADR", "difficulty": "Medium",
     "question": "Why was CIM chosen as the default domain language?",
     "expected_keywords": ["semantic", "interoperability", "standard"]},

    {"id": "A4", "category": "ADR", "difficulty": "Medium",
     "question": "What authentication and authorization standard was chosen?",
     "expected_keywords": ["OAuth", "2.0", "authentication", "authorization"]},

    {"id": "A7", "category": "ADR", "difficulty": "Medium",
     "question": "How should message exchange be handled in distributed systems?",
     "expected_keywords": ["idempotent", "message"]},

    {"id": "A9", "category": "ADR", "difficulty": "Easy",
     "question": "What format is used for Architectural Decision Records?",
     "expected_keywords": ["Markdown", "MADR"]},

    # Principles (3)
    {"id": "P1", "category": "Principle", "difficulty": "Easy",
     "question": "What does the principle 'Data is een Asset' mean?",
     "expected_keywords": ["data", "asset", "value", "responsible"]},

    {"id": "P3", "category": "Principle", "difficulty": "Medium",
     "question": "What principle addresses data reliability?",
     "expected_keywords": ["betrouwbaar", "quality", "reliable"]},

    {"id": "P5", "category": "Principle", "difficulty": "Medium",
     "question": "What principle covers data access control?",
     "expected_keywords": ["toegankelijk", "access", "security"]},

    # Policies (2)
    {"id": "PO1", "category": "Policy", "difficulty": "Easy",
     "question": "What policy document covers data governance at Alliander?",
     "expected_keywords": ["Governance", "Beleid", "Alliander"]},

    {"id": "PO3", "category": "Policy", "difficulty": "Medium",
     "question": "What capability document addresses data integration?",
     "expected_keywords": ["integration", "interoperability", "Capability"]},

    # Cross-Domain (2)
    {"id": "X1", "category": "Cross-Domain", "difficulty": "Hard",
     "question": "How do the architecture decisions support the data governance principles?",
     "expected_keywords": ["CIM", "interoperability", "security", "TLS"]},

    {"id": "X4", "category": "Cross-Domain", "difficulty": "Hard",
     "question": "What security measures are defined across ADRs and principles?",
     "expected_keywords": ["TLS", "OAuth", "toegankelijk", "security"]},

    # Comparative (2)
    {"id": "C1", "category": "Comparative", "difficulty": "Hard",
     "question": "What's the difference between TLS and OAuth 2.0 in our architecture?",
     "expected_keywords": ["transport", "authentication", "communication"]},

    {"id": "C2", "category": "Comparative", "difficulty": "Medium",
     "question": "What's the difference between 'Data is beschikbaar' and 'Data is toegankelijk'?",
     "expected_keywords": ["beschikbaar", "toegankelijk", "availability", "access"]},

    # Temporal (1)
    {"id": "T2", "category": "Temporal", "difficulty": "Medium",
     "question": "When was the CIM standard decision (ADR-0012) accepted?",
     "expected_keywords": ["2025", "October", "date"]},

    # Disambiguation (1) - D1 (ESA) removed as answer not in knowledge base
    {"id": "D2", "category": "Disambiguation", "difficulty": "Medium",
     "question": "What does CIM stand for in this context?",
     "expected_keywords": ["Common Information Model", "IEC"]},

    # Negative Tests (3)
    {"id": "N1", "category": "Negative", "difficulty": "Test",
     "question": "What is the architecture decision about using GraphQL?",
     "expected_keywords": [],  # Should say "no such ADR" or similar
     "expect_no_answer": True},

    {"id": "N2", "category": "Negative", "difficulty": "Test",
     "question": "What is Alliander's policy on employee vacation days?",
     "expected_keywords": [],
     "expect_no_answer": True},

    {"id": "N3", "category": "Negative", "difficulty": "Test",
     "question": "What does ADR-0050 decide?",
     "expected_keywords": [],
     "expect_no_answer": True},
]

# Quick test subset (10 questions)
QUICK_TEST_IDS = ["V1", "A1", "A3", "P1", "PO1", "X1", "C1", "D2", "N1", "N3"]

# Faster Ollama model alternatives when default times out
FAST_OLLAMA_MODELS = [
    "alibayram/smollm3:latest",  # Small, fast model
    "llama3.2:1b",               # 1B parameter model
    "phi3:mini",                 # Microsoft's small model
    "gemma2:2b",                 # Google's 2B model
]


async def check_service_health(verbose: bool = True) -> dict:
    """Check if required services are running and accessible.

    Returns dict with service status:
    - ollama: bool (is Ollama API reachable)
    - ollama_models: list (available models)
    - chat_server: bool (is chat UI server reachable)
    - weaviate: bool (is Weaviate reachable)
    """
    import httpx

    status = {
        "ollama": False,
        "ollama_models": [],
        "chat_server": False,
        "weaviate": False,
        "errors": []
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        # Check Ollama
        try:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                status["ollama"] = True
                models = resp.json().get("models", [])
                status["ollama_models"] = [m["name"] for m in models]
        except Exception as e:
            status["errors"].append(f"Ollama: {e}")

        # Check Chat Server
        try:
            resp = await client.get("http://localhost:8081/api/settings")
            if resp.status_code == 200:
                status["chat_server"] = True
        except Exception as e:
            status["errors"].append(f"Chat Server: {e}")

        # Check Weaviate
        try:
            resp = await client.get("http://localhost:8080/v1/.well-known/ready")
            if resp.status_code == 200:
                status["weaviate"] = True
        except Exception as e:
            status["errors"].append(f"Weaviate: {e}")

    if verbose:
        print("\n🔍 Service Health Check:")
        print(f"  Ollama API:    {'✅' if status['ollama'] else '❌'} {'(' + str(len(status['ollama_models'])) + ' models)' if status['ollama'] else '(not running)'}")
        print(f"  Chat Server:   {'✅' if status['chat_server'] else '❌'} {'(http://localhost:8081)' if status['chat_server'] else '(not running)'}")
        print(f"  Weaviate:      {'✅' if status['weaviate'] else '❌'} {'(http://localhost:8080)' if status['weaviate'] else '(not running)'}")

        if status["ollama_models"]:
            print(f"\n  Available Ollama models: {', '.join(status['ollama_models'][:5])}")
            if len(status["ollama_models"]) > 5:
                print(f"    ... and {len(status['ollama_models']) - 5} more")

    return status


def suggest_faster_model(current_model: str, available_models: list) -> Optional[str]:
    """Suggest a faster model if current one times out."""
    for fast_model in FAST_OLLAMA_MODELS:
        # Check if model or a variant is available
        for available in available_models:
            if fast_model.split(":")[0] in available.lower():
                if available != current_model:
                    return available
    return None


def calculate_keyword_score(response: str, expected_keywords: list) -> float:
    """Calculate what fraction of expected keywords are in the response."""
    if not expected_keywords:
        return 1.0  # No keywords expected

    response_lower = response.lower()
    found = sum(1 for kw in expected_keywords if kw.lower() in response_lower)
    return found / len(expected_keywords)


def check_no_answer(response: str) -> bool:
    """Check if response indicates 'I don't know' or similar."""
    no_answer_phrases = [
        "don't have information",
        "no such",
        "doesn't exist",
        "does not exist",
        "not found",
        "no adr",
        "cannot find",
        "not in the",
        "no information",
        "i don't know",
        "unable to find",
        "not available",
        "does not include",
        "cannot provide an answer",
        "no specific",
        "not mentioned",
        "no mention of",
        "outside the scope",
        "beyond the scope",
        "not covered",
        "no relevant",
        "no data about",
        "no record of",
    ]
    response_lower = response.lower()
    return any(phrase in response_lower for phrase in no_answer_phrases)


async def set_provider(provider: str, model: str = None) -> bool:
    """Set the LLM provider via API before running tests."""
    import httpx

    # Default models for each provider
    default_models = {
        "ollama": "qwen3:4b",  # Faster than smollm3
        "openai": "gpt-4o-mini"  # Cost-effective
    }

    model = model or default_models.get(provider, "qwen3:4b")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "http://localhost:8081/api/settings/llm",
                json={"provider": provider, "model": model}
            )
            if response.status_code == 200:
                print(f"✓ Provider set to: {provider} ({model})")
                return True
            else:
                print(f"✗ Failed to set provider: {response.text}")
                return False
    except Exception as e:
        print(f"✗ Error setting provider: {e}")
        return False


async def query_rag(question: str, provider: str = "ollama", debug: bool = False) -> dict:
    """Query the RAG system and return response with timing."""
    import httpx

    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=330.0) as client:  # Slightly longer than server's 300s
            # Use the non-streaming JSON endpoint (not SSE)
            response = await client.post(
                "http://localhost:8081/api/chat",
                json={"message": question},
                headers={"Content-Type": "application/json"}
            )

            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                if debug:
                    print(f"\n    [DEBUG] Error: {error_msg}")
                return {
                    "response": "",
                    "latency_ms": latency_ms,
                    "error": error_msg
                }

            # Parse JSON response
            data = response.json()
            full_response = data.get("response", "")

            if debug:
                print(f"\n    [DEBUG] Response length: {len(full_response)}")
                print(f"    [DEBUG] Sources: {len(data.get('sources', []))}")
                if not full_response:
                    print(f"    [DEBUG] Full response data: {data}")

            return {
                "response": full_response,
                "latency_ms": latency_ms,
                "error": None,
                "sources": data.get("sources", [])
            }

    except httpx.TimeoutException:
        return {
            "response": "",
            "latency_ms": int((time.time() - start_time) * 1000),
            "error": "Request timed out (180s)"
        }
    except Exception as e:
        return {
            "response": "",
            "latency_ms": int((time.time() - start_time) * 1000),
            "error": str(e)
        }


async def run_single_test(test: dict, provider: str, debug: bool = False) -> dict:
    """Run a single test question and evaluate the result."""
    print(f"  [{test['id']}] {test['question'][:50]}...", end=" ", flush=True)

    result = await query_rag(test["question"], provider, debug=debug)

    if result["error"]:
        print(f"❌ ERROR: {result['error']}")
        return {
            **test,
            "response": "",
            "latency_ms": result["latency_ms"],
            "score": "error",
            "keyword_score": 0,
            "error": result["error"]
        }

    response = result["response"]

    # Evaluate response
    if test.get("expect_no_answer"):
        # For negative tests, check if it correctly says "I don't know"
        is_correct = check_no_answer(response)
        score = "✅" if is_correct else "❌"
        keyword_score = 1.0 if is_correct else 0.0
    else:
        # For regular tests, check keyword coverage
        keyword_score = calculate_keyword_score(response, test["expected_keywords"])
        if keyword_score >= 0.8:
            score = "✅"
        elif keyword_score >= 0.5:
            score = "⚠️"
        else:
            score = "❌"

    print(f"{score} ({result['latency_ms']}ms, keywords: {keyword_score:.0%})")

    return {
        **test,
        "response": response[:500],  # Truncate for report
        "latency_ms": result["latency_ms"],
        "score": score,
        "keyword_score": keyword_score,
        "error": None
    }


async def run_tests(provider: str = "ollama", model: str = None, quick: bool = False, debug: bool = False, skip_health_check: bool = False) -> dict:
    """Run all tests and generate report."""

    questions = TEST_QUESTIONS
    if quick:
        questions = [q for q in TEST_QUESTIONS if q["id"] in QUICK_TEST_IDS]

    print(f"\n{'='*60}")
    print(f"RAG Quality Test - {provider.upper()} Provider")
    print(f"{'='*60}")

    # Health check before running tests
    if not skip_health_check:
        health = await check_service_health(verbose=True)

        # Critical: Chat server must be running
        if not health["chat_server"]:
            print("\n❌ FATAL: Chat server is not running!")
            print("   Start it with: python -m src.chat_ui")
            return {"error": "chat_server_not_running", "results": []}

        # Critical: Weaviate must be running
        if not health["weaviate"]:
            print("\n❌ FATAL: Weaviate is not running!")
            print("   Start it with: docker-compose up -d")
            return {"error": "weaviate_not_running", "results": []}

        # Warning: Ollama not running but using Ollama provider
        if provider == "ollama" and not health["ollama"]:
            print("\n⚠️  WARNING: Ollama is not running but provider is 'ollama'!")
            print("   Options:")
            print("   1. Start Ollama: ollama serve")
            print("   2. Use OpenAI: python -m src.evaluation.test_runner --openai")
            print()
            user_input = input("Continue anyway? [y/N]: ").strip().lower()
            if user_input != 'y':
                return {"error": "ollama_not_running", "results": []}

        # Check if specified model exists
        if provider == "ollama" and model and health["ollama_models"]:
            if model not in health["ollama_models"]:
                print(f"\n⚠️  WARNING: Model '{model}' not found in Ollama!")
                print(f"   Available models: {', '.join(health['ollama_models'][:5])}")
                suggestion = suggest_faster_model(model, health["ollama_models"])
                if suggestion:
                    print(f"   Suggested faster model: {suggestion}")

    print()

    # Set provider via API before running tests
    if not await set_provider(provider, model):
        print("WARNING: Could not set provider. Tests may use wrong provider.")
    print()

    print(f"Running {len(questions)} questions...")
    if debug:
        print("[DEBUG MODE ENABLED]")
    print()

    results = []
    consecutive_timeouts = 0
    timeout_warned = False

    for test in questions:
        result = await run_single_test(test, provider, debug=debug)
        results.append(result)

        # Track consecutive timeouts
        if result.get("error") and "timeout" in result["error"].lower():
            consecutive_timeouts += 1
            if consecutive_timeouts >= 3 and not timeout_warned:
                timeout_warned = True
                print("\n" + "="*60)
                print("⚠️  MULTIPLE TIMEOUTS DETECTED!")
                print("="*60)
                print("The current model may be too slow. Consider:")
                print("  1. Using a faster model: --model llama3.2:1b")
                print("  2. Using a smaller model: --model alibayram/smollm3:latest")
                print("  3. Switching to OpenAI: --openai")
                print("  4. Increasing server timeout in elysia_agents.py")
                print("="*60 + "\n")
        else:
            consecutive_timeouts = 0  # Reset on successful query

    # Calculate summary statistics
    total = len(results)
    correct = sum(1 for r in results if r["score"] == "✅")
    partial = sum(1 for r in results if r["score"] == "⚠️")
    wrong = sum(1 for r in results if r["score"] == "❌")
    errors = sum(1 for r in results if r["score"] == "error")

    avg_latency = sum(r["latency_ms"] for r in results) / total if total > 0 else 0
    avg_keyword_score = sum(r["keyword_score"] for r in results) / total if total > 0 else 0

    # Category breakdown
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "correct": 0}
        categories[cat]["total"] += 1
        if r["score"] == "✅":
            categories[cat]["correct"] += 1

    # Difficulty breakdown
    difficulties = {}
    for r in results:
        diff = r["difficulty"]
        if diff not in difficulties:
            difficulties[diff] = {"total": 0, "correct": 0}
        difficulties[diff]["total"] += 1
        if r["score"] == "✅":
            difficulties[diff]["correct"] += 1

    report = {
        "timestamp": datetime.now().isoformat(),
        "provider": provider,
        "total_questions": total,
        "summary": {
            "correct": correct,
            "partial": partial,
            "wrong": wrong,
            "errors": errors,
            "accuracy": f"{(correct / total * 100):.1f}%" if total > 0 else "0%",
            "avg_latency_ms": int(avg_latency),
            "avg_keyword_score": f"{avg_keyword_score:.1%}",
        },
        "by_category": {cat: f"{v['correct']}/{v['total']}" for cat, v in categories.items()},
        "by_difficulty": {diff: f"{v['correct']}/{v['total']}" for diff, v in difficulties.items()},
        "results": results,
    }

    # Print summary
    print()
    print(f"{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total Questions: {total}")
    print(f"✅ Correct: {correct} ({correct/total*100:.1f}%)")
    print(f"⚠️ Partial: {partial} ({partial/total*100:.1f}%)")
    print(f"❌ Wrong: {wrong} ({wrong/total*100:.1f}%)")
    print(f"Errors: {errors}")
    print(f"Average Latency: {avg_latency:.0f}ms")
    print(f"Average Keyword Score: {avg_keyword_score:.1%}")
    print()
    print("By Category:")
    for cat, score in report["by_category"].items():
        print(f"  {cat}: {score}")
    print()
    print("By Difficulty:")
    for diff, score in report["by_difficulty"].items():
        print(f"  {diff}: {score}")

    return report


def save_report(report: dict, output_dir: str = "test_results"):
    """Save test report to JSON file."""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    filename = f"rag_test_{report['provider']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = output_path / filename

    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nReport saved to: {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="RAG Quality Test Runner")
    parser.add_argument("--provider", "-p", choices=["ollama", "openai"], default="ollama",
                       help="LLM provider to test")
    parser.add_argument("--openai", action="store_true",
                       help="Shortcut for --provider openai")
    parser.add_argument("--model", "-m", type=str, default=None,
                       help="Specific model to use (e.g., qwen3:4b, gpt-4o)")
    parser.add_argument("--quick", "-q", action="store_true",
                       help="Run quick test (10 questions instead of 25)")
    parser.add_argument("--debug", "-d", action="store_true",
                       help="Enable debug output (show raw SSE events)")
    parser.add_argument("--no-save", action="store_true",
                       help="Don't save report to file")
    parser.add_argument("--skip-health-check", action="store_true",
                       help="Skip service health check before tests")
    parser.add_argument("--check-only", action="store_true",
                       help="Only run health check, don't run tests")

    args = parser.parse_args()

    # Handle --openai shortcut
    provider = "openai" if args.openai else args.provider

    print("\n" + "="*60)
    print("  AION-AINSTEIN RAG Quality Test Runner")
    print("="*60)

    # Health check only mode
    if args.check_only:
        asyncio.run(check_service_health(verbose=True))
        return

    print(f"\nMake sure the server is running: python -m src.chat_ui")
    print(f"Provider: {provider}")
    if args.model:
        print(f"Model: {args.model}")
    print(f"Mode: {'Quick (10 questions)' if args.quick else 'Full (25 questions)'}")
    if args.debug:
        print("Debug: ENABLED")

    # Run tests
    report = asyncio.run(run_tests(
        provider=provider,
        model=args.model,
        quick=args.quick,
        debug=args.debug,
        skip_health_check=args.skip_health_check
    ))

    # Save report
    if not args.no_save:
        save_report(report)


if __name__ == "__main__":
    main()
