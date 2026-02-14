"""Elysia-based agentic RAG system for AION-AINSTEIN.

Uses Weaviate's Elysia framework for decision tree-based tool selection
and agentic query processing.

Concurrency:
    Elysia Tree calls are blocking. To prevent event loop starvation under load,
    all Tree invocations are wrapped with asyncio.to_thread() and guarded by a
    semaphore to limit concurrent calls.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional, Any

import re

# =============================================================================
# Concurrency Control
# =============================================================================

# Module-level semaphore for Elysia call concurrency control
_elysia_semaphore: asyncio.Semaphore | None = None
_elysia_semaphore_size: int | None = None


def _get_elysia_semaphore() -> asyncio.Semaphore:
    """Get or create the Elysia concurrency semaphore.

    Lazily initialized to work with any event loop.
    Uses settings.max_concurrent_elysia_calls for the limit.
    """
    global _elysia_semaphore, _elysia_semaphore_size
    from .config import settings

    # Reinitialize if settings changed (for testing/reconfiguration)
    if (_elysia_semaphore is None or
            _elysia_semaphore_size != settings.max_concurrent_elysia_calls):
        _elysia_semaphore = asyncio.Semaphore(settings.max_concurrent_elysia_calls)
        _elysia_semaphore_size = settings.max_concurrent_elysia_calls
    return _elysia_semaphore
from weaviate import WeaviateClient
from weaviate.classes.query import Filter, MetadataQuery

from .config import settings


# =============================================================================
# Fallback Filter Metrics & Observability
# =============================================================================

@dataclass
class FallbackMetrics:
    """Thread-safe metrics for fallback filter observability.

    Tracks:
    - adr_filter_fallback_used_total: Times fallback was triggered
    - adr_filter_fallback_blocked_total: Times fallback was blocked (cap exceeded)
    """
    adr_filter_fallback_used_total: int = 0
    adr_filter_fallback_blocked_total: int = 0
    principle_filter_fallback_used_total: int = 0
    principle_filter_fallback_blocked_total: int = 0

    def increment_fallback_used(self, collection_type: str = "adr") -> None:
        """Increment fallback used counter."""
        if collection_type == "adr":
            self.adr_filter_fallback_used_total += 1
        else:
            self.principle_filter_fallback_used_total += 1

    def increment_fallback_blocked(self, collection_type: str = "adr") -> None:
        """Increment fallback blocked counter."""
        if collection_type == "adr":
            self.adr_filter_fallback_blocked_total += 1
        else:
            self.principle_filter_fallback_blocked_total += 1

    def get_metrics(self) -> dict:
        """Return all metrics as dictionary."""
        return {
            "adr_filter_fallback_used_total": self.adr_filter_fallback_used_total,
            "adr_filter_fallback_blocked_total": self.adr_filter_fallback_blocked_total,
            "principle_filter_fallback_used_total": self.principle_filter_fallback_used_total,
            "principle_filter_fallback_blocked_total": self.principle_filter_fallback_blocked_total,
        }


# Global metrics instance
_fallback_metrics = FallbackMetrics()


def get_fallback_metrics() -> FallbackMetrics:
    """Get the global fallback metrics instance."""
    return _fallback_metrics


def generate_request_id() -> str:
    """Generate a unique request ID for error tracking."""
    return str(uuid.uuid4())[:8]


def _maybe_add_debug_footer(response: str, route_log: dict, debug_enabled: bool) -> str:
    """Append routing debug footer if debug headers are enabled.

    Only adds to string responses. Shows route, intent, confidence, and
    collections queried. Never includes prompts or sensitive info.
    """
    if not debug_enabled or not isinstance(response, str):
        return response

    parts = []
    if route_log.get("route_selected"):
        parts.append(f"route: {route_log['route_selected']}")
    if route_log.get("intent"):
        parts.append(f"intent: {route_log['intent']}")
    if route_log.get("confidence") is not None:
        parts.append(f"intent_confidence: {route_log['confidence']:.2f}")
    if route_log.get("collections_queried"):
        parts.append(f"collections: {', '.join(route_log['collections_queried'])}")
    if route_log.get("abstain_gate_triggered"):
        parts.append("abstain_gate: triggered")
    if route_log.get("tree_timeout"):
        parts.append("tree_timeout: true")

    if parts:
        footer = "\n\n---\n_" + " | ".join(parts) + "_"
        return response + footer

    return response


class FallbackBlockedError(Exception):
    """Raised when fallback is blocked due to safety cap or feature flag."""

    def __init__(self, message: str, request_id: str, reason: str, collection_size: int):
        super().__init__(message)
        self.request_id = request_id
        self.reason = reason
        self.collection_size = collection_size


def check_fallback_allowed(
    collection_size: int,
    collection_type: str,
    query: str,
    request_id: str,
) -> tuple[bool, Optional[str]]:
    """Check if fallback filtering is allowed based on guardrails.

    Args:
        collection_size: Total documents in the collection
        collection_type: "adr" or "principle"
        query: The original query for logging
        request_id: Unique request ID for tracing

    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    logger = logging.getLogger(__name__)

    # Check feature flag
    if not settings.enable_inmemory_filter_fallback:
        error_msg = (
            f"ADR metadata missing; in-memory fallback is disabled. "
            f"Please run migration. [request_id={request_id}]"
        )
        logger.warning(
            f"Fallback BLOCKED (feature disabled): "
            f"collection_type={collection_type}, collection_size={collection_size}, "
            f"query='{query[:50]}...', request_id={request_id}"
        )
        _fallback_metrics.increment_fallback_blocked(collection_type)
        return False, error_msg

    # Check safety cap
    if collection_size > settings.max_fallback_scan_docs:
        error_msg = (
            f"ADR metadata missing; collection size ({collection_size}) exceeds "
            f"safety cap ({settings.max_fallback_scan_docs}). "
            f"Please run migration. [request_id={request_id}, reason=DOC_METADATA_MISSING_REQUIRES_MIGRATION]"
        )
        logger.warning(
            f"Fallback BLOCKED (cap exceeded): "
            f"collection_type={collection_type}, collection_size={collection_size}, "
            f"max_allowed={settings.max_fallback_scan_docs}, "
            f"query='{query[:50]}...', request_id={request_id}, "
            f"reason=DOC_METADATA_MISSING_REQUIRES_MIGRATION"
        )
        _fallback_metrics.increment_fallback_blocked(collection_type)
        return False, error_msg

    # Fallback allowed - log and increment metrics
    logger.warning(
        f"adr_filter_fallback_used=1: "
        f"collection_type={collection_type}, collection_total={collection_size}, "
        f"query='{query[:50]}...', request_id={request_id}, "
        f"reason=DOC_TYPE_MISSING"
    )
    _fallback_metrics.increment_fallback_used(collection_type)

    # Warn if fallback is enabled in prod
    if settings.environment == "prod":
        logger.warning(
            f"WARNING: In-memory fallback is enabled in PRODUCTION. "
            f"This should be disabled after migration. request_id={request_id}"
        )

    return True, None
from .skills import SkillRegistry, get_skill_registry, DEFAULT_SKILL
from .skills.filters import build_document_filter
from .weaviate.embeddings import embed_text
from .weaviate.collections import get_collection_name, get_all_collection_names
from .weaviate.skosmos_client import get_skosmos_client, TermLookupResult
from .observability import metrics as obs_metrics
from .meta_route import build_meta_response
from .response_schema import (
    ResponseParser,
    ResponseValidator,
    StructuredResponse,
    RESPONSE_SCHEMA_INSTRUCTIONS,
)
from .list_response_builder import (
    build_list_result_marker,
    is_list_result,
    finalize_list_result,
    dedupe_by_identity,
)
from .response_gateway import (
    handle_list_result,
    StructuredModeContext,
    create_context_from_skills,
)

# Initialize skill registry (use singleton to share state across modules)
_skill_registry = get_skill_registry()

# Default abstention thresholds (overridden by skills if available)
_DEFAULT_DISTANCE_THRESHOLD = 0.5
_DEFAULT_MIN_QUERY_COVERAGE = 0.2


def _get_abstention_thresholds() -> tuple[float, float]:
    """Get abstention thresholds from skill configuration.

    Returns:
        Tuple of (distance_threshold, min_query_coverage)
    """
    try:
        return _skill_registry.loader.get_abstention_thresholds(DEFAULT_SKILL)
    except Exception:
        return _DEFAULT_DISTANCE_THRESHOLD, _DEFAULT_MIN_QUERY_COVERAGE


def _get_list_query_config() -> dict:
    """Get list query detection config from skill configuration.

    Returns:
        Dictionary with list_indicators, list_patterns, additional_stop_words
    """
    try:
        return _skill_registry.loader.get_list_query_config(DEFAULT_SKILL)
    except Exception:
        return {
            "list_indicators": ["list", "show", "all", "exist", "exists", "available", "have", "many", "which", "enumerate"],
            "list_patterns": [
                r"what\s+\w+s\s+(are|exist|do we have)",
                r"(list|show|give)\s+(me\s+)?(all|the)",
                r"how many\s+\w+",
                r"which\s+\w+s?\s+(are|exist|do)",
            ],
            "additional_stop_words": ["are", "there", "exist", "exists", "list", "show", "all", "me", "give"],
        }


# Cache for compiled regex patterns (performance optimization)
_compiled_list_patterns: list | None = None


def _get_compiled_list_patterns() -> list:
    """Get cached compiled regex patterns for list query detection."""
    global _compiled_list_patterns
    if _compiled_list_patterns is None:
        list_config = _get_list_query_config()
        patterns = list_config.get("list_patterns", [])
        _compiled_list_patterns = [re.compile(p) for p in patterns]
    return _compiled_list_patterns


# =============================================================================
# Ambiguity-Safe Query Routing (Phase 4 Gap C)
# =============================================================================

# =============================================================================
# Config-driven routing pattern loading
# =============================================================================

def _get_routing_config() -> dict:
    """Load routing configuration from taxonomy config with hardcoded fallbacks."""
    try:
        return settings.get_taxonomy_config().get("routing", {})
    except Exception:
        return {}


def _get_doc_reference_patterns() -> list[str]:
    """Get strong document reference patterns from config."""
    defaults = [
        r"\badr[.\s-]?\d{1,4}\b",
        r"\bpcp[.\s-]?\d{1,4}\b",
        r"\bprinciple[.\s-]?\d{1,4}\b",
        r"\badr\s+number\s+\d+\b",
        r"\bdecision\s+\d+\b",
    ]
    return _get_routing_config().get("doc_reference_patterns", defaults)


def _get_doc_request_phrases() -> list[str]:
    """Get weak document request phrases from config."""
    defaults = [
        r"about\s+(adr|decision)",
        r"details?\s+(of|for|about)",
        r"explain\s+(adr|decision)",
        r"what\s+does\s+adr",
        r"tell\s+me\s+about",
    ]
    return _get_routing_config().get("doc_request_phrases", defaults)


def _get_terminology_pattern_list() -> list[str]:
    """Get terminology patterns from config."""
    defaults = [
        r"what\s+is\s+(a\s+|an\s+)?(\w+)",
        r"define\s+(\w+)",
        r"definition\s+of\s+(\w+)",
        r"what\s+does\s+(\w+)\s+mean",
        r"explain\s+(the\s+)?term\s+(\w+)",
        r"meaning\s+of\s+(\w+)",
    ]
    return _get_routing_config().get("terminology_patterns", defaults)


def _get_vocab_keywords() -> list[str]:
    """Get vocabulary keywords from config."""
    defaults = ["vocab", "vocabulary", "definition", "term", "concept", "meaning", "cim", "iec", "skos"]
    return _get_routing_config().get("vocab_keywords", defaults)


def _get_markers(marker_name: str) -> list[str]:
    """Get marker list from config."""
    defaults = {
        "list_intent": ["list", "show", "all", "exist", "exists", "available", "have", "many", "which", "enumerate"],
        "count_intent": ["how many", "total number of", "count", "number of"],
        "approval_intent": ["who approved", "approved by", "approvers", "approval", "who signed", "signed off", "reviewed by"],
        "topical_intent": ["about", "status", "consequences", "decision drivers", "context", "what does it say", "explain", "details", "regarding", "concerning"],
    }
    markers = _get_routing_config().get("markers", {})
    return markers.get(marker_name, defaults.get(marker_name, []))


# Patterns that indicate a SPECIFIC document reference (detail query, NOT list)
# Loaded from config: strong references + weak phrases combined for backward compat
_SPECIFIC_DOC_PATTERNS = None  # Lazy-loaded

def _load_specific_doc_patterns() -> list[str]:
    """Load and combine doc reference patterns and request phrases."""
    return _get_doc_reference_patterns() + _get_doc_request_phrases()


# Compiled patterns cache
_compiled_specific_patterns: list | None = None
_compiled_reference_patterns: list | None = None


def _get_compiled_specific_patterns() -> list:
    """Get cached compiled patterns for specific document detection."""
    global _compiled_specific_patterns
    if _compiled_specific_patterns is None:
        patterns = _load_specific_doc_patterns()
        _compiled_specific_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
    return _compiled_specific_patterns


def invalidate_pattern_caches():
    """Invalidate all compiled pattern caches.

    Call this after config changes to force patterns to be reloaded.
    Also invalidates the config-level caches via invalidate_config_caches().
    """
    global _compiled_specific_patterns, _compiled_reference_patterns
    global _compiled_list_patterns, _compiled_terminology_patterns
    _compiled_specific_patterns = None
    _compiled_reference_patterns = None
    _compiled_list_patterns = None
    _compiled_terminology_patterns = None

    from .config import invalidate_config_caches
    invalidate_config_caches()


def _is_specific_document_query(question: str) -> bool:
    """Check if query references a specific document (not a list request).

    Args:
        question: The user's question

    Returns:
        True if query references a specific document (ADR.0031, etc.)
    """
    for pattern in _get_compiled_specific_patterns():
        if pattern.search(question):
            return True
    return False


# =============================================================================
# Terminology Query Detection (Phase 5 Gap A)
# =============================================================================

# Compiled terminology patterns cache (loaded from config)
_compiled_terminology_patterns: list | None = None


def _get_compiled_terminology_patterns() -> list:
    """Get cached compiled patterns for terminology query detection."""
    global _compiled_terminology_patterns
    if _compiled_terminology_patterns is None:
        _compiled_terminology_patterns = [
            re.compile(p, re.IGNORECASE) for p in _get_terminology_pattern_list()
        ]
    return _compiled_terminology_patterns


def _is_decision_or_reasoning_query(question: str) -> bool:
    """Check if the query is asking about an architecture decision or reasoning.

    These queries should NOT be treated as vocabulary/terminology lookups even
    if they contain vocab keywords (e.g., "CIM", "IEC") or match "what is"
    patterns.
    """
    question_lower = question.lower()

    # Reasoning indicators: "why was X chosen", "how should", "what was decided"
    reasoning_phrases = [
        "why was", "why is", "why did", "why does",
        "how should", "how was", "how is",
        "chosen", "decided", "selected", "adopted",
        "architecture decision", "architectural decision",
        "decision about", "decision on",
    ]
    if any(phrase in question_lower for phrase in reasoning_phrases):
        return True

    # Explicit ADR/principle reference patterns
    if re.search(r'\b(adr|pcp|principle)[.\s-]?\d', question_lower):
        return True

    return False


def _has_esa_cues(question: str) -> bool:
    """Check whether the question contains Energy System Architecture cues.

    Returns True if the query references ESA document types, standards,
    organisations, or technical domains.  Used to gate ESA-specific
    routing (vocabulary, lists, cross-domain) so that general-purpose
    questions don't get pulled into the ESA pipeline.
    """
    q = question.lower()

    # Document type keywords
    if re.search(r"\b(adrs?|dars?|pcps?|principles?|polic(?:y|ies))\b", q):
        return True

    # Standard references (IEC, CIM, SKOS, ArchiMate, CGMES, CIMXML, etc.)
    if re.search(r"\b(iec|cim|skos|archimate|cgmes|cimxml|rdf|ttl|sparql)\b", q):
        return True

    # ESA domain keywords
    esa_keywords = [
        "architecture decision", "data governance", "energy system",
        "alliander", "esa", "ainstein", "knowledge base",
        "demandable capacity", "sign convention", "grid",
        "approval record", "approval",
    ]
    if any(kw in q for kw in esa_keywords):
        return True

    # Explicit document references like ADR.0025, PCP.10
    if re.search(r'\b(adr|pcp|dar)[.\s-]?\d', q):
        return True

    # CamelCase / PascalCase identifiers (12+ chars total with mixed case)
    # These are likely CIM/IEC class names: PowerTransformer, TopologicalNode, etc.
    # The 12-char minimum avoids false positives on common words (JavaScript, TypeScript).
    if re.search(r'\b(?=[A-Za-z]{12,})[A-Z][a-z]+[A-Z]\w+\b', question):
        return True

    # Short CamelCase with AC/DC prefix (ACLine, DCSwitch, etc.)
    if re.search(r'\b[AD]C[A-Z][a-z]\w+\b', question):
        return True

    return False




def is_terminology_query(question: str) -> bool:
    """Check if query is asking about terminology/definitions.

    Args:
        question: The user's question

    Returns:
        True if query is asking about technical terms or definitions
    """
    # Early exit: decision/reasoning queries are never terminology queries
    if _is_decision_or_reasoning_query(question):
        return False

    question_lower = question.lower()

    # Strong vocabulary keywords that are inherently ESA-scoped
    # These fire even without additional ESA cues
    _strong_vocab = {"cim", "iec", "skos", "archimate", "vocabulary", "vocab"}
    if any(kw in question_lower for kw in _strong_vocab):
        return True

    # For broader patterns (e.g., "what is X"), require ESA cues
    # to avoid pulling general questions into the SKOSMOS pipeline
    if not _has_esa_cues(question):
        return False

    # Check explicit terminology patterns
    for pattern in _get_compiled_terminology_patterns():
        if pattern.search(question):
            return True

    # Check for vocabulary keywords (from config)
    if any(indicator in question_lower for indicator in _get_vocab_keywords()):
        return True

    return False


def verify_terminology_in_query(question: str, request_id: str | None = None) -> tuple[bool, str, list[TermLookupResult]]:
    """Verify technical terms in a query using SKOSMOS.

    This function extracts technical terms from the query and verifies them
    against the SKOSMOS vocabulary. If any term cannot be verified and the
    query is specifically about that term, the system should abstain.

    Enterprise-grade behavior for terminology queries:
    - If extracted terms exist and none verify: abstain (per IR0003)
    - If no terms extracted from terminology query: abstain (suspicious)

    Args:
        question: The user's question
        request_id: Optional request ID for logging

    Returns:
        Tuple of (should_abstain, abstain_reason, verification_results)
    """
    skosmos = get_skosmos_client()

    # Verify all technical terms in the query
    results = skosmos.verify_query_terms(question, request_id)

    # If this is a terminology query, apply strict verification
    if is_terminology_query(question):
        # Case 1: No terms extracted - terminology query but we couldn't identify the term
        # This is suspicious; abstain rather than guessing
        if not results:
            obs_metrics.increment("rag_abstention_total", labels={"reason": "terminology_extraction_empty"})
            return True, "Could not identify the technical term in this terminology query.", results

        # Case 2: Terms extracted but unverified - abstain with specific reason
        unverified = [r for r in results if r.should_abstain]
        if unverified:
            # Take the first unverified term's reason
            reason = unverified[0].abstain_reason
            obs_metrics.increment("rag_abstention_total", labels={"reason": "terminology_not_verified"})
            return True, reason, results

        # Case 3: All extracted terms are verified - proceed
        # (At least one term found and verified)

    return False, "", results


class ListQueryResult:
    """Result of list query detection with confidence level."""

    def __init__(self, is_list: bool, confidence: str, reason: str):
        """
        Args:
            is_list: Whether this is a list query
            confidence: "high", "medium", or "low"
            reason: Human-readable explanation
        """
        self.is_list = is_list
        self.confidence = confidence
        self.reason = reason

    def __bool__(self):
        """Allow using result directly in boolean context for backward compat."""
        return self.is_list

    def __repr__(self):
        return f"ListQueryResult(is_list={self.is_list}, confidence='{self.confidence}', reason='{self.reason}')"


def detect_list_query(question: str) -> ListQueryResult:
    """Detect if the query is asking for a comprehensive listing/catalog.

    This is the advanced version with confidence levels and ambiguity handling.

    Decision logic (from ESA_DOCUMENT_TAXONOMY.md):
    1. If specific document pattern found -> NOT a list (high confidence)
    2. If topical/semantic markers found -> NOT a list (semantic route)
    3. If list keyword + no specific doc + no topic -> IS a list (high confidence)
    4. If list pattern matches + no specific doc -> IS a list (medium confidence)
    5. Otherwise -> NOT a list (high confidence)

    Args:
        question: The user's question

    Returns:
        ListQueryResult with is_list, confidence, and reason
    """
    question_lower = question.lower()

    # Priority 1: Check for specific document references (takes precedence)
    if _is_specific_document_query(question):
        return ListQueryResult(
            is_list=False,
            confidence="high",
            reason="specific_document_reference"
        )

    # Priority 2: Check for topical/semantic markers (from config routing.markers.topical_intent)
    # These indicate semantic content queries, not "what exists" queries
    topical_markers = _get_markers("topical_intent")
    has_topical_marker = any(marker in question_lower for marker in topical_markers)

    list_config = _get_list_query_config()
    list_indicators = set(list_config.get("list_indicators", []))

    query_words = set(question_lower.split())

    # Priority 3: Check for strong list indicators
    # "list", "enumerate", "all" are strong indicators
    strong_list_words = {"list", "enumerate", "all"}
    if query_words & strong_list_words:
        # If topical marker is present, this is a semantic query not a list
        if has_topical_marker:
            return ListQueryResult(
                is_list=False,
                confidence="medium",
                reason="list_with_topic_filter"
            )

        return ListQueryResult(
            is_list=True,
            confidence="high",
            reason="strong_list_indicator"
        )

    # Priority 4: Check other list indicators (show, exist, etc.)
    if query_words & list_indicators:
        # If topical marker is present, this is a semantic query not a list
        if has_topical_marker:
            return ListQueryResult(
                is_list=False,
                confidence="medium",
                reason="list_with_topic_filter"
            )

        return ListQueryResult(
            is_list=True,
            confidence="medium",
            reason="list_indicator_keyword"
        )

    # Priority 5: Check regex patterns
    for pattern in _get_compiled_list_patterns():
        if pattern.search(question_lower):
            # If topical marker is present, this is a semantic query not a list
            if has_topical_marker:
                return ListQueryResult(
                    is_list=False,
                    confidence="medium",
                    reason="list_with_topic_filter"
                )

            return ListQueryResult(
                is_list=True,
                confidence="medium",
                reason="list_pattern_match"
            )

    # Default: Not a list query
    return ListQueryResult(
        is_list=False,
        confidence="high",
        reason="no_list_indicators"
    )


def is_list_query(question: str) -> bool:
    """Detect if the query is asking for a comprehensive listing/catalog.

    List queries ask "what exists" rather than asking about specific content.
    For these queries, we should fetch all matching documents and be transparent
    about the total count.

    This function provides backward compatibility while using the enhanced
    detect_list_query() internally. For new code, prefer detect_list_query()
    which provides confidence levels.

    Args:
        question: The user's question

    Returns:
        True if this is a list/catalog query, False for semantic/specific queries
    """
    result = detect_list_query(question)

    # Only route to list path for high/medium confidence list queries
    # Low confidence should go to semantic path for LLM interpretation
    if result.confidence == "low":
        return False

    return result.is_list


# =============================================================================
# Structured Response Post-Processing
# =============================================================================

# Enforcement policies for structured mode
ENFORCEMENT_STRICT = "strict"   # Retry once with JSON-only prompt, then fail
ENFORCEMENT_SOFT = "soft"       # Log and degrade to raw text

# Default enforcement policy (can be configured)
DEFAULT_ENFORCEMENT_POLICY = ENFORCEMENT_STRICT


def postprocess_llm_output(
    raw_response: str,
    structured_mode: bool,
    enforcement_policy: str = DEFAULT_ENFORCEMENT_POLICY,
    retry_func: callable = None,
) -> tuple[str, bool, str]:
    """Unified post-processing for LLM output with structured mode enforcement.

    This function MUST be called on ALL LLM outputs (main path and fallback path)
    to ensure consistent contract enforcement.

    In strict mode, if parsing fails and retry_func is provided, this function
    will attempt ONE retry with a JSON-only instruction before failing.

    Args:
        raw_response: The raw LLM response text
        structured_mode: Whether response-contract skill is active
        enforcement_policy: "strict" (retry + fail) or "soft" (degrade gracefully)
        retry_func: Optional function to call for retry. Receives RETRY_PROMPT
                    as input and should return the LLM's retry response.

    Returns:
        Tuple of:
        - processed_response: The final response text to display
        - was_structured: Whether structured parsing succeeded
        - reason: Reason code for debugging ("success", "fallback", "parse_failed", etc.)
    """
    from .response_gateway import RETRY_PROMPT

    logger = logging.getLogger(__name__)

    if not structured_mode:
        # Not in structured mode - return raw response as-is
        return raw_response, False, "not_structured_mode"

    # Attempt to parse structured response
    structured, fallback_used = ResponseParser.parse_with_fallbacks(raw_response)

    if structured:
        # Success! Generate processed response with transparency
        logger.info(f"Structured response parsed successfully via {fallback_used}")
        transparency = structured.generate_transparency_message()
        if transparency and transparency not in structured.answer:
            processed = f"{structured.answer}\n\n{transparency}"
        else:
            processed = structured.answer
        return processed, True, "success"

    # Parsing failed
    logger.warning(f"Structured response parsing failed: {fallback_used}")

    if enforcement_policy == ENFORCEMENT_SOFT:
        # Soft mode: log and degrade to raw text
        logger.info("Soft enforcement: degrading to raw response")
        return raw_response, False, f"soft_fallback:{fallback_used}"

    # Strict mode: attempt retry if retry_func is provided
    if retry_func is not None:
        logger.info("Strict enforcement: attempting retry with JSON-only instruction")
        try:
            # Call retry_func with the JSON-only prompt
            retry_response = retry_func(RETRY_PROMPT)

            # Attempt to parse the retry response
            retry_structured, retry_fallback = ResponseParser.parse_with_fallbacks(retry_response)

            if retry_structured:
                # Retry succeeded!
                logger.info(f"Retry succeeded via {retry_fallback}")
                transparency = retry_structured.generate_transparency_message()
                if transparency and transparency not in retry_structured.answer:
                    processed = f"{retry_structured.answer}\n\n{transparency}"
                else:
                    processed = retry_structured.answer
                return processed, True, f"retry_success:{retry_fallback}"

            # Retry parsing also failed
            logger.warning(f"Retry parsing failed: {retry_fallback}")

        except Exception as e:
            logger.error(f"Retry function raised exception: {e}")

    # Strict mode without successful retry: degrade gracefully to raw text
    # Never leak internal formatting failures to the user (P0 fix)
    # Sanitize to strip protocol artifacts (delimiters, schema fields)
    from .response_gateway import sanitize_raw_fallback
    logger.warning(
        f"Strict enforcement failed: unable to parse structured response. "
        f"Degrading to raw text. (fallback: {fallback_used})"
    )
    return sanitize_raw_fallback(raw_response), False, f"strict_fallback:{fallback_used}"


def get_collection_count(collection, content_filter=None) -> int:
    """Get the total count of documents in a collection, optionally filtered.

    Args:
        collection: Weaviate collection object
        content_filter: Optional filter to apply

    Returns:
        Total count of matching documents
    """
    try:
        aggregate = collection.aggregate.over_all(
            total_count=True,
            filters=content_filter
        )
        return aggregate.total_count
    except Exception as e:
        coll_name = getattr(collection, 'name', 'unknown')
        logger.warning(
            f"Failed to get collection count for {coll_name} "
            f"(filter={'applied' if content_filter else 'none'}): {e}"
        )
        return 0


def fetch_all_objects(collection, filters=None, return_properties: list[str] = None, page_size: int = 100) -> list:
    """Fetch ALL objects from a collection with pagination.

    Unlike fetch_objects with a fixed limit, this function pages through
    the entire collection to ensure complete results for deterministic
    list operations.

    Args:
        collection: Weaviate collection object
        filters: Optional filter to apply
        return_properties: Properties to return
        page_size: Number of objects per page (default 100)

    Returns:
        List of all matching Weaviate objects
    """
    all_objects = []
    offset = 0

    while True:
        results = collection.query.fetch_objects(
            limit=page_size,
            offset=offset,
            filters=filters,
            return_properties=return_properties,
        )

        if not results.objects:
            break

        all_objects.extend(results.objects)
        offset += page_size

        # Safety limit to prevent infinite loops (10k objects max)
        if offset >= 10000:
            logger.warning(f"fetch_all_objects hit safety limit at {offset} objects")
            break

    return all_objects


def should_abstain(query: str, results: list) -> tuple[bool, str]:
    """Determine if the system should abstain from answering.

    Checks retrieval quality signals to prevent hallucination when
    no relevant documents are found. Thresholds are loaded from
    skill configuration.

    Args:
        query: The user's question
        results: List of retrieved documents with distance/score metadata

    Returns:
        Tuple of (should_abstain: bool, reason: str)
    """
    # Load thresholds from skill configuration
    distance_threshold, min_query_coverage = _get_abstention_thresholds()

    # No results at all
    if not results:
        return True, "No relevant documents found in the knowledge base."

    # Check if any result has acceptable distance
    distances = [r.get("distance") for r in results if r.get("distance") is not None]
    if distances:
        min_distance = min(distances)
        if min_distance > distance_threshold:
            return True, f"No sufficiently relevant documents found (best match distance: {min_distance:.2f})."

    # Check for specific ADR queries - must find the exact ADR
    adr_match = re.search(r'adr[- ]?0*(\d+)', query.lower())
    if adr_match:
        adr_num = adr_match.group(1).zfill(4)
        adr_found = any(
            f"adr-{adr_num}" in str(r.get("title", "")).lower() or
            f"adr-{adr_num}" in str(r.get("content", "")).lower()
            for r in results
        )
        if not adr_found:
            return True, f"ADR-{adr_num} was not found in the knowledge base."

    # Load list query detection config from skill
    list_config = _get_list_query_config()
    list_indicators = set(list_config.get("list_indicators", []))
    list_patterns = list_config.get("list_patterns", [])
    additional_stop_words = set(list_config.get("additional_stop_words", []))

    # Detect LIST-type queries (asking for enumeration/listing)
    # These queries ask "what exists" rather than asking about specific content
    query_lower = query.lower()
    query_words = set(query_lower.split())
    is_list_query = bool(query_words & list_indicators)

    # Also detect patterns like "What ADRs..." or "What principles..."
    if not is_list_query:
        is_list_query = any(re.search(p, query_lower) for p in list_patterns)

    # For LIST queries with good distance scores, skip coverage check
    # The query terms won't appear in documents (e.g., "exist" won't be in ADR titles)
    if is_list_query and distances and min(distances) <= distance_threshold:
        return False, "OK"

    # Check query term coverage in results
    # Extract meaningful terms (skip common words, clean punctuation)
    base_stop_words = {"what", "is", "the", "a", "an", "of", "in", "to", "for", "and", "or", "how", "does", "do", "about", "our"}
    stop_words = base_stop_words | additional_stop_words
    # Clean punctuation from terms
    query_terms = [re.sub(r'[^\w]', '', t) for t in query_lower.split()]
    query_terms = [t for t in query_terms if t not in stop_words and len(t) > 2]

    if query_terms:
        results_text = " ".join(
            str(r.get("title", "")) + " " + str(r.get("content", "")) + " " +
            str(r.get("label", "")) + " " + str(r.get("definition", ""))
            for r in results
        ).lower()

        terms_found = sum(1 for t in query_terms if t in results_text)
        coverage = terms_found / len(query_terms) if query_terms else 0

        if coverage < min_query_coverage:
            return True, f"Query terms not well covered by retrieved documents (coverage: {coverage:.0%})."

    return False, "OK"


def get_abstention_response(reason: str) -> str:
    """Generate a helpful abstention response.

    Args:
        reason: The reason for abstaining

    Returns:
        User-friendly abstention message
    """
    return f"""I don't have sufficient information to answer this question.

**Reason:** {reason}

**Suggestions:**
- Try rephrasing your question with different terms
- Check if the topic exists in our knowledge base
- For terminology questions, verify the term exists in SKOSMOS

If you believe this information should be available, please contact the ESA team to have it added to the knowledge base."""


logger = logging.getLogger(__name__)

# Import elysia components
try:
    import elysia
    from elysia import tool, Tree
    ELYSIA_AVAILABLE = True
except ImportError as e:
    ELYSIA_AVAILABLE = False
    logger.warning(f"elysia-ai import failed: {e}")
except Exception as e:
    ELYSIA_AVAILABLE = False
    logger.warning(f"elysia-ai error: {e}")


# =============================================================================
# Semantic Response Cache (TTL-based, model-aware)
# =============================================================================

import time as _time

_RESPONSE_CACHE: dict[tuple, tuple[str, list, float]] = {}
"""Cache: (question, provider, model) → (response, objects, timestamp)."""

_CACHE_TTL_SECONDS = 300  # 5 minutes
_CACHE_MAX_SIZE = 100


def _cache_get(question: str) -> tuple[str, list] | None:
    """Get a cached response if it exists and is within TTL."""
    key = (question.strip().lower(), settings.llm_provider, settings.chat_model)
    entry = _RESPONSE_CACHE.get(key)
    if entry is None:
        return None
    response, objects, ts = entry
    if _time.time() - ts > _CACHE_TTL_SECONDS:
        del _RESPONSE_CACHE[key]
        return None
    return response, objects


def _cache_put(question: str, response: str, objects: list) -> None:
    """Store a response in the cache."""
    # Evict oldest entries if cache is full
    if len(_RESPONSE_CACHE) >= _CACHE_MAX_SIZE:
        oldest_key = min(_RESPONSE_CACHE, key=lambda k: _RESPONSE_CACHE[k][2])
        del _RESPONSE_CACHE[oldest_key]
    key = (question.strip().lower(), settings.llm_provider, settings.chat_model)
    _RESPONSE_CACHE[key] = (response, objects, _time.time())


# =============================================================================
# Elysia Model Configuration
# =============================================================================

_elysia_configured = False
"""Module-level flag tracking whether configure_elysia_from_settings() has run."""

_elysia_config_signature: tuple | None = None
"""Signature of (provider, model, api_base) used for the last configure call."""


def configure_elysia_from_settings() -> None:
    """Wire AInstein model settings into Elysia's config singleton.

    Call this once at the composition root (CLI / API / test startup)
    **before** creating any ``ElysiaRAGSystem`` instance.  Uses
    ``replace=True`` so no ``smart_setup()`` / env-var defaults leak.

    Idempotent: subsequent calls with the *same* settings are no-ops.
    Raises ``RuntimeError`` if called again with *different* settings
    (prevents silent mid-process reconfiguration).
    """
    global _elysia_configured, _elysia_config_signature

    from .config import settings as ainstein_settings

    provider = ainstein_settings.llm_provider   # "openai" or "ollama"
    model = ainstein_settings.chat_model         # resolved per provider
    api_base = ainstein_settings.ollama_url if provider == "ollama" else None
    new_signature = (provider, model, api_base)

    # Idempotency: same config → no-op; different config → reject
    if _elysia_configured:
        if _elysia_config_signature == new_signature:
            return
        raise RuntimeError(
            f"Elysia already configured with {_elysia_config_signature}, "
            f"refusing to reconfigure with {new_signature}. "
            f"This likely indicates a settings mutation mid-process."
        )

    try:
        from elysia.config import settings as elysia_settings
    except ImportError:
        logger.warning("Cannot import elysia.config — skipping model wiring")
        return

    configure_kwargs: dict = {}

    if provider == "openai":
        configure_kwargs = {
            "base_model": model,
            "base_provider": "openai",
            "complex_model": model,
            "complex_provider": "openai",
        }
    elif provider == "ollama":
        configure_kwargs = {
            "base_model": model,
            "base_provider": "ollama",
            "complex_model": model,
            "complex_provider": "ollama",
            "model_api_base": api_base,
        }

    if configure_kwargs:
        elysia_settings.configure(replace=True, **configure_kwargs)
        _elysia_configured = True
        _elysia_config_signature = new_signature
        logger.info(
            "Elysia configured: provider=%s, base_model=%s, complex_model=%s",
            provider,
            elysia_settings.BASE_MODEL,
            elysia_settings.COMPLEX_MODEL,
        )


class ElysiaRAGSystem:
    """Elysia-based agentic RAG system with custom tools for energy domain.

    Thread Safety:
        This class creates a new Tree instance per request to avoid race conditions
        when modifying agent descriptions in concurrent scenarios. The tool functions
        are stored in a registry and registered on each per-request Tree.
    """

    def __init__(self, client: WeaviateClient):
        """Initialize the Elysia RAG system.

        Args:
            client: Connected Weaviate client
        """
        if not ELYSIA_AVAILABLE:
            raise ImportError("elysia-ai package is required. Run: pip install elysia-ai")

        # Safety net: if the caller forgot to call configure_elysia_from_settings()
        # at the composition root.
        #   - prod/staging: fail fast (mis-wiring must be caught before deployment)
        #   - local/dev:    warn + auto-configure (developer convenience)
        if not _elysia_configured:
            from .config import settings as _cfg
            if _cfg.environment in ("prod", "staging"):
                raise RuntimeError(
                    "ElysiaRAGSystem created without prior call to "
                    "configure_elysia_from_settings(). Fix the composition root."
                )
            logger.warning(
                "Elysia model config was not applied before ElysiaRAGSystem(). "
                "Applying now as fallback — call configure_elysia_from_settings() "
                "at your entrypoint to silence this warning."
            )
            configure_elysia_from_settings()

        self.client = client
        self._recursion_limit = 2

        # Base agent description for AInstein - skills will be injected dynamically per query
        self._base_agent_description = """You are AInstein, the Energy System Architecture AI Assistant at Alliander.

Your role is to help architects, engineers, and stakeholders navigate Alliander's energy system architecture knowledge base, including:
- Architectural Decision Records (ADRs)
- Data governance principles and policies
- IEC/CIM vocabulary and standards

IMPORTANT GUIDELINES:
- When referencing ADRs, use the format ADR.XX (e.g., ADR.21)
- When referencing Principles, use the format PCP.XX (e.g., PCP.10)
- For technical terms, provide clear explanations
- Be transparent about the data: always indicate how many items exist vs. how many are shown
- Never hallucinate - if you're not confident, say so"""

        # Build tool registry (functions to register on per-request trees)
        self._tool_registry = self._build_tool_registry()

    def _create_tree(self, agent_description: str) -> Tree:
        """Create and configure a new Elysia Tree instance.

        Creates a fresh tree per request to avoid race conditions
        when modifying agent descriptions in concurrent scenarios.

        Args:
            agent_description: Full agent description including skill content

        Returns:
            Configured Tree instance with all tools registered
        """
        tree = Tree(
            agent_description=agent_description,
            style="Professional, concise, and informative. Use structured formatting for lists.",
            end_goal="Provide accurate, well-sourced answers based on the knowledge base."
        )

        # Limit recursion to prevent infinite loops in decision tree
        tree.tree_data.recursion_limit = self._recursion_limit

        # Register all tools on this tree instance
        for name, func in self._tool_registry.items():
            tool(tree=tree)(func)
            logger.debug(f"Registered tool on tree: {name}")

        return tree

    def _build_tool_registry(self) -> dict[str, callable]:
        """Build registry of tool functions for Elysia trees.

        Returns tool functions that can be registered on any Tree instance.
        Tools are not decorated here - they get decorated when registered on a tree.

        Returns:
            Dict mapping tool names to their async functions
        """
        registry = {}

        # Load truncation limits from skill configuration for tool responses
        truncation = _skill_registry.loader.get_truncation(DEFAULT_SKILL)
        content_max_chars = truncation.get("content_max_chars", 800)
        content_chars = truncation.get("elysia_content_chars", 500)
        summary_chars = truncation.get("elysia_summary_chars", 300)
        consequences_max_chars = truncation.get("consequences_max_chars", 4000)

        # Capture self.client for closures
        client = self.client

        # Vocabulary/SKOS search tool
        async def search_vocabulary(query: str, limit: int = 5) -> list[dict]:
            """Search SKOS vocabulary concepts from IEC standards (CIM, 61970, 61968, 62325).

            Use this tool when the user asks about:
            - Energy sector terminology and definitions
            - CIM (Common Information Model) concepts
            - IEC standards (61970, 61968, 62325, 62746)
            - SKOS concepts, vocabularies, or ontologies
            - Technical terms and their meanings

            Args:
                query: Search query for vocabulary concepts
                limit: Maximum number of results to return

            Returns:
                List of matching vocabulary concepts with definitions
            """
            collection = client.collections.get(get_collection_name("vocabulary"))
            query_vector = embed_text(query)
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
            )
            return [
                {
                    "label": obj.properties.get("pref_label", ""),
                    "definition": obj.properties.get("definition", ""),
                    "vocabulary": obj.properties.get("vocabulary_name", ""),
                    "uri": obj.properties.get("uri", ""),
                }
                for obj in results.objects
            ]

        registry["search_vocabulary"] = search_vocabulary

        # SKOSMOS terminology verification tool
        async def verify_terminology(term: str) -> dict:
            """Verify a technical term using SKOSMOS vocabulary lookup.

            Use this tool when the user asks:
            - What is ACLineSegment?
            - Define CIM
            - What does PowerTransformer mean?
            - Explain the term CIMXML

            This tool verifies terms against the local SKOSMOS vocabulary index
            loaded from IEC/CIM standards (61970, 61968, 62325).

            Args:
                term: The technical term to verify (e.g., "ACLineSegment", "CIM")

            Returns:
                Dictionary with verification status and definition if found
            """
            skosmos = get_skosmos_client()
            result = skosmos.lookup_term(term)

            if result.found:
                return {
                    "verified": True,
                    "term": result.term,
                    "label": result.label,
                    "definition": result.definition_text,
                    "vocabulary": result.definition.vocabulary_name if result.definition else "",
                    "source": result.source,
                }
            else:
                return {
                    "verified": False,
                    "term": result.term,
                    "should_abstain": result.should_abstain,
                    "reason": result.abstain_reason,
                }

        registry["verify_terminology"] = verify_terminology

        # ADR search tool
        async def search_architecture_decisions(query: str, limit: int = 5) -> list[dict]:
            """Search Architectural Decision Records (ADRs) for design decisions.

            Use this tool when the user asks about:
            - Architecture decisions and their rationale
            - Design choices and tradeoffs
            - Technical decisions and their context
            - ADRs or architectural records
            - System design patterns used

            Args:
                query: Search query for architecture decisions
                limit: Maximum number of results to return

            Returns:
                List of matching ADRs with context and decisions
            """
            collection = client.collections.get(get_collection_name("adr"))
            query_vector = embed_text(query)
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "adr_number": obj.properties.get("adr_number", ""),
                    "file_path": obj.properties.get("file_path", ""),
                    "status": obj.properties.get("status", ""),
                    "context": obj.properties.get("context", "")[:content_chars],
                    "decision": obj.properties.get("decision", "")[:content_chars],
                    "consequences": obj.properties.get("consequences", "")[:consequences_max_chars],
                }
                for obj in results.objects
            ]

        registry["search_architecture_decisions"] = search_architecture_decisions

        # Principles search tool
        async def search_principles(query: str, limit: int = 5) -> list[dict]:
            """Search architecture and governance principles.

            Use this tool when the user asks about:
            - Architecture principles and guidelines
            - Governance principles
            - Design principles and best practices
            - Standards and conventions

            Args:
                query: Search query for principles
                limit: Maximum number of results to return

            Returns:
                List of matching principles
            """
            collection = client.collections.get(get_collection_name("principle"))
            query_vector = embed_text(query)
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "principle_number": obj.properties.get("principle_number", ""),
                    "file_path": obj.properties.get("file_path", ""),
                    "content": obj.properties.get("content", "")[:content_max_chars],
                    "doc_type": obj.properties.get("doc_type", ""),
                }
                for obj in results.objects
            ]

        registry["search_principles"] = search_principles

        # Policy document search tool
        async def search_policies(query: str, limit: int = 5) -> list[dict]:
            """Search data governance and policy documents.

            Use this tool when the user asks about:
            - Data governance policies
            - Data quality requirements
            - Compliance and regulatory policies
            - Data management policies
            - Security and privacy policies

            Args:
                query: Search query for policy documents
                limit: Maximum number of results to return

            Returns:
                List of matching policy documents
            """
            collection = client.collections.get(get_collection_name("policy"))
            query_vector = embed_text(query)
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "file_path": obj.properties.get("file_path", ""),
                    "content": obj.properties.get("content", "")[:content_max_chars],
                    "file_type": obj.properties.get("file_type", ""),
                }
                for obj in results.objects
            ]

        registry["search_policies"] = search_policies

        # List all ADRs tool
        async def list_all_adrs() -> dict:
            """List all Architectural Decision Records in the system.

            Use this tool when the user asks:
            - What ADRs exist?
            - List all architecture decisions
            - Show me all ADRs
            - What decisions have been documented?

            Returns:
                Marked list result with deduplicated ADRs (document-identity based)
            """
            request_id = generate_request_id()
            collection = client.collections.get(get_collection_name("adr"))

            # Use allow-list filter (doc_type IN ["adr", "content"]) for server-side filtering
            # This approach excludes null/missing doc_type values and uses canonical taxonomy
            content_filter = build_document_filter(
                question="list all ADRs",
                skill_registry=_skill_registry,
                skill_name=DEFAULT_SKILL,
                collection_type="adr",
            )

            # Debug: Get unfiltered count to compare
            unfiltered_count = get_collection_count(collection, None)
            filtered_count = get_collection_count(collection, content_filter)
            logger.debug(
                f"list_all_adrs filter debug: unfiltered={unfiltered_count}, "
                f"filtered={filtered_count}, filter_applied={content_filter is not None}, "
                f"request_id={request_id}"
            )

            # Fallback logic with guardrails
            use_filter = content_filter
            fallback_triggered = False

            if filtered_count == 0 and unfiltered_count > 0:
                # Documents likely don't have doc_type set - check guardrails
                fallback_allowed, error_msg = check_fallback_allowed(
                    collection_size=unfiltered_count,
                    collection_type="adr",
                    query="list all ADRs",
                    request_id=request_id,
                )

                if not fallback_allowed:
                    # Return controlled error response
                    return {
                        "error": True,
                        "message": error_msg,
                        "request_id": request_id,
                        "reason": "DOC_METADATA_MISSING_REQUIRES_MIGRATION",
                    }

                # Fallback is allowed - proceed with in-memory filtering
                use_filter = None
                fallback_triggered = True

            # Fetch ALL objects with pagination to ensure complete deterministic results
            all_objects = fetch_all_objects(
                collection,
                filters=use_filter,
                return_properties=["title", "status", "file_path", "adr_number", "doc_type"],
            )

            # Debug: Log doc_type distribution
            doc_type_counts = {}
            for obj in all_objects:
                dt = obj.properties.get("doc_type", "None/missing")
                doc_type_counts[dt] = doc_type_counts.get(dt, 0) + 1
            if doc_type_counts:
                logger.debug(f"list_all_adrs doc_type distribution: {doc_type_counts}")

            adrs = []
            for obj in all_objects:
                title = obj.properties.get("title", "")
                file_path = obj.properties.get("file_path", "")
                doc_type = obj.properties.get("doc_type", "")
                file_name = file_path.lower() if file_path else ""

                # In-memory filtering when Weaviate filter couldn't be used
                # Skip: templates, index files, registry files, and decision approval records (DARs)
                if fallback_triggered or not doc_type:
                    if "template" in title.lower() or "template" in file_name:
                        continue
                    # Skip index.md (directory indexes) and esa_doc_registry.md (top-level registry)
                    # These are metadata/catalog files, not individual ADRs
                    if file_name.endswith("index.md") or file_name.endswith("readme.md"):
                        continue
                    if file_name.endswith("esa_doc_registry.md") or file_name.endswith("esa-doc-registry.md"):
                        continue
                    # DAR files match pattern: NNNND-*.md (e.g., 0021D-approval.md)
                    if re.match(r".*\d{4}d-.*\.md$", file_name):
                        continue

                adrs.append({
                    "title": title,
                    "adr_number": obj.properties.get("adr_number", ""),
                    "status": obj.properties.get("status", ""),
                    "file_path": file_path,
                    "doc_type": doc_type,
                })

            # Dedupe by file_path to get unique documents (not chunks)
            unique_adrs = dedupe_by_identity(adrs, identity_key="file_path")
            unique_adrs_sorted = sorted(
                unique_adrs,
                key=lambda x: x.get("adr_number", "") or x.get("file_path", "")
            )

            log_suffix = " (via fallback)" if fallback_triggered else " (filtered)"
            logger.info(
                f"list_all_adrs: Returning {len(unique_adrs_sorted)} unique ADRs{log_suffix} "
                f"(collection total: {unfiltered_count}, after filter: {filtered_count}, "
                f"chunks before dedupe: {len(adrs)}, request_id={request_id})"
            )

            # Return marker-based result for deterministic serialization
            # Pass fallback_triggered to enable transparency in response
            return build_list_result_marker(
                collection="adr",
                rows=unique_adrs_sorted,
                total_unique=len(unique_adrs_sorted),
                fallback_triggered=fallback_triggered,
            )

        registry["list_all_adrs"] = list_all_adrs

        # List all principles tool
        async def list_all_principles() -> dict:
            """List all architecture and governance principles.

            Use this tool when the user asks:
            - What principles exist?
            - List all principles
            - Show me the governance principles

            Returns:
                Marked list result with deduplicated principles (document-identity based)
            """
            request_id = generate_request_id()
            collection = client.collections.get(get_collection_name("principle"))
            # Use allow-list filter for server-side filtering with canonical taxonomy
            content_filter = build_document_filter(
                question="list all principles",
                skill_registry=_skill_registry,
                skill_name=DEFAULT_SKILL,
                collection_type="principle",
            )

            # Get counts for fallback logic
            unfiltered_count = get_collection_count(collection, None)
            filtered_count = get_collection_count(collection, content_filter)

            # Fallback logic with guardrails
            use_filter = content_filter
            fallback_triggered = False

            if filtered_count == 0 and unfiltered_count > 0:
                # Documents likely don't have doc_type set - check guardrails
                fallback_allowed, error_msg = check_fallback_allowed(
                    collection_size=unfiltered_count,
                    collection_type="principle",
                    query="list all principles",
                    request_id=request_id,
                )

                if not fallback_allowed:
                    # Return controlled error response
                    return {
                        "error": True,
                        "message": error_msg,
                        "request_id": request_id,
                        "reason": "DOC_METADATA_MISSING_REQUIRES_MIGRATION",
                    }

                # Fallback is allowed - proceed with in-memory filtering
                use_filter = None
                fallback_triggered = True

            # Fetch ALL objects with pagination to ensure complete deterministic results
            all_objects = fetch_all_objects(
                collection,
                filters=use_filter,
                return_properties=["title", "doc_type", "file_path", "principle_number"],
            )

            principles = []
            for obj in all_objects:
                title = obj.properties.get("title", "")
                doc_type = obj.properties.get("doc_type", "")
                file_path = obj.properties.get("file_path", "")
                file_name = file_path.lower() if file_path else ""

                # In-memory filtering when Weaviate filter couldn't be used
                # Skip: templates, index files, and registry files
                if fallback_triggered or not doc_type:
                    if "template" in title.lower() or "template" in file_name:
                        continue
                    # Skip index.md (directory indexes) and esa_doc_registry.md (top-level registry)
                    # These are metadata/catalog files, not individual principles
                    if file_name.endswith("index.md") or file_name.endswith("readme.md"):
                        continue
                    if file_name.endswith("esa_doc_registry.md") or file_name.endswith("esa-doc-registry.md"):
                        continue

                principles.append({
                    "title": title,
                    "principle_number": obj.properties.get("principle_number", ""),
                    "file_path": file_path,
                    "type": doc_type,
                })

            # Dedupe by file_path to get unique documents (not chunks)
            unique_principles = dedupe_by_identity(principles, identity_key="file_path")
            unique_principles_sorted = sorted(
                unique_principles,
                key=lambda x: x.get("principle_number", "") or x.get("file_path", "")
            )

            log_suffix = " (via fallback)" if fallback_triggered else " (filtered)"
            logger.info(
                f"list_all_principles: Returning {len(unique_principles_sorted)} unique principles{log_suffix} "
                f"(collection total: {unfiltered_count}, after filter: {filtered_count}, "
                f"chunks before dedupe: {len(principles)}, request_id={request_id})"
            )

            # Return marker-based result for deterministic serialization
            # Pass fallback_triggered to enable transparency in response
            return build_list_result_marker(
                collection="principle",
                rows=unique_principles_sorted,
                total_unique=len(unique_principles_sorted),
                fallback_triggered=fallback_triggered,
            )

        registry["list_all_principles"] = list_all_principles

        # List approval records for ADRs or Principles
        async def list_approval_records(collection_type: str = "all") -> dict:
            """List Decision Approval Records (DARs) for governance tracking.

            Use this tool when the user asks about:
            - Approval records for principles
            - Decision approval records
            - Who approved ADRs or principles
            - DACI records
            - Governance history

            Args:
                collection_type: Type to search - "adr", "principle", or "all"

            Returns:
                Marked list result with approval records
            """
            request_id = generate_request_id()
            results = []

            # Map collection type to Weaviate collection
            type_mapping = {
                "adr": [get_collection_name("adr")],
                "adrs": [get_collection_name("adr")],
                "principle": [get_collection_name("principle")],
                "principles": [get_collection_name("principle")],
                "all": [get_collection_name("adr"), get_collection_name("principle")],
            }

            collections_to_search = type_mapping.get(
                collection_type.lower(),
                [get_collection_name("adr"), get_collection_name("principle")],
            )

            for coll_name in collections_to_search:
                try:
                    collection = client.collections.get(coll_name)

                    # Filter for approval records — use correct type per collection
                    if coll_name == get_collection_name("principle"):
                        approval_filter = Filter.by_property("doc_type").equal("principle_approval")
                    else:
                        approval_filter = Filter.by_property("doc_type").equal("adr_approval")

                    # Fetch all approval records
                    all_objects = fetch_all_objects(
                        collection,
                        filters=approval_filter,
                        return_properties=["title", "doc_type", "file_path", "adr_number", "principle_number"],
                    )

                    for obj in all_objects:
                        record = {
                            "title": obj.properties.get("title", ""),
                            "file_path": obj.properties.get("file_path", ""),
                            "doc_type": obj.properties.get("doc_type", ""),
                            "collection": coll_name,
                        }
                        # Add identifier based on collection
                        if coll_name == get_collection_name("adr"):
                            record["adr_number"] = obj.properties.get("adr_number", "")
                        else:
                            record["principle_number"] = obj.properties.get("principle_number", "")
                        results.append(record)

                except Exception as e:
                    logger.warning(f"Error fetching approval records from {coll_name}: {e}")

            # Dedupe by file_path
            unique_results = dedupe_by_identity(results, identity_key="file_path")
            unique_sorted = sorted(
                unique_results,
                key=lambda x: x.get("file_path", "")
            )

            logger.info(
                f"list_approval_records: Found {len(unique_sorted)} unique approval records "
                f"(collection_type={collection_type}, request_id={request_id})"
            )

            return build_list_result_marker(
                collection="approval_records",
                rows=unique_sorted,
                total_unique=len(unique_sorted),
                fallback_triggered=False,
            )

        registry["list_approval_records"] = list_approval_records

        # List all policy documents tool
        async def list_all_policies() -> dict:
            """List all data governance policy documents in the system.

            Use this tool when the user asks:
            - What policies exist?
            - List all policies
            - Show me the data governance policies
            - What data governance documents are there?

            Returns:
                Marked list result with deduplicated policy documents
            """
            request_id = generate_request_id()
            collection = client.collections.get(get_collection_name("policy"))

            # PolicyDocument has no doc_type property — always fetch unfiltered
            total_count = get_collection_count(collection, None)

            all_objects = fetch_all_objects(
                collection,
                filters=None,
                return_properties=["title", "file_path", "file_type"],
            )

            policies = []
            for obj in all_objects:
                policies.append({
                    "title": obj.properties.get("title", ""),
                    "file_path": obj.properties.get("file_path", ""),
                    "file_type": obj.properties.get("file_type", ""),
                })

            # Dedupe by file_path
            unique_policies = dedupe_by_identity(policies, identity_key="file_path")
            unique_policies_sorted = sorted(
                unique_policies,
                key=lambda x: x.get("title", "") or x.get("file_path", "")
            )

            logger.info(
                f"list_all_policies: Returning {len(unique_policies_sorted)} unique policies "
                f"(collection total: {total_count}, chunks before dedupe: {len(policies)}, "
                f"request_id={request_id})"
            )

            return build_list_result_marker(
                collection="policy",
                rows=unique_policies_sorted,
                total_unique=len(unique_policies_sorted),
                fallback_triggered=False,
            )

        registry["list_all_policies"] = list_all_policies

        # Search documents by team/owner
        async def search_by_team(team_name: str, query: str = "", limit: int = 10) -> list[dict]:
            """Search all documents owned by a specific team or workgroup.

            Use this tool when the user asks about documents from a specific team:
            - What documents does ESA/Energy System Architecture have?
            - Show me Data Office documents
            - What are the ESA principles and ADRs?
            - Documents from System Operations team

            Args:
                team_name: Team name or abbreviation
                query: Optional search query to filter results
                limit: Maximum number of results per collection

            Returns:
                List of documents with their type, title, and owner info
            """
            results = []

            # Search ADRs
            try:
                adr_collection = client.collections.get(get_collection_name("adr"))
                if query:
                    search_query = f"{team_name} {query}"
                    query_vector = embed_text(search_query)
                    adr_results = adr_collection.query.hybrid(
                        query=search_query,
                        vector=query_vector,
                        limit=limit,
                        alpha=settings.alpha_default,
                    )
                else:
                    adr_results = adr_collection.query.fetch_objects(
                        limit=limit * 2,
                        return_properties=["title", "status", "owner_team", "owner_team_abbr", "owner_display"],
                    )

                for obj in adr_results.objects:
                    owner = obj.properties.get("owner_team", "") or obj.properties.get("owner_team_abbr", "")
                    owner_display = obj.properties.get("owner_display", "")
                    if team_name.lower() in owner.lower() or team_name.lower() in owner_display.lower():
                        results.append({
                            "type": "ADR",
                            "title": obj.properties.get("title", ""),
                            "status": obj.properties.get("status", ""),
                            "owner": owner_display or owner,
                        })
            except Exception as e:
                logger.warning(f"Error searching ADRs by team: {e}")

            # Search Principles
            try:
                principle_collection = client.collections.get(get_collection_name("principle"))
                if query:
                    search_query = f"{team_name} {query}"
                    query_vector = embed_text(search_query)
                    principle_results = principle_collection.query.hybrid(
                        query=search_query,
                        vector=query_vector,
                        limit=limit,
                        alpha=settings.alpha_default,
                    )
                else:
                    principle_results = principle_collection.query.fetch_objects(
                        limit=limit * 2,
                        return_properties=["title", "doc_type", "owner_team", "owner_team_abbr", "owner_display"],
                    )

                for obj in principle_results.objects:
                    owner = obj.properties.get("owner_team", "") or obj.properties.get("owner_team_abbr", "")
                    owner_display = obj.properties.get("owner_display", "")
                    if team_name.lower() in owner.lower() or team_name.lower() in owner_display.lower():
                        results.append({
                            "type": "Principle",
                            "title": obj.properties.get("title", ""),
                            "doc_type": obj.properties.get("doc_type", ""),
                            "owner": owner_display or owner,
                        })
            except Exception as e:
                logger.warning(f"Error searching Principles by team: {e}")

            # Search Policies
            try:
                policy_collection = client.collections.get(get_collection_name("policy"))
                if query:
                    search_query = f"{team_name} {query}"
                    query_vector = embed_text(search_query)
                    policy_results = policy_collection.query.hybrid(
                        query=search_query,
                        vector=query_vector,
                        limit=limit,
                        alpha=settings.alpha_default,
                    )
                else:
                    policy_results = policy_collection.query.fetch_objects(
                        limit=limit * 2,
                        return_properties=["title", "file_type", "owner_team", "owner_team_abbr", "owner_display"],
                    )

                for obj in policy_results.objects:
                    owner = obj.properties.get("owner_team", "") or obj.properties.get("owner_team_abbr", "")
                    owner_display = obj.properties.get("owner_display", "")
                    if team_name.lower() in owner.lower() or team_name.lower() in owner_display.lower():
                        results.append({
                            "type": "Policy",
                            "title": obj.properties.get("title", ""),
                            "file_type": obj.properties.get("file_type", ""),
                            "owner": owner_display or owner,
                        })
            except Exception as e:
                logger.warning(f"Error searching Policies by team: {e}")

            return results

        registry["search_by_team"] = search_by_team

        # Collection statistics tool
        async def get_collection_stats() -> dict:
            """Get statistics about all collections in the knowledge base.

            Use this tool when the user asks:
            - How many documents are there?
            - What's in the knowledge base?
            - Show me the system status
            - Collection statistics

            Returns:
                Dictionary with collection names and document counts
            """
            collections = get_all_collection_names()
            stats = {}
            for name in collections:
                if client.collections.exists(name):
                    collection = client.collections.get(name)
                    aggregate = collection.aggregate.over_all(total_count=True)
                    stats[name] = aggregate.total_count
                else:
                    stats[name] = 0
            return stats

        registry["get_collection_stats"] = get_collection_stats

        # Dedicated counting tool for accurate UNIQUE document counts
        async def count_documents(collection_type: str = "all") -> dict:
            """Get accurate UNIQUE document counts (not chunk counts).

            Use this tool when the user asks:
            - How many ADRs are there?
            - How many principles exist?
            - Count the policies
            - Total documents in the system

            NOTE: This counts unique documents by deduping via file_path,
            NOT raw chunk counts from Weaviate aggregation.

            Args:
                collection_type: Type to count - "adr", "principle", "policy", "vocabulary", or "all"

            Returns:
                Dictionary with accurate unique document counts
            """
            counts = {}

            type_mapping = {
                "adr": get_collection_name("adr"),
                "adrs": get_collection_name("adr"),
                "principle": get_collection_name("principle"),
                "principles": get_collection_name("principle"),
                "policy": get_collection_name("policy"),
                "policies": get_collection_name("policy"),
                "vocabulary": get_collection_name("vocabulary"),
                "vocab": get_collection_name("vocabulary"),
            }

            collections_to_check = []
            if collection_type.lower() == "all":
                collections_to_check = get_all_collection_names()
            else:
                coll_name = type_mapping.get(collection_type.lower())
                if coll_name:
                    collections_to_check = [coll_name]
                else:
                    return {"error": f"Unknown collection type: {collection_type}"}

            friendly_names = {
                get_collection_name("adr"): "ADRs",
                get_collection_name("principle"): "Principles",
                get_collection_name("policy"): "Policies",
                get_collection_name("vocabulary"): "Vocabulary Terms",
            }

            for name in collections_to_check:
                try:
                    collection = client.collections.get(name)

                    # Get filter for non-vocab collections
                    content_filter = None
                    if name != get_collection_name("vocabulary"):
                        content_filter = build_document_filter(f"count {name}", _skill_registry, DEFAULT_SKILL)

                    # Fetch ALL objects with pagination to get accurate unique count
                    all_objects = fetch_all_objects(
                        collection,
                        filters=content_filter,
                        return_properties=["file_path"],
                    )

                    # Dedupe by file_path to get unique documents
                    unique_paths = set()
                    for obj in all_objects:
                        file_path = obj.properties.get("file_path", "")
                        if file_path:
                            # Apply same filtering as list functions (skip templates, index files, registry)
                            file_name = file_path.lower()
                            if "template" in file_name:
                                continue
                            # Skip index.md (directory indexes) and esa_doc_registry.md (top-level registry)
                            if file_name.endswith("index.md") or file_name.endswith("readme.md"):
                                continue
                            if file_name.endswith("esa_doc_registry.md") or file_name.endswith("esa-doc-registry.md"):
                                continue
                            # For ADRs: skip DARs
                            if name == get_collection_name("adr") and re.match(r".*\d{4}d-.*\.md$", file_name):
                                continue
                            unique_paths.add(file_path)

                    counts[friendly_names.get(name, name)] = len(unique_paths)
                    logger.debug(f"count_documents: {name} has {len(unique_paths)} unique documents (from {len(all_objects)} chunks)")

                except Exception as e:
                    logger.warning(f"Error counting {name}: {e}")
                    counts[friendly_names.get(name, name)] = 0

            return counts

        registry["count_documents"] = count_documents

        logger.info(f"Built tool registry with {len(registry)} tools: {list(registry.keys())}")
        return registry

    # =================================================================
    # INTENT SHORT-CIRCUIT HANDLERS
    # These bypass the Elysia Tree for intents with deterministic routing.
    # =================================================================

    @staticmethod
    def _normalize_doc_ref(ref: str) -> tuple[str, str]:
        """Normalize a document reference to (collection_type, canonical_id).

        Examples:
            "adr.0025" → ("adr", "ADR.0025")
            "ADR-25" → ("adr", "ADR.0025")
            "pcp.10" → ("pcp", "PCP.0010")
        """
        match = re.match(r'(adr|pcp|dar)[.\s\-]?(\d{1,4})', ref.strip(), re.IGNORECASE)
        if not match:
            return "", ""
        prefix = match.group(1).upper()
        number = match.group(2).zfill(4)
        return prefix.lower(), f"{prefix}.{number}"

    async def _handle_lookup_doc(
        self, question: str, intent_decision, structured_mode: bool
    ) -> tuple[str, list]:
        """Fetch a specific document by ID and generate an LLM answer.

        Short-circuits the Tree for queries like "Tell me about ADR.0025".
        """
        doc_refs = intent_decision.detected_entities
        if not doc_refs:
            return None, []

        coll_type, canonical_id = self._normalize_doc_ref(doc_refs[0])
        if not canonical_id:
            return None, []

        logger.info(f"Deterministic content retrieval for {canonical_id}")

        # Determine collection name and number field
        suffix = "_OpenAI" if settings.llm_provider == "openai" else ""
        if coll_type in ("adr", "dar"):
            coll_name = get_collection_name("adr")
            number_field = "adr_number"
        elif coll_type == "pcp":
            coll_name = get_collection_name("principle")
            number_field = "principle_number"
        else:
            return None, []

        # Fetch all chunks of the specific document by ID
        collection = self.client.collections.get(f"{coll_name}{suffix}")
        results = collection.query.fetch_objects(
            filters=Filter.by_property(number_field).equal(canonical_id),
            limit=20,
        )

        if not results.objects:
            # Document doesn't exist → clean abstention
            logger.info(f"Document {canonical_id} not found in collection")
            abstention = get_abstention_response(
                f"Document {canonical_id} was not found in the knowledge base."
            )
            return abstention, []

        # Compile document content from all chunks
        doc_parts = []
        objects_out = []
        for obj in results.objects:
            props = obj.properties
            if coll_type in ("adr", "dar"):
                doc_parts.append(
                    f"Title: {props.get('title', '')}\n"
                    f"ADR Number: {props.get('adr_number', '')}\n"
                    f"Status: {props.get('status', '')}\n"
                    f"Context: {props.get('context', '')}\n"
                    f"Decision: {props.get('decision', '')}\n"
                    f"Consequences: {props.get('consequences', '')}"
                )
                objects_out.append({
                    "type": "ADR",
                    "title": props.get("title", ""),
                    "adr_number": props.get("adr_number", ""),
                    "status": props.get("status", ""),
                })
            else:
                doc_parts.append(
                    f"Title: {props.get('title', '')}\n"
                    f"Principle Number: {props.get('principle_number', '')}\n"
                    f"Content: {props.get('content', '')}"
                )
                objects_out.append({
                    "type": "Principle",
                    "title": props.get("title", ""),
                    "principle_number": props.get("principle_number", ""),
                })

        # Dedupe objects
        seen_titles = set()
        unique_objects = []
        for obj in objects_out:
            key = obj.get("title", "")
            if key not in seen_titles:
                seen_titles.add(key)
                unique_objects.append(obj)

        doc_content = "\n\n---\n\n".join(doc_parts)

        # Generate answer via LLM
        system_prompt = (
            "You are AInstein, the ESA knowledge base assistant at Alliander. "
            "Answer the user's question based on the document content below. "
            "Be thorough and include relevant details from the document. "
            "If the content doesn't address the question, say so."
        )
        user_prompt = f"Question: {question}\n\nDocument content:\n{doc_content}"

        if settings.llm_provider == "ollama":
            raw_response = await self._generate_with_ollama(system_prompt, user_prompt)
        else:
            raw_response = await self._generate_with_openai(system_prompt, user_prompt)

        # Post-process for structured mode
        processed, _, _ = postprocess_llm_output(
            raw_response=raw_response,
            structured_mode=structured_mode,
            enforcement_policy=DEFAULT_ENFORCEMENT_POLICY,
        )

        return processed, unique_objects

    async def _handle_lookup_approval(
        self, question: str, intent_decision, structured_mode: bool
    ) -> tuple[str, list]:
        """Fetch approval records for a specific document.

        Short-circuits the Tree for queries like "Who approved ADR.0025?".
        """
        doc_refs = intent_decision.detected_entities
        logger.info(f"Deterministic approval extraction for {doc_refs}")

        suffix = "_OpenAI" if settings.llm_provider == "openai" else ""

        if doc_refs:
            coll_type, canonical_id = self._normalize_doc_ref(doc_refs[0])
            if not canonical_id:
                return None, []

            # Determine the approval doc_type and collection
            if coll_type in ("adr", "dar"):
                coll_name = get_collection_name("adr")
                approval_doc_type = "adr_approval"
                number_field = "adr_number"
            elif coll_type == "pcp":
                coll_name = get_collection_name("principle")
                approval_doc_type = "principle_approval"
                number_field = "principle_number"
            else:
                return None, []

            # Fetch approval records for this specific document
            collection = self.client.collections.get(f"{coll_name}{suffix}")
            results = collection.query.fetch_objects(
                filters=(
                    Filter.by_property("doc_type").equal(approval_doc_type)
                    & Filter.by_property(number_field).equal(canonical_id)
                ),
                limit=10,
            )

            if not results.objects:
                # No approval record found
                abstention = get_abstention_response(
                    f"No approval record found for {canonical_id} in the knowledge base."
                )
                return abstention, []

            # Compile approval content
            doc_parts = []
            objects_out = []
            for obj in results.objects:
                props = obj.properties
                content = props.get("content", "") or props.get("decision", "") or ""
                doc_parts.append(
                    f"Title: {props.get('title', '')}\n"
                    f"Content:\n{content}"
                )
                objects_out.append({
                    "type": "Approval Record",
                    "title": props.get("title", ""),
                    "file_path": props.get("file_path", ""),
                })

            doc_content = "\n\n---\n\n".join(doc_parts)

            # Generate answer via LLM
            system_prompt = (
                "You are AInstein, the ESA knowledge base assistant at Alliander. "
                "Answer the user's question about document approval based on the "
                "approval record content below. Include the names of approvers "
                "and their roles if available."
            )
            user_prompt = f"Question: {question}\n\nApproval record:\n{doc_content}"

            if settings.llm_provider == "ollama":
                raw_response = await self._generate_with_ollama(system_prompt, user_prompt)
            else:
                raw_response = await self._generate_with_openai(system_prompt, user_prompt)

            processed, _, _ = postprocess_llm_output(
                raw_response=raw_response,
                structured_mode=structured_mode,
                enforcement_policy=DEFAULT_ENFORCEMENT_POLICY,
            )
            return processed, objects_out

        else:
            # No specific doc ref — use the list_approval_records tool
            list_tool = self._tool_registry.get("list_approval_records")
            if list_tool:
                scope = intent_decision.entity_scope.value
                if scope in ("adr", "dar_adr"):
                    list_result = await list_tool("adr")
                elif scope in ("pcp", "dar_pcp"):
                    list_result = await list_tool("principle")
                else:
                    list_result = await list_tool("all")

                if list_result and is_list_result(list_result):
                    context = create_context_from_skills(question, _skill_registry)
                    gateway_result = handle_list_result(list_result, context)
                    if gateway_result:
                        objects = list_result.get("rows", []) if isinstance(list_result, dict) else []
                        return gateway_result.response, objects

            return None, []

    async def _handle_list(
        self, question: str, intent_decision, structured_mode: bool
    ) -> tuple[str, list]:
        """Execute deterministic list for the given entity scope.

        Short-circuits the Tree for queries like "List all ADRs".
        """
        scope = intent_decision.entity_scope.value
        logger.info(f"Deterministic list response for scope: {scope}")

        # Map scope to list tool
        scope_tool_map = {
            "adr": "list_all_adrs",
            "pcp": "list_all_principles",
            "dar_adr": "list_approval_records",
            "dar_pcp": "list_approval_records",
            "dar_all": "list_approval_records",
            "policy": "list_all_policies",
        }

        tool_name = scope_tool_map.get(scope)
        if not tool_name:
            # Unknown scope — try to infer from question text
            q = question.lower()
            if "adr" in q or "decision" in q:
                tool_name = "list_all_adrs"
            elif "principle" in q or "pcp" in q:
                tool_name = "list_all_principles"
            elif "polic" in q:
                tool_name = "list_all_policies"
            elif "approval" in q or "dar" in q:
                tool_name = "list_approval_records"
            else:
                return None, []

        list_tool = self._tool_registry.get(tool_name)
        if not list_tool:
            return None, []

        # Call the list tool
        if tool_name == "list_approval_records":
            if scope == "dar_adr":
                list_result = await list_tool("adr")
            elif scope == "dar_pcp":
                list_result = await list_tool("principle")
            else:
                list_result = await list_tool("all")
        else:
            list_result = await list_tool()

        if list_result and is_list_result(list_result):
            context = create_context_from_skills(question, _skill_registry)
            gateway_result = handle_list_result(list_result, context)
            if gateway_result:
                objects = list_result.get("rows", []) if isinstance(list_result, dict) else []
                return gateway_result.response, objects

        return None, []

    async def query(self, question: str, collection_names: Optional[list[str]] = None) -> tuple[str, list[dict]]:
        """Process a query using Elysia's decision tree.

        Creates a fresh Tree instance per request to ensure thread safety
        when processing concurrent requests.

        For list queries (e.g., "What ADRs exist?"), this method bypasses
        LLM-based response generation and uses deterministic serialization
        for contract compliance.

        Args:
            question: The user's question
            collection_names: Optional list of collection names to focus on

        Returns:
            Tuple of (response text, retrieved objects)
        """
        logger.info(f"Elysia processing: {question}")

        # Check semantic response cache (avoids re-running Tree for identical queries)
        cached = _cache_get(question)
        if cached is not None:
            logger.info("Cache hit — returning cached semantic response")
            obs_metrics.increment("semantic_cache_hit_total")
            return cached

        # Determine structured mode FIRST - this affects both prompt injection and post-processing
        # response-contract skill enforces JSON output format
        structured_mode = _skill_registry.is_skill_active("response-contract", question)
        if structured_mode:
            logger.info(f"Structured mode ACTIVE for query: {question[:50]}...")

        # Create structured mode context for gateway integration
        context = create_context_from_skills(question, _skill_registry)

        # =============================================================================
        # ROUTING POLICY — load feature flags
        # =============================================================================
        routing_policy = settings.get_routing_policy()
        intent_router_enabled = routing_policy.get("intent_router_enabled", False)
        abstain_gate_enabled = routing_policy.get("abstain_gate_enabled", True)
        tree_enabled = routing_policy.get("tree_enabled", True)
        debug_headers = routing_policy.get("debug_headers_enabled", False)
        intent_router_mode = routing_policy.get("intent_router_mode", "heuristic")
        confidence_threshold = routing_policy.get("intent_confidence_threshold", 0.55)
        max_tree_seconds = routing_policy.get("max_tree_seconds", settings.elysia_query_timeout_seconds)
        followup_binding_enabled = routing_policy.get("followup_binding_enabled", True)

        # Routing transparency log (internal only, never exposed in responses)
        route_log = {
            "request_id": generate_request_id(),
            "route_selected": None,
            "intent": None,
            "confidence": None,
            "collections_queried": [],
            "doc_types_allowed": [],
            "abstain_gate_triggered": False,
            "tree_timeout": False,
            "tree_enabled": tree_enabled,
            "abstain_gate_enabled": abstain_gate_enabled,
        }

        # =============================================================================
        # INTENT ROUTER (when enabled, runs BEFORE legacy keyword routing)
        # Returns a stable IntentDecision schema that determines the route.
        # =============================================================================
        intent_decision = None
        if intent_router_enabled:
            from .intent_router import (
                classify_intent, needs_clarification, build_clarification_response,
                handle_compare_concepts, handle_compare_counts,
                Intent, EntityScope, OutputShape,
            )
            intent_decision = await classify_intent(question, mode=intent_router_mode)
            route_log["intent"] = intent_decision.intent.value
            route_log["confidence"] = intent_decision.confidence

            # If confidence is too low, ask clarifying question
            if needs_clarification(intent_decision, threshold=confidence_threshold):
                route_log["route_selected"] = "clarification"
                logger.info(f"Intent confidence too low ({intent_decision.confidence:.2f}), asking clarification")
                clarification = await build_clarification_response(intent_decision, question)
                response = _maybe_add_debug_footer(clarification, route_log, debug_headers)
                return response, []

            # Route based on intent decision
            if intent_decision.intent == Intent.META:
                route_log["route_selected"] = "meta"
                obs_metrics.increment("meta_route_total")
                response = build_meta_response(question, structured_mode=structured_mode)
                response = _maybe_add_debug_footer(response, route_log, debug_headers)
                return response, []

            if intent_decision.intent == Intent.COMPARE_CONCEPTS:
                route_log["route_selected"] = "compare_concepts"
                compare_response = handle_compare_concepts(question)
                if structured_mode:
                    import json as _json
                    compare_response = _json.dumps({
                        "schema_version": "1.0",
                        "answer": compare_response,
                        "sources": [],
                        "transparency_statement": "Deterministic concept comparison.",
                    }, indent=2)
                response = _maybe_add_debug_footer(compare_response, route_log, debug_headers)
                return response, []

            if intent_decision.intent == Intent.COMPARE_COUNTS:
                route_log["route_selected"] = "compare_counts"
                counts_response = await handle_compare_counts(question, self._tool_registry)
                if structured_mode:
                    import json as _json
                    counts_response = _json.dumps({
                        "schema_version": "1.0",
                        "answer": counts_response,
                        "sources": [],
                        "transparency_statement": "Numeric count comparison.",
                    }, indent=2)
                response = _maybe_add_debug_footer(counts_response, route_log, debug_headers)
                return response, []

            # ---- LOOKUP_DOC: fetch specific document by ID ----
            if intent_decision.intent == Intent.LOOKUP_DOC and intent_decision.detected_entities:
                route_log["route_selected"] = "lookup_doc"
                response, objects = await self._handle_lookup_doc(
                    question, intent_decision, structured_mode
                )
                if response:
                    response = _maybe_add_debug_footer(response, route_log, debug_headers)
                    return response, objects

            # ---- LOOKUP_APPROVAL: fetch approval info ----
            if intent_decision.intent == Intent.LOOKUP_APPROVAL:
                route_log["route_selected"] = "lookup_approval"
                response, objects = await self._handle_lookup_approval(
                    question, intent_decision, structured_mode
                )
                if response:
                    response = _maybe_add_debug_footer(response, route_log, debug_headers)
                    return response, objects

            # ---- LIST: deterministic document listing ----
            if intent_decision.intent == Intent.LIST:
                route_log["route_selected"] = "list"
                response, objects = await self._handle_list(
                    question, intent_decision, structured_mode
                )
                if response:
                    response = _maybe_add_debug_footer(response, route_log, debug_headers)
                    return response, objects

            # For remaining intents (SEMANTIC_ANSWER, COUNT, UNKNOWN),
            # fall through to Tree/direct routing.
            logger.info(
                f"Intent router decision: {intent_decision.intent.value} "
                f"(confidence={intent_decision.confidence:.2f}), proceeding to Tree routing"
            )

        # Always specify our collection names to bypass Elysia's metadata collection discovery
        # This avoids gRPC errors from Elysia's internal collections
        our_collections = collection_names or get_all_collection_names()

        # Build agent description with injected skills
        skill_content = _skill_registry.get_all_skill_content(question)
        if skill_content:
            agent_description = f"{self._base_agent_description}\n\n{skill_content}"
            logger.debug("Injected skills into agent description")
        else:
            agent_description = self._base_agent_description

        # Inject entity scope hint from intent router to guide Tree tool selection
        if intent_router_enabled and intent_decision:
            scope = intent_decision.entity_scope
            scope_hints = {
                EntityScope.ADR: (
                    "\n\nIMPORTANT: This query is about Architecture Decision Records (ADRs). "
                    "Use search_architecture_decisions() to find relevant ADRs. "
                    "Do NOT use list_all_adrs() unless the user explicitly asks for a list."
                ),
                EntityScope.PCP: (
                    "\n\nIMPORTANT: This query is about Principles (PCPs). "
                    "Use search_principles() to find relevant principles. "
                    "Do NOT use list_all_principles() unless the user explicitly asks for a list."
                ),
                EntityScope.POLICY: (
                    "\n\nIMPORTANT: This query is about Policy documents. "
                    "Use search_policies() to find relevant policies."
                ),
                EntityScope.VOCAB: (
                    "\n\nIMPORTANT: This query is about vocabulary/terminology. "
                    "Use search_vocabulary() to find relevant terms and definitions."
                ),
                EntityScope.MULTI: (
                    "\n\nIMPORTANT: This is a cross-domain query. "
                    "Search multiple collections (ADRs, principles, policies) to provide a comprehensive answer."
                ),
            }
            hint = scope_hints.get(scope, "")
            if hint:
                agent_description += hint

        # =============================================================================
        # TREE / LLM PATH
        # When tree_enabled=true, use Elysia Tree for multi-step reasoning.
        # When tree_enabled=false, use direct retrieval + LLM generation.
        # =============================================================================
        if tree_enabled:
            # Create per-request tree instance (thread-safe: no shared mutable state)
            request_tree = self._create_tree(agent_description)

            try:
                # Use semaphore to limit concurrent Elysia calls (prevents thread explosion)
                # Use asyncio.to_thread to offload blocking Tree call (prevents event loop blocking)
                # Use wait_for to add timeout and enable cancellation
                semaphore = _get_elysia_semaphore()
                async with semaphore:
                    response, objects = await asyncio.wait_for(
                        asyncio.to_thread(
                            request_tree, question, collection_names=our_collections
                        ),
                        timeout=max_tree_seconds
                    )

                    # Log tree completion stats for debugging (must be done after call completes)
                    iterations = request_tree.tree_data.num_trees_completed
                    limit = request_tree.tree_data.recursion_limit

                if iterations >= limit:
                    logger.warning(f"Elysia tree hit recursion limit ({iterations}/{limit})")
                else:
                    logger.debug(f"Elysia tree completed in {iterations} iteration(s)")

            except asyncio.TimeoutError:
                # Query exceeded timeout - log and fallback
                logger.warning(
                    f"Elysia tree timed out after {max_tree_seconds}s, "
                    "using direct tool execution"
                )
                response, objects = await self._direct_query(question, structured_mode=structured_mode)
                return response, objects

            except Exception as e:
                # If Elysia's tree fails, fall back to direct tool execution
                logger.warning(f"Elysia tree failed: {e}, using direct tool execution")
                # _direct_query handles its own post-processing, pass structured_mode
                response, objects = await self._direct_query(question, structured_mode=structured_mode)
                # Return directly since _direct_query already post-processed
                return response, objects
        else:
            # Tree disabled — use direct retrieval + LLM generation
            logger.info("Tree disabled — using direct retrieval + LLM generation")
            response, objects = await self._direct_query(question, structured_mode=structured_mode)
            return response, objects

        # =================================================================
        # GROUNDING GATE: reject LLM answers when retrieval is empty
        # If the Tree generated a substantive response but retrieved zero
        # documents, the answer is almost certainly hallucinated.
        # Gated by abstain_gate_enabled flag.
        # =================================================================
        if abstain_gate_enabled:
            _response_text = response if isinstance(response, str) else str(response)
            _is_substantive = len(_response_text.strip()) > 100
            _is_abstention = any(
                phrase in _response_text.lower()
                for phrase in (
                    "not found in the knowledge base",
                    "don't have sufficient information",
                    "no relevant documents",
                    "i couldn't find",
                )
            )
            if not objects and _is_substantive and not _is_abstention:
                logger.warning(
                    "Grounding gate: Tree returned substantive response with zero "
                    "retrieved objects — replacing with abstention"
                )
                obs_metrics.increment("grounding_gate_abstention_total")
                grounded = get_abstention_response(
                    "No relevant documents were retrieved from the knowledge base for this query."
                )
                return grounded, objects

        # POST-PROCESS the Elysia tree response through unified contract enforcement
        # This is the critical fix: main path must also enforce structured response contract
        processed_response, was_structured, reason = postprocess_llm_output(
            raw_response=response,
            structured_mode=structured_mode,
            enforcement_policy=DEFAULT_ENFORCEMENT_POLICY,
        )

        if structured_mode:
            logger.info(f"Main path post-processing: was_structured={was_structured}, reason={reason}")

        # Guard: if post-processing produced an empty response despite retrieved
        # objects, fall back to direct query rather than returning nothing.
        if not processed_response or not processed_response.strip():
            logger.warning(
                "Tree returned empty response after post-processing "
                f"(objects={len(objects)}), falling back to _direct_query"
            )
            obs_metrics.increment("tree_empty_response_total")
            return await self._direct_query(question, structured_mode=structured_mode)

        # Cache the successful semantic response
        _cache_put(question, processed_response, objects)

        return processed_response, objects

    async def _direct_query(self, question: str, structured_mode: bool = None) -> tuple[str, list[dict]]:
        """Direct query execution bypassing Elysia tree when it fails.

        Supports both OpenAI and Ollama as LLM backends.
        Uses client-side embeddings for local collections (Ollama provider).
        Implements confidence-based abstention to prevent hallucination.

        Args:
            question: The user's question
            structured_mode: Whether response-contract is active (auto-detected if None)

        Returns:
            Tuple of (response text, retrieved objects)
        """
        # Auto-detect structured mode if not provided
        if structured_mode is None:
            structured_mode = _skill_registry.is_skill_active("response-contract", question)
        question_lower = question.lower()
        all_results = []
        collection_counts = {}  # Track total counts for transparency

        # Detect query type: list/catalog vs semantic/specific
        is_catalog_query = is_list_query(question)
        if is_catalog_query:
            logger.info(f"Catalog query detected in _direct_query: {question}")

        # ── Deterministic list shortcut (safety net) ──────────────────────
        # When the Tree times out and falls back here, re-try the same
        # deterministic list tools that the main query() method uses.
        # This avoids the expensive generic search + LLM path for catalog
        # queries that should have been handled deterministically.
        _DAR_RE_FALLBACK = re.compile(r"\bdars?\b|decision approval record", re.IGNORECASE)
        if _DAR_RE_FALLBACK.search(question_lower):
            list_tool = self._tool_registry.get("list_approval_records")
            if list_tool:
                logger.info("_direct_query: re-routing DAR query to deterministic list tool")
                if "principle" in question_lower:
                    list_result = await list_tool("principle")
                elif "adr" in question_lower:
                    list_result = await list_tool("adr")
                else:
                    list_result = await list_tool("all")
                if list_result and is_list_result(list_result):
                    context = create_context_from_skills(question, _skill_registry)
                    gateway_result = handle_list_result(list_result, context)
                    if gateway_result:
                        objects = list_result.get("rows", []) if isinstance(list_result, dict) else []
                        return gateway_result.response, objects
        elif re.search(r"\badrs?\b", question_lower):
            list_tool = self._tool_registry.get("list_all_adrs")
            if list_tool:
                logger.info("_direct_query: re-routing ADR query to deterministic list tool")
                list_result = await list_tool()
                if list_result and is_list_result(list_result):
                    context = create_context_from_skills(question, _skill_registry)
                    gateway_result = handle_list_result(list_result, context)
                    if gateway_result:
                        objects = list_result.get("rows", []) if isinstance(list_result, dict) else []
                        return gateway_result.response, objects
        elif re.search(r"\bprinciples?\b", question_lower):
            list_tool = self._tool_registry.get("list_all_principles")
            if list_tool:
                logger.info("_direct_query: re-routing Principle query to deterministic list tool")
                list_result = await list_tool()
                if list_result and is_list_result(list_result):
                    context = create_context_from_skills(question, _skill_registry)
                    gateway_result = handle_list_result(list_result, context)
                    if gateway_result:
                        objects = list_result.get("rows", []) if isinstance(list_result, dict) else []
                        return gateway_result.response, objects
        elif re.search(r"\bpolic(?:y|ies)\b", question_lower):
            list_tool = self._tool_registry.get("list_all_policies")
            if list_tool:
                logger.info("_direct_query: re-routing Policy query to deterministic list tool")
                list_result = await list_tool()
                if list_result and is_list_result(list_result):
                    context = create_context_from_skills(question, _skill_registry)
                    gateway_result = handle_list_result(list_result, context)
                    if gateway_result:
                        objects = list_result.get("rows", []) if isinstance(list_result, dict) else []
                        return gateway_result.response, objects

        # Load retrieval limits from skill configuration
        retrieval_limits = _skill_registry.loader.get_retrieval_limits(DEFAULT_SKILL)
        adr_limit = retrieval_limits.get("adr", 20)
        principle_limit = retrieval_limits.get("principle", 12)
        policy_limit = retrieval_limits.get("policy", 8)
        vocab_limit = retrieval_limits.get("vocabulary", 8)
        catalog_fetch_limit = retrieval_limits.get("catalog_fetch_limit", 100)

        # Load truncation limits from skill configuration
        truncation = _skill_registry.loader.get_truncation(DEFAULT_SKILL)
        content_max_chars = truncation.get("content_max_chars", 800)
        content_chars = truncation.get("elysia_content_chars", 500)
        summary_chars = truncation.get("elysia_summary_chars", 300)

        # Determine collection suffix based on provider
        # Local collections use client-side embeddings (Nomic via Ollama)
        # OpenAI collections use Weaviate's text2vec-openai vectorizer
        use_openai_collections = settings.llm_provider == "openai"
        suffix = "_OpenAI" if use_openai_collections else ""

        # For local collections, compute query embedding client-side
        # This is a workaround for Weaviate text2vec-ollama bug (#8406)
        query_vector = None
        if not use_openai_collections:
            try:
                query_vector = embed_text(question)
            except Exception as e:
                logger.error(f"Failed to compute query embedding: {e}")

        # Build document filter based on skill configuration and query intent
        content_filter = build_document_filter(question, _skill_registry, DEFAULT_SKILL)

        # Request metadata for abstention decisions
        metadata_request = MetadataQuery(score=True, distance=True)

        # Search relevant collections
        if any(term in question_lower for term in ["adr", "decision", "architecture"]):
            try:
                collection = self.client.collections.get(f"{get_collection_name('adr')}{suffix}")

                # Always get total count first for transparency
                total_count = get_collection_count(collection, content_filter)
                collection_counts["ADR"] = total_count

                if is_catalog_query:
                    # Catalog query: fetch all matching documents
                    results = collection.query.fetch_objects(
                        filters=content_filter,
                        limit=catalog_fetch_limit,
                        return_metadata=metadata_request
                    )
                    logger.info(f"Fetched {len(results.objects)} of {total_count} total ADRs")
                else:
                    # Semantic query: use hybrid search for relevance
                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=adr_limit, alpha=settings.alpha_vocabulary,
                        filters=content_filter, return_metadata=metadata_request
                    )

                for obj in results.objects:
                    all_results.append({
                        "type": "ADR",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("decision", "")[:content_chars],
                        "distance": getattr(obj.metadata, 'distance', None),
                        "score": getattr(obj.metadata, 'score', None),
                    })
            except Exception as e:
                logger.warning(f"Error searching {get_collection_name('adr')}{suffix}: {e}")

        if any(term in question_lower for term in ["principle", "governance", "esa"]):
            try:
                collection = self.client.collections.get(f"{get_collection_name('principle')}{suffix}")

                # Always get total count first for transparency
                total_count = get_collection_count(collection, content_filter)
                collection_counts["Principle"] = total_count

                if is_catalog_query:
                    results = collection.query.fetch_objects(
                        filters=content_filter,
                        limit=catalog_fetch_limit,
                        return_metadata=metadata_request
                    )
                    logger.info(f"Fetched {len(results.objects)} of {total_count} total Principles")
                else:
                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=principle_limit, alpha=settings.alpha_vocabulary,
                        filters=content_filter, return_metadata=metadata_request
                    )

                for obj in results.objects:
                    all_results.append({
                        "type": "Principle",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", "")[:content_chars],
                        "distance": getattr(obj.metadata, 'distance', None),
                        "score": getattr(obj.metadata, 'score', None),
                    })
            except Exception as e:
                logger.warning(f"Error searching {get_collection_name('principle')}{suffix}: {e}")

        if any(term in question_lower for term in ["policy", "data governance", "compliance"]):
            try:
                collection = self.client.collections.get(f"{get_collection_name('policy')}{suffix}")

                # PolicyDocument does not have a doc_type property — never apply
                # doc_type filters.  The old try/except around get_collection_count
                # was dead code because that function swallows exceptions internally.
                policy_filter = None
                total_count = get_collection_count(collection)
                collection_counts["Policy"] = total_count

                if is_catalog_query:
                    results = collection.query.fetch_objects(
                        filters=policy_filter,
                        limit=catalog_fetch_limit,
                        return_metadata=metadata_request
                    )
                    logger.info(f"Fetched {len(results.objects)} of {total_count} total Policies")
                else:
                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=policy_limit, alpha=settings.alpha_vocabulary,
                        filters=policy_filter, return_metadata=metadata_request
                    )

                for obj in results.objects:
                    all_results.append({
                        "type": "Policy",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", "")[:content_chars],
                        "distance": getattr(obj.metadata, 'distance', None),
                        "score": getattr(obj.metadata, 'score', None),
                    })
            except Exception as e:
                logger.warning(f"Error searching {get_collection_name('policy')}{suffix}: {e}")

        # Expanded keyword matching for vocabulary - catch "what is X" type questions
        vocab_keywords = ["vocab", "concept", "definition", "cim", "iec", "what is", "what does", "define", "meaning", "term", "standard", "archimate"]
        if any(term in question_lower for term in vocab_keywords):
            try:
                collection = self.client.collections.get(f"{get_collection_name('vocabulary')}{suffix}")

                # Always get total count first for transparency
                # Note: Vocabulary doesn't use content_filter (no doc_type field)
                total_count = get_collection_count(collection, None)
                collection_counts["Vocabulary"] = total_count

                if is_catalog_query:
                    results = collection.query.fetch_objects(
                        limit=catalog_fetch_limit,
                        return_metadata=metadata_request
                    )
                    logger.info(f"Fetched {len(results.objects)} of {total_count} total Vocabulary terms")
                else:
                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=vocab_limit, alpha=settings.alpha_vocabulary,
                        return_metadata=metadata_request
                    )

                for obj in results.objects:
                    all_results.append({
                        "type": "Vocabulary",
                        "label": obj.properties.get("pref_label", ""),
                        "definition": obj.properties.get("definition", ""),
                        "distance": getattr(obj.metadata, 'distance', None),
                        "score": getattr(obj.metadata, 'score', None),
                    })
            except Exception as e:
                logger.warning(f"Error searching {get_collection_name('vocabulary')}{suffix}: {e}")

        # If no specific collection matched, search all including Vocabulary
        if not all_results:
            # Map collection base names to display types
            type_map = {
                get_collection_name("adr"): "ADR",
                get_collection_name("principle"): "Principle",
                get_collection_name("policy"): "Policy",
                get_collection_name("vocabulary"): "Vocabulary",
            }
            for coll_base in get_all_collection_names():
                try:
                    collection = self.client.collections.get(f"{coll_base}{suffix}")

                    # Get total count for transparency (even in fallback).
                    # Skip doc_type filter for collections that lack the property
                    # (Vocabulary has no doc_type, PolicyDocument has no doc_type).
                    _skip_filter = coll_base in (
                        get_collection_name("vocabulary"),
                        get_collection_name("policy"),
                    )
                    total_count = get_collection_count(
                        collection, None if _skip_filter else content_filter
                    )
                    display_type = type_map.get(coll_base, coll_base)
                    if total_count > 0 and display_type not in collection_counts:
                        collection_counts[display_type] = total_count

                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=3, alpha=settings.alpha_vocabulary,
                        return_metadata=metadata_request
                    )
                    for obj in results.objects:
                        if coll_base == get_collection_name("vocabulary"):
                            all_results.append({
                                "type": "Vocabulary",
                                "label": obj.properties.get("pref_label", ""),
                                "definition": obj.properties.get("definition", ""),
                                "distance": getattr(obj.metadata, 'distance', None),
                                "score": getattr(obj.metadata, 'score', None),
                            })
                        else:
                            all_results.append({
                                "type": display_type,
                                "title": obj.properties.get("title", ""),
                                "content": obj.properties.get("content", obj.properties.get("decision", ""))[:summary_chars],
                                "distance": getattr(obj.metadata, 'distance', None),
                                "score": getattr(obj.metadata, 'score', None),
                            })
                except Exception as e:
                    logger.warning(f"Error searching {coll_base}{suffix}: {e}")

        # Check if we should abstain from answering
        # Rule: Abstention applies only to semantic routes. Catalog/list queries
        # that retrieved results should never be overridden by abstention.
        if is_catalog_query and all_results:
            logger.info(
                f"Catalog query with {len(all_results)} results — skipping abstention check"
            )
        else:
            abstain, reason = should_abstain(question, all_results)
            if abstain:
                logger.info(f"Abstaining from query: {reason}")
                return get_abstention_response(reason), all_results

        # Build context from retrieved results with transparency about totals
        max_context_results = truncation.get("max_context_results", 10)

        # Add transparency header with collection counts
        context_parts = []
        if collection_counts:
            count_info = []
            # Count how many of each type are in the truncated results (what LLM actually sees)
            truncated_results = all_results[:max_context_results]
            for doc_type, total in collection_counts.items():
                # Count shown items in the TRUNCATED results, not all_results
                shown = sum(1 for r in truncated_results if r.get("type") == doc_type)
                if shown < total:
                    count_info.append(f"{doc_type}: showing {shown} of {total} total")
                else:
                    count_info.append(f"{doc_type}: {total} total (all shown)")
            context_parts.append("--- COLLECTION COUNTS (be transparent about these!) ---")
            context_parts.append("\n".join(count_info))
            context_parts.append("--- END COUNTS ---\n")

        # Add document contents
        context_parts.append("\n\n".join([
            f"[{r.get('type', 'Document')}] {r.get('title', r.get('label', 'Untitled'))}: {r.get('content', r.get('definition', ''))}"
            for r in all_results[:max_context_results]
        ]))

        context = "\n".join(context_parts)

        # Get skill content for prompt injection
        skill_content = _skill_registry.get_all_skill_content(question)

        system_prompt = """You are AInstein, the Energy System Architecture AI Assistant at Alliander.

Your role is to help architects, engineers, and stakeholders navigate Alliander's energy system architecture knowledge base, including:
- Architectural Decision Records (ADRs)
- Data governance principles and policies
- IEC/CIM vocabulary and standards
- Energy domain concepts and terminology

Guidelines:
- Base your answers strictly on the provided context
- If the information is not in the context, clearly state that you don't have that information
- Be concise but thorough
- When referencing ADRs, use the format ADR.XX (e.g., ADR.21)
- When referencing Principles, use the format PCP.XX (e.g., PCP.10)
- For technical terms, provide clear explanations

""" + RESPONSE_SCHEMA_INSTRUCTIONS

        # Inject skill rules if available
        if skill_content:
            system_prompt = f"{system_prompt}\n\n{skill_content}"
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

        # Generate response based on LLM provider
        if settings.llm_provider == "ollama":
            raw_response = await self._generate_with_ollama(system_prompt, user_prompt)
        else:
            raw_response = await self._generate_with_openai(system_prompt, user_prompt)

        # POST-PROCESS through unified contract enforcement
        # This ensures consistent behavior between main path and fallback path
        response_text, was_structured, reason = postprocess_llm_output(
            raw_response=raw_response,
            structured_mode=structured_mode,
            enforcement_policy=DEFAULT_ENFORCEMENT_POLICY,
        )

        if structured_mode:
            logger.info(f"Fallback path post-processing: was_structured={was_structured}, reason={reason}")

        return response_text, all_results

    async def _generate_with_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using Ollama API.

        Args:
            system_prompt: System instruction
            user_prompt: User's message with context

        Returns:
            Generated response text
        """
        import httpx
        import re
        import time

        start_time = time.time()
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min for slow local models
                response = await client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model": settings.ollama_model,
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {"num_predict": 1000},
                    },
                )
                response.raise_for_status()
                result = response.json()
                response_text = result.get("response", "")

                # Strip <think>...</think> tags from responses
                response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
                response_text = re.sub(r'</?think>', '', response_text)
                response_text = re.sub(r'\n{3,}', '\n\n', response_text)

                return response_text.strip()

        except httpx.TimeoutException:
            latency_ms = int((time.time() - start_time) * 1000)
            raise Exception(f"Ollama generation timed out after {latency_ms}ms.")

        except httpx.HTTPStatusError as e:
            latency_ms = int((time.time() - start_time) * 1000)
            raise Exception(f"Ollama HTTP error after {latency_ms}ms: {str(e)}")

    async def _generate_with_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using OpenAI API.

        Args:
            system_prompt: System instruction
            user_prompt: User's message with context

        Returns:
            Generated response text
        """
        from openai import OpenAI

        openai_client = OpenAI(api_key=settings.openai_api_key)

        # GPT-5.x models use max_completion_tokens instead of max_tokens
        model = settings.openai_chat_model
        completion_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if model.startswith("gpt-5"):
            completion_kwargs["max_completion_tokens"] = 1000
        else:
            completion_kwargs["max_tokens"] = 1000

        response = openai_client.chat.completions.create(**completion_kwargs)

        return response.choices[0].message.content

    def query_sync(self, question: str) -> str:
        """Synchronous query wrapper.

        Args:
            question: The user's question

        Returns:
            Response text from Elysia
        """
        import asyncio
        response, _ = asyncio.run(self.query(question))
        return response


def create_elysia_system(client: WeaviateClient) -> ElysiaRAGSystem:
    """Factory function to create an Elysia RAG system.

    Args:
        client: Connected Weaviate client

    Returns:
        Configured ElysiaRAGSystem instance
    """
    return ElysiaRAGSystem(client)
