#!/usr/bin/env python3
"""
Gold Standard RAG Test Runner v3.0

Runs the recommended 25 test questions against the RAG system and generates
a quality report with route tracking, doc ID tracking, and fullness regression tests.

Usage:
    python -m src.evaluation.test_runner
    python -m src.evaluation.test_runner --provider ollama
    python -m src.evaluation.test_runner --provider openai
    python -m src.evaluation.test_runner --quick  # Run only 10 questions
"""

import argparse
import asyncio
import io
import json
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

# Suppress verbose logging during tests
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("weaviate").setLevel(logging.WARNING)
logging.getLogger("elysia").setLevel(logging.WARNING)


@contextmanager
def suppress_output():
    """Suppress stdout/stderr and Rich console output for Elysia's verbose output."""
    import os

    # Save original file descriptors
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    old_stdout_fd = os.dup(1)
    old_stderr_fd = os.dup(2)

    # Open devnull
    devnull = os.open(os.devnull, os.O_WRONLY)

    try:
        # Redirect at both Python and OS level
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        # Restore everything
        os.dup2(old_stdout_fd, 1)
        os.dup2(old_stderr_fd, 2)
        os.close(old_stdout_fd)
        os.close(old_stderr_fd)
        os.close(devnull)
        sys.stdout = old_stdout
        sys.stderr = old_stderr


class RouteCapture(logging.Handler):
    """Captures log messages from elysia_agents to detect the actual route taken."""

    ROUTE_PATTERNS = [
        (re.compile(r"Meta route: short-circuiting"), "meta"),
        (re.compile(r"Specific approval query detected"), "approval"),
        (re.compile(r"Specific DAR content query detected"), "direct_doc"),
        (re.compile(r"Specific content query detected"), "direct_doc"),
        (re.compile(r"Deterministic content retrieval"), "direct_doc"),
        (re.compile(r"Deterministic approval extraction"), "approval"),
        (re.compile(r"Deterministic DAR content retrieval"), "direct_doc"),
        (re.compile(r"List query detected"), "list"),
        (re.compile(r"Deterministic list response"), "list"),
        (re.compile(r"Approval records query detected"), "list"),
        (re.compile(r"Count query detected"), "count"),
        (re.compile(r"Terminology verification failed"), "vocab"),
        (re.compile(r"Terminology verified"), "vocab"),
    ]

    def __init__(self):
        super().__init__()
        self.detected_route = None
        self.log_lines = []

    def emit(self, record):
        msg = self.format(record)
        self.log_lines.append(msg)
        for pattern, route in self.ROUTE_PATTERNS:
            if pattern.search(msg):
                self.detected_route = route

    def reset(self):
        self.detected_route = None
        self.log_lines = []

    def get_route(self) -> str:
        """Return the detected route, or 'semantic' as fallback (LLM path)."""
        return self.detected_route or "semantic"


# Global RAG system instance
_rag_system = None
_weaviate_client = None
_route_capture = RouteCapture()

# =============================================================================
# Gold Standard v3.0 - Recommended 25 questions
# =============================================================================

TEST_QUESTIONS = [
    # --- Vocabulary (4) ---
    {"id": "V1", "category": "Vocabulary", "difficulty": "Easy",
     "question": "What is 'Demandable Capacity' in energy systems?",
     "expected_keywords": ["difference", "high", "low", "power", "limit"],
     "expected_route": "vocab",
     "expected_doc_ids": []},

    {"id": "V3", "category": "Vocabulary", "difficulty": "Easy",
     "question": "What is Agentic RAG according to the vocabulary?",
     "expected_keywords": ["agent", "RAG", "retrieval"],
     "expected_route": "vocab",
     "expected_doc_ids": []},

    {"id": "V6", "category": "Vocabulary", "difficulty": "Medium",
     "question": "What is a Business Actor in ArchiMate?",
     "expected_keywords": ["business", "actor", "archimate"],
     "expected_route": "vocab",
     "expected_doc_ids": []},

    {"id": "V8", "category": "Vocabulary", "difficulty": "Medium",
     "question": "What is defined in the IEC 61970 standard?",
     "expected_keywords": ["CIM", "Common Information Model", "energy"],
     "expected_route": "vocab",
     "expected_doc_ids": []},

    # --- ADR (4) ---
    {"id": "A1", "category": "ADR", "difficulty": "Easy",
     "question": "What decision was made about the domain language standard?",
     "expected_keywords": ["CIM", "IEC", "61970", "domain language"],
     "expected_route": "semantic",
     "expected_doc_ids": ["ADR.0012"]},

    {"id": "A2", "category": "ADR", "difficulty": "Easy",
     "question": "What is the status of ADR.0027 about TLS security?",
     "expected_keywords": ["Accepted", "TLS"],
     "expected_route": "direct_doc",
     "expected_doc_ids": ["ADR.0027"]},

    {"id": "A3", "category": "ADR", "difficulty": "Medium",
     "question": "Why was CIM chosen as the default domain language?",
     "expected_keywords": ["semantic", "interoperability", "standard"],
     "expected_route": "semantic",
     "expected_doc_ids": ["ADR.0012"]},

    {"id": "A4", "category": "ADR", "difficulty": "Medium",
     "question": "What authentication and authorization standard was chosen?",
     "expected_keywords": ["OAuth", "2.0", "authentication", "authorization"],
     "expected_route": "semantic",
     "expected_doc_ids": ["ADR.0029"]},

    {"id": "A7", "category": "ADR", "difficulty": "Medium",
     "question": "How should message exchange be handled in distributed systems?",
     "expected_keywords": ["idempotent", "message"],
     "expected_route": "semantic",
     "expected_doc_ids": ["ADR.0026"]},

    # --- Fullness Tests (3) ---
    {"id": "F1", "category": "Fullness", "difficulty": "Medium",
     "question": "Tell me about ADR.0025",
     "expected_keywords": ["Governance", "Transparency", "Testing", "MFFBAS"],
     "expected_route": "direct_doc",
     "expected_doc_ids": ["ADR.0025"],
     "fullness_min_chars": 800,
     "fullness_must_not_contain": ["Decision Approval Record List"]},

    {"id": "F2", "category": "Fullness", "difficulty": "Medium",
     "question": "Tell me about ADR.0028",
     "expected_keywords": ["invalidation", "operating constraints", "FSP"],
     "expected_route": "direct_doc",
     "expected_doc_ids": ["ADR.0028"],
     "fullness_min_chars": 500,
     "fullness_check_keywords": ["Pros", "Cons"]},

    {"id": "F3", "category": "Fullness", "difficulty": "Medium",
     "question": "Who approved ADR.0025?",
     "expected_keywords": ["Robert-Jan Peters", "Laurent van Groningen", "Accepted"],
     "expected_route": "approval",
     "expected_doc_ids": ["ADR.0025D"],
     "fullness_must_not_contain": ["Unified D/R product interface"]},

    # --- Principles (3) ---
    {"id": "P1", "category": "Principle", "difficulty": "Easy",
     "question": "What does the principle 'Data is een Asset' mean?",
     "expected_keywords": ["data", "asset", "value", "responsible"],
     "expected_route": "semantic",
     "expected_doc_ids": []},

    {"id": "P3", "category": "Principle", "difficulty": "Medium",
     "question": "What principle addresses data reliability?",
     "expected_keywords": ["betrouwbaar", "quality", "reliable"],
     "expected_route": "semantic",
     "expected_doc_ids": ["PCP.0036"]},

    {"id": "P4", "category": "Principle", "difficulty": "Medium",
     "question": "What does 'eventual consistency by design' mean?",
     "expected_keywords": ["eventual", "consistency", "design"],
     "expected_route": "semantic",
     "expected_doc_ids": ["PCP.0010"]},

    {"id": "P5", "category": "Principle", "difficulty": "Medium",
     "question": "What principle covers data access control?",
     "expected_keywords": ["toegankelijk", "access", "security"],
     "expected_route": "semantic",
     "expected_doc_ids": ["PCP.0038"]},

    # --- Policies (2) ---
    {"id": "PO1", "category": "Policy", "difficulty": "Easy",
     "question": "What policy document covers data governance at Alliander?",
     "expected_keywords": ["Governance", "Beleid", "Alliander"],
     "expected_route": "semantic",
     "expected_doc_ids": []},

    {"id": "PO3", "category": "Policy", "difficulty": "Medium",
     "question": "What capability document addresses data integration?",
     "expected_keywords": ["integration", "interoperability", "Capability"],
     "expected_route": "semantic",
     "expected_doc_ids": []},

    # --- Cross-Domain (2) ---
    {"id": "X1", "category": "Cross-Domain", "difficulty": "Hard",
     "question": "How do the architecture decisions support the data governance principles?",
     "expected_keywords": ["CIM", "interoperability", "security", "TLS"],
     "expected_route": "multi_hop",
     "expected_doc_ids": ["ADR.0012", "PCP.0038"]},

    {"id": "X4", "category": "Cross-Domain", "difficulty": "Hard",
     "question": "What security measures are defined across ADRs and principles?",
     "expected_keywords": ["TLS", "OAuth", "toegankelijk", "security"],
     "expected_route": "multi_hop",
     "expected_doc_ids": ["ADR.0027", "ADR.0029"]},

    # --- Comparative (1) ---
    {"id": "C1", "category": "Comparative", "difficulty": "Hard",
     "question": "What's the difference between TLS and OAuth 2.0 in our architecture?",
     "expected_keywords": ["transport", "authentication", "communication"],
     "expected_route": "semantic",
     "expected_doc_ids": ["ADR.0027", "ADR.0029"]},

    # --- Listing (1) ---
    {"id": "L2", "category": "Listing", "difficulty": "Medium",
     "question": "What are all the data governance principles?",
     "expected_keywords": ["Data is een Asset", "Data is beschikbaar", "Data is begrijpelijk",
                           "Data is betrouwbaar", "Data is herbruikbaar", "Data is toegankelijk"],
     "expected_route": "list",
     "expected_doc_ids": []},

    # --- Disambiguation (1) ---
    {"id": "D1", "category": "Disambiguation", "difficulty": "Medium",
     "question": "What is ESA?",
     "expected_keywords": ["Energy System Architecture"],
     "expected_route": "vocab",
     "expected_doc_ids": []},

    # --- Negative/Edge Cases (3) ---
    {"id": "N1", "category": "Negative", "difficulty": "Test",
     "question": "What is the architecture decision about using GraphQL?",
     "expected_keywords": [],
     "expect_no_answer": True,
     "expected_route": "semantic",
     "expected_doc_ids": []},

    {"id": "N3", "category": "Negative", "difficulty": "Test",
     "question": "What does ADR.0050 decide?",
     "expected_keywords": [],
     "expect_no_answer": True,
     "expected_route": "direct_doc",
     "expected_doc_ids": []},

    # --- Meta / System Questions (2 from recommended selection) ---
    {"id": "M1", "category": "Meta", "difficulty": "Test",
     "question": "Which skills did you use to format this output?",
     "expected_keywords": ["skill", "injection", "format", "response"],
     "expected_route": "meta",
     "expected_doc_ids": []},

    {"id": "M4", "category": "Meta", "difficulty": "Test",
     "question": "Explain your own architecture",
     "expected_keywords": ["AInstein", "pipeline", "retrieval", "routing"],
     "expected_route": "meta",
     "expected_doc_ids": [],
     "must_not_contain": ["IEC 61968", "market participant", "DACI"]},

    # --- Batch / Principle Approvals (2 from recommended selection) ---
    {"id": "BA2", "category": "BatchApproval", "difficulty": "Medium",
     "question": "Who approved PCP.0020?",
     "expected_keywords": [],
     "expected_route": "approval",
     "expected_doc_ids": ["PCP.0020D"]},

    {"id": "BA3", "category": "BatchApproval", "difficulty": "Medium",
     "question": "Who approved PCP.0030?",
     "expected_keywords": [],
     "expected_route": "approval",
     "expected_doc_ids": ["PCP.0030D"]},
]

# Quick test subset (10 questions)
QUICK_TEST_IDS = ["V1", "A1", "A2", "F1", "P1", "PO1", "L2", "D1", "N1", "N3"]

# Faster Ollama model alternatives when default times out
FAST_OLLAMA_MODELS = [
    "alibayram/smollm3:latest",  # Small, fast model
    "llama3.2:1b",               # 1B parameter model
    "phi3:mini",                 # Microsoft's small model
    "gemma2:2b",                 # Google's 2B model
]


# =============================================================================
# Doc ID Normalization (accepts ADR.0025 / ADR.25 / ADR-0025 as equivalent)
# =============================================================================

_DOC_ID_PATTERN = re.compile(
    r'\b(ADR|PCP|Principle)[.\s-]?0*(\d+)D?\b', re.IGNORECASE
)


def normalize_doc_id(doc_id: str) -> str:
    """Normalize a doc ID to canonical form: ADR.XXXX or PCP.XXXX."""
    m = _DOC_ID_PATTERN.match(doc_id.strip())
    if m:
        prefix = m.group(1).upper()
        if prefix == "PRINCIPLE":
            prefix = "PCP"
        number = m.group(2).zfill(4)
        # Preserve D suffix if present
        if doc_id.strip().upper().endswith("D"):
            return f"{prefix}.{number}D"
        return f"{prefix}.{number}"
    return doc_id.strip().upper()


def extract_doc_ids_from_response(response: str) -> list[str]:
    """Extract all doc IDs mentioned in a response, normalized."""
    # Match ADR.XXXX, ADR-XXXX, ADR XXXX, PCP.XXXX, etc.
    raw_matches = re.findall(
        r'\b(ADR|PCP|Principle)[.\s-]?0*(\d+)(D)?\b', response, re.IGNORECASE
    )
    ids = set()
    for prefix, number, dar_suffix in raw_matches:
        p = prefix.upper()
        if p == "PRINCIPLE":
            p = "PCP"
        n = number.zfill(4)
        if dar_suffix:
            ids.add(f"{p}.{n}D")
        else:
            ids.add(f"{p}.{n}")
    return sorted(ids)


def check_doc_ids_ok(expected_ids: list[str], actual_ids: list[str]) -> bool:
    """Check if all expected doc IDs are present in actual IDs.

    Uses normalized comparison: ADR.0025 == ADR.25 == ADR-0025.
    Returns True if expected is empty (no specific docs expected).
    """
    if not expected_ids:
        return True
    expected_norm = {normalize_doc_id(d) for d in expected_ids}
    actual_norm = {normalize_doc_id(d) for d in actual_ids}
    return expected_norm.issubset(actual_norm)


# =============================================================================
# Route Comparison
# =============================================================================

def check_route_ok(expected_route: str, actual_route: str) -> bool:
    """Check if the actual route matches the expected route.

    Accepts semantic as equivalent to multi_hop (both go through LLM path).
    """
    if expected_route == actual_route:
        return True
    # semantic and multi_hop both go through the Elysia tree (LLM path)
    if {expected_route, actual_route} <= {"semantic", "multi_hop"}:
        return True
    # vocab queries may also go through semantic path (Elysia routes to vocabulary tool)
    if expected_route == "vocab" and actual_route == "semantic":
        return True
    return False


# =============================================================================
# Service Health Check
# =============================================================================

async def check_service_health(verbose: bool = True) -> dict:
    """Check if required services are running and accessible."""
    import httpx

    status = {
        "ollama": False,
        "ollama_models": [],
        "weaviate": False,
        "errors": []
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                status["ollama"] = True
                models = resp.json().get("models", [])
                status["ollama_models"] = [m["name"] for m in models]
        except Exception as e:
            status["errors"].append(f"Ollama: {e}")

        try:
            resp = await client.get("http://localhost:8080/v1/.well-known/ready")
            if resp.status_code == 200:
                status["weaviate"] = True
        except Exception as e:
            status["errors"].append(f"Weaviate: {e}")

    if verbose:
        print("\n  Service Health Check:")
        print(f"  Ollama API:    {'OK' if status['ollama'] else 'FAIL'} {'(' + str(len(status['ollama_models'])) + ' models)' if status['ollama'] else '(not running)'}")
        print(f"  Weaviate:      {'OK' if status['weaviate'] else 'FAIL'} {'(http://localhost:8080)' if status['weaviate'] else '(not running)'}")

        if status["ollama_models"]:
            print(f"\n  Available Ollama models: {', '.join(status['ollama_models'][:5])}")
            if len(status["ollama_models"]) > 5:
                print(f"    ... and {len(status['ollama_models']) - 5} more")

    return status


def suggest_faster_model(current_model: str, available_models: list) -> Optional[str]:
    """Suggest a faster model if current one times out."""
    for fast_model in FAST_OLLAMA_MODELS:
        for available in available_models:
            if fast_model.split(":")[0] in available.lower():
                if available != current_model:
                    return available
    return None


# =============================================================================
# Scoring Functions
# =============================================================================

def calculate_keyword_score(response: str, expected_keywords: list) -> float:
    """Calculate what fraction of expected keywords are in the response."""
    if not expected_keywords:
        return 1.0

    response_lower = response.lower()
    found = sum(1 for kw in expected_keywords if kw.lower() in response_lower)
    return found / len(expected_keywords)


def detect_hallucination(response: str, sources: list, test_id: str) -> dict:
    """Detect potential hallucinations in the response."""
    result = {
        "is_hallucination": False,
        "issues": [],
        "adr_refs_found": [],
        "adr_refs_unsupported": [],
    }

    if not response or len(response.strip()) < 10:
        return result

    # Skip hallucination detection for abstention responses
    abstention_indicators = [
        "was not found in the knowledge base",
        "i don't have sufficient information",
        "not found in the context",
        "no relevant documents found",
    ]
    response_lower = response.lower()
    if any(indicator in response_lower for indicator in abstention_indicators):
        return result

    # Build context from sources
    source_text = ""
    source_adrs = set()
    for src in (sources or []):
        if isinstance(src, dict):
            source_text += " " + str(src.get("title", ""))
            source_text += " " + str(src.get("preview", ""))
            source_text += " " + str(src.get("content", ""))
            title = str(src.get("title", ""))
            adr_match = re.search(r'adr[- ]?0*(\d+)', title.lower())
            if adr_match:
                source_adrs.add(adr_match.group(1).zfill(4))
    source_text_lower = source_text.lower()

    # Find ADR references in response
    adr_refs = re.findall(r'adr[- ]?0*(\d+)', response_lower)
    result["adr_refs_found"] = [f"ADR-{num.zfill(4)}" for num in adr_refs]

    for adr_num in adr_refs:
        adr_padded = adr_num.zfill(4)
        if adr_padded not in source_adrs:
            if f"adr-{adr_padded}" not in source_text_lower and f"adr{adr_num}" not in source_text_lower:
                result["adr_refs_unsupported"].append(f"ADR-{adr_padded}")
                result["issues"].append(f"References ADR-{adr_padded} not found in retrieved context")

    if len(source_text.strip()) < 50:
        if len(response.strip()) > 100:
            result["issues"].append("Substantive response generated with minimal/empty context")

    result["is_hallucination"] = len(result["issues"]) > 0
    return result


def check_no_answer(response: str) -> bool:
    """Check if response indicates 'I don't know' or similar."""
    if not response or len(response.strip()) < 10:
        return True

    no_answer_phrases = [
        "there is no", "there are no", "there isn't", "there aren't",
        "no such", "no adr", "no specific", "no relevant", "no information",
        "no mention of", "no data about", "no record of",
        "doesn't exist", "does not exist", "doesn't appear", "does not appear",
        "doesn't include", "does not include", "doesn't contain", "does not contain",
        "not found", "not in the", "not available", "not mentioned",
        "not covered", "not recorded",
        "cannot find", "cannot provide", "unable to find", "unable to locate",
        "don't have information", "don't have any information",
        "i don't know", "i don't have",
        "outside the scope", "beyond the scope", "not within the",
        "based on the provided context", "in the provided context",
        "context does not", "context doesn't",
    ]
    response_lower = response.lower()
    return any(phrase in response_lower for phrase in no_answer_phrases)


def evaluate_fullness(test: dict, response: str) -> dict:
    """Evaluate fullness-specific criteria for F-tests.

    Returns dict with fullness results:
    - length_ok: answer OR full_text meets minimum char threshold
    - must_not_contain_ok: no prohibited strings found
    - check_keywords_ok: additional keywords found (if specified)
    """
    result = {
        "length_ok": True,
        "must_not_contain_ok": True,
        "check_keywords_ok": True,
        "issues": [],
    }

    # Try to parse as JSON (structured mode) for full_text
    response_text = response
    full_text = ""
    try:
        parsed = json.loads(response)
        if isinstance(parsed, dict):
            response_text = parsed.get("answer", response)
            full_text = parsed.get("full_text", "")
    except (json.JSONDecodeError, TypeError):
        pass

    # Use the longer of answer or full_text for length check
    check_text = response_text if len(response_text) >= len(full_text) else full_text

    # Length check
    min_chars = test.get("fullness_min_chars")
    if min_chars and len(check_text) < min_chars:
        result["length_ok"] = False
        result["issues"].append(f"Length {len(check_text)} < {min_chars} chars (answer OR full_text)")

    # Must-not-contain check
    for prohibited in test.get("fullness_must_not_contain", []):
        if prohibited.lower() in response.lower():
            result["must_not_contain_ok"] = False
            result["issues"].append(f"Contains prohibited text: '{prohibited}'")

    # Additional keyword check (e.g., Pros/Cons)
    for kw in test.get("fullness_check_keywords", []):
        if kw.lower() not in response.lower():
            result["check_keywords_ok"] = False
            result["issues"].append(f"Missing fullness keyword: '{kw}'")

    return result


# =============================================================================
# RAG System Init & Query
# =============================================================================

async def init_rag_system(provider: str = "ollama", model: str = None) -> bool:
    """Initialize the RAG system directly (no chat server needed)."""
    global _rag_system, _weaviate_client

    from ..config import settings
    from ..weaviate.client import get_weaviate_client
    from ..elysia_agents import ElysiaRAGSystem

    default_models = {
        "ollama": "qwen3:4b",
        "openai": "gpt-4o-mini"
    }

    model = model or default_models.get(provider, "qwen3:4b")

    settings.llm_provider = provider
    if provider == "ollama":
        settings.ollama_model = model
    else:
        settings.openai_chat_model = model

    try:
        if not _weaviate_client:
            _weaviate_client = get_weaviate_client()

        _rag_system = ElysiaRAGSystem(_weaviate_client)

        # Install route capture on elysia_agents logger
        elysia_logger = logging.getLogger("src.elysia_agents")
        elysia_logger.addHandler(_route_capture)
        elysia_logger.setLevel(logging.DEBUG)

        print(f"  RAG system initialized: {provider} ({model})")
        return True

    except Exception as e:
        print(f"  FAIL: Could not initialize RAG system: {e}")
        return False


async def query_rag(question: str, debug: bool = False, verbose: bool = False) -> dict:
    """Query the RAG system and return response with timing and route info."""
    global _rag_system

    if not _rag_system:
        return {
            "response": "",
            "latency_ms": 0,
            "error": "RAG system not initialized",
            "actual_route": "unknown",
        }

    # Reset route capture for this query
    _route_capture.reset()

    start_time = time.time()

    try:
        if verbose:
            response, objects = await _rag_system.query(question)
        else:
            with suppress_output():
                response, objects = await _rag_system.query(question)

        latency_ms = int((time.time() - start_time) * 1000)

        # Get route from log capture
        actual_route = _route_capture.get_route()

        # Format sources
        sources = []
        flat_objects = []
        for item in (objects or []):
            if isinstance(item, list):
                flat_objects.extend(item)
            elif isinstance(item, dict):
                flat_objects.append(item)

        for obj in flat_objects[:5]:
            if not isinstance(obj, dict):
                continue
            source = {
                "type": obj.get("type", "Document"),
                "title": obj.get("title") or obj.get("label") or "Untitled",
            }
            content = obj.get("content") or obj.get("definition") or obj.get("decision") or ""
            if content:
                source["preview"] = content[:200] + "..." if len(content) > 200 else content
            sources.append(source)

        if debug:
            print(f"\n    [DEBUG] Response length: {len(response)}")
            print(f"    [DEBUG] Sources: {len(sources)}")
            print(f"    [DEBUG] Route: {actual_route}")
            if not response:
                print(f"    [DEBUG] Raw objects: {objects}")

        return {
            "response": response,
            "latency_ms": latency_ms,
            "error": None,
            "sources": sources,
            "actual_route": actual_route,
        }

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        if debug:
            print(f"\n    [DEBUG] Error: {error_msg}")
        return {
            "response": "",
            "latency_ms": latency_ms,
            "error": error_msg,
            "actual_route": _route_capture.get_route(),
        }


# =============================================================================
# Single Test Execution
# =============================================================================

async def run_single_test(test: dict, debug: bool = False, verbose: bool = False) -> dict:
    """Run a single test question and evaluate with route + doc ID tracking."""
    print(f"  [{test['id']}] {test['question'][:55]}...", end=" ", flush=True)

    result = await query_rag(test["question"], debug=debug, verbose=verbose)

    if result["error"]:
        print(f"ERROR: {result['error'][:50]}")
        return {
            **test,
            "response": "",
            "latency_ms": result["latency_ms"],
            "score": "error",
            "keyword_score": 0,
            "hallucination": None,
            "actual_route": result.get("actual_route", "unknown"),
            "route_ok": False,
            "actual_doc_ids": [],
            "doc_ids_ok": False,
            "fullness": None,
            "error": result["error"]
        }

    response = result["response"]
    sources = result.get("sources", [])
    actual_route = result.get("actual_route", "semantic")

    # Route check
    expected_route = test.get("expected_route", "semantic")
    route_ok = check_route_ok(expected_route, actual_route)

    # Doc ID extraction & check
    actual_doc_ids = extract_doc_ids_from_response(response)
    expected_doc_ids = test.get("expected_doc_ids", [])
    doc_ids_ok = check_doc_ids_ok(expected_doc_ids, actual_doc_ids)

    # Detect hallucination
    hallucination = detect_hallucination(response, sources, test["id"])

    # Fullness evaluation (for F-tests)
    fullness = None
    if test.get("fullness_min_chars") or test.get("fullness_must_not_contain") or test.get("fullness_check_keywords"):
        fullness = evaluate_fullness(test, response)

    # Evaluate response
    if test.get("expect_no_answer"):
        is_correct = check_no_answer(response)
        if not is_correct and hallucination["is_hallucination"]:
            score = "WRONG_HALLUC"
            keyword_score = 0.0
        elif is_correct:
            score = "PASS"
            keyword_score = 1.0
        else:
            score = "WRONG"
            keyword_score = 0.0
    else:
        keyword_score = calculate_keyword_score(response, test["expected_keywords"])

        # Check must_not_contain (confident-wrong-answer guard)
        must_not_contain_ok = True
        if test.get("must_not_contain"):
            response_lower = response.lower()
            for forbidden in test["must_not_contain"]:
                if forbidden.lower() in response_lower:
                    must_not_contain_ok = False
                    if debug:
                        print(f"    [MUST_NOT_CONTAIN] Found forbidden: '{forbidden}'")

        # For fullness tests, incorporate fullness results
        if fullness:
            fullness_ok = all([
                fullness["length_ok"],
                fullness["must_not_contain_ok"],
                fullness["check_keywords_ok"],
            ])
            if keyword_score >= 0.8 and fullness_ok and must_not_contain_ok:
                score = "PASS"
            elif keyword_score >= 0.5 or (keyword_score >= 0.3 and fullness_ok):
                score = "PARTIAL"
            else:
                score = "WRONG"
        else:
            if keyword_score >= 0.8 and must_not_contain_ok:
                score = "PASS"
            elif keyword_score >= 0.5 and must_not_contain_ok:
                score = "PARTIAL"
            elif not must_not_contain_ok:
                score = "WRONG"  # Confident wrong answer
            else:
                score = "WRONG"

    # Print result line
    route_indicator = "R:Y" if route_ok else "R:N"
    doc_id_indicator = "D:Y" if doc_ids_ok else "D:N"
    output = f"{score} ({result['latency_ms']}ms, kw:{keyword_score:.0%}, {route_indicator}, {doc_id_indicator})"
    if hallucination["is_hallucination"] and "HALLUC" not in score:
        output += " HALLUC"
    if fullness and fullness["issues"]:
        output += f" [{', '.join(fullness['issues'][:2])}]"
    print(output)

    if debug and hallucination["issues"]:
        for issue in hallucination["issues"]:
            print(f"    [HALLUCINATION] {issue}")
    if debug and not route_ok:
        print(f"    [ROUTE] expected={expected_route}, actual={actual_route}")
    if debug and not doc_ids_ok:
        print(f"    [DOC_IDS] expected={expected_doc_ids}, actual={actual_doc_ids}")

    return {
        **test,
        "response": response[:500],
        "latency_ms": result["latency_ms"],
        "score": score,
        "keyword_score": keyword_score,
        "hallucination": hallucination,
        "sources_count": len(sources),
        "actual_route": actual_route,
        "route_ok": route_ok,
        "actual_doc_ids": actual_doc_ids,
        "doc_ids_ok": doc_ids_ok,
        "fullness": fullness,
        "error": None
    }


# =============================================================================
# Full Test Suite
# =============================================================================

async def run_tests(provider: str = "ollama", model: str = None, quick: bool = False,
                    debug: bool = False, verbose: bool = False,
                    skip_health_check: bool = False) -> dict:
    """Run all tests and generate report with route/doc_id tracking."""

    questions = TEST_QUESTIONS
    if quick:
        questions = [q for q in TEST_QUESTIONS if q["id"] in QUICK_TEST_IDS]

    print(f"\n{'='*60}")
    print(f"RAG Quality Test v3.0 - {provider.upper()} Provider")
    print(f"{'='*60}")

    if not skip_health_check:
        health = await check_service_health(verbose=True)

        if not health["weaviate"]:
            print("\n  FATAL: Weaviate is not running!")
            print("   Start it with: docker-compose up -d")
            return {"error": "weaviate_not_running", "results": []}

        if provider == "ollama" and not health["ollama"]:
            print("\n  WARNING: Ollama is not running but provider is 'ollama'!")
            print("   Start Ollama: ollama serve")
            return {"error": "ollama_not_running", "results": []}

        if provider == "ollama" and model and health["ollama_models"]:
            if model not in health["ollama_models"]:
                print(f"\n  WARNING: Model '{model}' not found in Ollama!")
                print(f"   Available: {', '.join(health['ollama_models'][:5])}")

    print()

    if not await init_rag_system(provider, model):
        print("FATAL: Could not initialize RAG system.")
        return {"error": "rag_init_failed", "results": []}
    print()

    print(f"Running {len(questions)} questions...")
    if debug:
        print("[DEBUG MODE]")
    print()

    results = []
    consecutive_timeouts = 0

    for test in questions:
        result = await run_single_test(test, debug=debug, verbose=verbose)
        results.append(result)

        if result.get("error") and "timeout" in result["error"].lower():
            consecutive_timeouts += 1
            if consecutive_timeouts >= 3:
                print(f"\n  MULTIPLE TIMEOUTS - consider a faster model")
                break
        else:
            consecutive_timeouts = 0

    # =============================================================================
    # Summary Statistics
    # =============================================================================
    total = len(results)
    correct = sum(1 for r in results if r["score"] == "PASS")
    partial = sum(1 for r in results if r["score"] == "PARTIAL")
    wrong = sum(1 for r in results if r["score"] in ("WRONG", "WRONG_HALLUC"))
    errors = sum(1 for r in results if r["score"] == "error")

    hallucinations = sum(
        1 for r in results
        if r.get("hallucination") and r["hallucination"].get("is_hallucination")
    )

    route_ok_count = sum(1 for r in results if r.get("route_ok"))
    doc_ids_ok_count = sum(1 for r in results if r.get("doc_ids_ok"))

    avg_latency = sum(r["latency_ms"] for r in results) / total if total > 0 else 0
    avg_keyword_score = sum(r["keyword_score"] for r in results) / total if total > 0 else 0

    # Category breakdown
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "correct": 0, "route_ok": 0, "doc_ids_ok": 0}
        categories[cat]["total"] += 1
        if r["score"] == "PASS":
            categories[cat]["correct"] += 1
        if r.get("route_ok"):
            categories[cat]["route_ok"] += 1
        if r.get("doc_ids_ok"):
            categories[cat]["doc_ids_ok"] += 1

    # Difficulty breakdown
    difficulties = {}
    for r in results:
        diff = r["difficulty"]
        if diff not in difficulties:
            difficulties[diff] = {"total": 0, "correct": 0}
        difficulties[diff]["total"] += 1
        if r["score"] == "PASS":
            difficulties[diff]["correct"] += 1

    # Failure triage
    routing_bugs = [r for r in results if not r.get("route_ok") and r["score"] != "error"]
    retrieval_bugs = [r for r in results if r.get("route_ok") and not r.get("doc_ids_ok")
                      and r.get("expected_doc_ids") and r["score"] != "error"]
    formatter_bugs = [r for r in results if r.get("route_ok") and r.get("doc_ids_ok")
                      and r["score"] not in ("PASS", "error")]

    report = {
        "timestamp": datetime.now().isoformat(),
        "version": "3.0",
        "provider": provider,
        "model": model,
        "total_questions": total,
        "summary": {
            "correct": correct,
            "partial": partial,
            "wrong": wrong,
            "errors": errors,
            "hallucinations": hallucinations,
            "accuracy": f"{(correct / total * 100):.1f}%" if total > 0 else "0%",
            "route_accuracy": f"{(route_ok_count / total * 100):.1f}%" if total > 0 else "0%",
            "doc_id_accuracy": f"{(doc_ids_ok_count / total * 100):.1f}%" if total > 0 else "0%",
            "avg_latency_ms": int(avg_latency),
            "avg_keyword_score": f"{avg_keyword_score:.1%}",
        },
        "failure_triage": {
            "routing_bugs": [r["id"] for r in routing_bugs],
            "retrieval_bugs": [r["id"] for r in retrieval_bugs],
            "formatter_bugs": [r["id"] for r in formatter_bugs],
        },
        "by_category": {
            cat: {
                "score": f"{v['correct']}/{v['total']}",
                "route_ok": f"{v['route_ok']}/{v['total']}",
                "doc_ids_ok": f"{v['doc_ids_ok']}/{v['total']}",
            }
            for cat, v in categories.items()
        },
        "by_difficulty": {diff: f"{v['correct']}/{v['total']}" for diff, v in difficulties.items()},
        "results": results,
    }

    # Print summary
    print()
    print(f"{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total Questions: {total}")
    print(f"  PASS:    {correct} ({correct/total*100:.1f}%)" if total else "")
    print(f"  PARTIAL: {partial} ({partial/total*100:.1f}%)" if total else "")
    print(f"  WRONG:   {wrong} ({wrong/total*100:.1f}%)" if total else "")
    if hallucinations > 0:
        print(f"  HALLUC:  {hallucinations} ({hallucinations/total*100:.1f}%)")
    if errors > 0:
        print(f"  ERRORS:  {errors}")
    print()
    print(f"Route Accuracy:   {route_ok_count}/{total} ({route_ok_count/total*100:.1f}%)" if total else "")
    print(f"Doc ID Accuracy:  {doc_ids_ok_count}/{total} ({doc_ids_ok_count/total*100:.1f}%)" if total else "")
    print(f"Average Latency:  {avg_latency:.0f}ms")
    print(f"Avg Keyword Score: {avg_keyword_score:.1%}")

    print()
    print("By Category:")
    for cat, v in report["by_category"].items():
        print(f"  {cat:15s} score={v['score']:5s}  route={v['route_ok']:5s}  docs={v['doc_ids_ok']:5s}")

    print()
    print("By Difficulty:")
    for diff, score in report["by_difficulty"].items():
        print(f"  {diff}: {score}")

    if routing_bugs or retrieval_bugs or formatter_bugs:
        print()
        print("Failure Triage:")
        if routing_bugs:
            print(f"  Routing bugs:   {', '.join(r['id'] for r in routing_bugs)}")
        if retrieval_bugs:
            print(f"  Retrieval bugs: {', '.join(r['id'] for r in retrieval_bugs)}")
        if formatter_bugs:
            print(f"  Formatter bugs: {', '.join(r['id'] for r in formatter_bugs)}")

    return report


def save_report(report: dict, output_dir: str = "test_results"):
    """Save test report to JSON file."""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    filename = f"rag_test_v3_{report['provider']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = output_path / filename

    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nReport saved to: {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="RAG Quality Test Runner v3.0")
    parser.add_argument("--provider", "-p", choices=["ollama", "openai"], default="ollama",
                       help="LLM provider to test")
    parser.add_argument("--openai", action="store_true",
                       help="Shortcut for --provider openai")
    parser.add_argument("--model", "-m", type=str, default=None,
                       help="Specific model to use (e.g., qwen3:4b, gpt-4o)")
    parser.add_argument("--quick", "-q", action="store_true",
                       help="Run quick test (10 questions instead of 25)")
    parser.add_argument("--debug", "-d", action="store_true",
                       help="Enable debug output (show response details)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Show Elysia's decision process (normally suppressed)")
    parser.add_argument("--no-save", action="store_true",
                       help="Don't save report to file")
    parser.add_argument("--skip-health-check", action="store_true",
                       help="Skip service health check before tests")
    parser.add_argument("--check-only", action="store_true",
                       help="Only run health check, don't run tests")

    args = parser.parse_args()

    provider = "openai" if args.openai else args.provider

    print("\n" + "="*60)
    print("  AION-AINSTEIN RAG Quality Test Runner v3.0")
    print("="*60)

    if args.check_only:
        asyncio.run(check_service_health(verbose=True))
        return

    print(f"\nProvider: {provider}")
    if args.model:
        print(f"Model: {args.model}")
    print(f"Mode: {'Quick (10 questions)' if args.quick else 'Full (25 questions)'}")
    if args.debug:
        print("Debug: ENABLED")

    report = asyncio.run(run_tests(
        provider=provider,
        model=args.model,
        quick=args.quick,
        debug=args.debug,
        verbose=args.verbose,
        skip_health_check=args.skip_health_check
    ))

    if not args.no_save and "error" not in report:
        save_report(report)


if __name__ == "__main__":
    main()
