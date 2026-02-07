"""Structured response schema for enterprise-grade LLM output validation.

This module defines the JSON contract for LLM responses, enabling:
- Deterministic validation (not regex-based)
- Stable CI tests
- Observability (parse success rate, field distributions)
- Controlled fallback chain
- Metrics tracking (P3)
- Response caching (P3)
- Schema versioning (P4)
"""

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Literal

logger = logging.getLogger(__name__)

# =============================================================================
# P4: Schema Versioning
# =============================================================================

CURRENT_SCHEMA_VERSION = "1.0"

# Supported schema versions for backward compatibility
SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


# =============================================================================
# P3: Metrics Tracking
# =============================================================================

class ReasonCode(str, Enum):
    """Reason codes for parse failures."""
    SUCCESS = "success"
    INVALID_JSON = "invalid_json"
    SCHEMA_MISSING_FIELD = "schema_missing_field"
    SCHEMA_TYPE_ERROR = "schema_type_error"
    INVARIANT_VIOLATION = "invariant_violation"
    EXTRACTION_FAILED = "extraction_failed"
    REPAIR_FAILED = "repair_failed"


@dataclass
class StageLatency:
    """Latency tracking for a single stage."""
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float('inf')
    max_ms: float = 0.0

    def record(self, latency_ms: float) -> None:
        """Record a latency measurement."""
        self.count += 1
        self.total_ms += latency_ms
        self.min_ms = min(self.min_ms, latency_ms)
        self.max_ms = max(self.max_ms, latency_ms)

    @property
    def avg_ms(self) -> float:
        """Average latency in milliseconds."""
        return self.total_ms / self.count if self.count > 0 else 0.0

    def to_dict(self) -> dict:
        """Export as dictionary."""
        return {
            "count": self.count,
            "total_ms": round(self.total_ms, 2),
            "avg_ms": round(self.avg_ms, 2),
            "min_ms": round(self.min_ms, 2) if self.min_ms != float('inf') else 0,
            "max_ms": round(self.max_ms, 2),
        }


class ResponseMetrics:
    """Metrics tracking for response parsing stages.

    Tracks counters, latency, and reason codes for observability.
    Thread-safe for concurrent access.

    Usage:
        metrics = ResponseMetrics.get_instance()
        metrics.increment("direct_parse_ok")
        metrics.record_latency("parse", 15.3)
        metrics.record_failure(ReasonCode.INVALID_JSON)
    """

    _instance: Optional["ResponseMetrics"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._counters: dict[str, int] = {
            "direct_parse_ok": 0,
            "repair_ok": 0,
            "extract_ok": 0,
            "final_failed": 0,
        }
        self._latencies: dict[str, StageLatency] = {
            "parse": StageLatency(),
            "extract": StageLatency(),
            "repair": StageLatency(),
            "total": StageLatency(),
        }
        self._reason_codes: dict[str, int] = {code.value: 0 for code in ReasonCode}
        self._counter_lock = threading.Lock()

        # Optional: external metrics exporter (Prometheus, StatsD, OpenTelemetry)
        self._exporter: Optional[Callable[[str, int], None]] = None

    @classmethod
    def get_instance(cls) -> "ResponseMetrics":
        """Get singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        with cls._lock:
            cls._instance = None

    def set_exporter(self, exporter: Callable[[str, int], None]) -> None:
        """Set external metrics exporter.

        Args:
            exporter: Callable that takes (metric_name, value) and exports to backend
        """
        self._exporter = exporter

    def increment(self, counter: str, value: int = 1) -> None:
        """Increment a counter.

        Args:
            counter: Counter name (direct_parse_ok, repair_ok, etc.)
            value: Amount to increment
        """
        with self._counter_lock:
            if counter in self._counters:
                self._counters[counter] += value
                if self._exporter:
                    try:
                        self._exporter(f"response_parse_{counter}", self._counters[counter])
                    except Exception as e:
                        logger.debug(f"Metrics export failed: {e}")

    def record_latency(self, stage: str, latency_ms: float) -> None:
        """Record latency for a parsing stage.

        Args:
            stage: Stage name (parse, extract, repair, total)
            latency_ms: Latency in milliseconds
        """
        with self._counter_lock:
            if stage in self._latencies:
                self._latencies[stage].record(latency_ms)

    def record_failure(self, reason: ReasonCode) -> None:
        """Record a failure with reason code.

        Args:
            reason: Reason code for the failure
        """
        with self._counter_lock:
            self._reason_codes[reason.value] += 1
            if self._exporter:
                try:
                    self._exporter(f"response_parse_reason_{reason.value}", self._reason_codes[reason.value])
                except Exception as e:
                    logger.debug(f"Metrics export failed: {e}")

    def get_stats(self) -> dict:
        """Get all metrics as dictionary."""
        with self._counter_lock:
            return {
                "counters": dict(self._counters),
                "latencies": {k: v.to_dict() for k, v in self._latencies.items()},
                "reason_codes": dict(self._reason_codes),
            }

    def get_success_rate(self) -> float:
        """Calculate overall success rate (SLO metric)."""
        with self._counter_lock:
            total = sum(self._counters.values())
            if total == 0:
                return 1.0
            failed = self._counters.get("final_failed", 0)
            return (total - failed) / total


# =============================================================================
# P3: Response Caching
# =============================================================================

@dataclass
class CacheEntry:
    """Cache entry with TTL support."""
    raw_response: str
    parsed_json: Optional[dict]
    structured_response: Optional["StructuredResponse"]
    validation_result: bool
    reason_code: ReasonCode
    fallback_used: str
    created_at: float
    ttl_seconds: float

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() > (self.created_at + self.ttl_seconds)


class ResponseCache:
    """LRU cache for parsed responses with TTL.

    Reduces cost and latency during retries/fallbacks.
    Thread-safe for concurrent access.

    Usage:
        cache = ResponseCache.get_instance()
        cache_key = cache.compute_key(model_id, prompt_version, query, doc_ids, raw_text)
        cached = cache.get(cache_key)
        if not cached:
            result = parse(raw_text)
            cache.set(cache_key, result)
    """

    _instance: Optional["ResponseCache"] = None
    _lock = threading.Lock()

    DEFAULT_TTL_ONLINE = 300  # 5 minutes for online traffic
    DEFAULT_TTL_CI = 3600  # 1 hour for CI/eval runs
    MAX_CACHE_SIZE = 1000

    def __init__(self, max_size: int = MAX_CACHE_SIZE) -> None:
        self._cache: dict[str, CacheEntry] = {}
        self._access_order: list[str] = []  # For LRU eviction
        self._max_size = max_size
        self._cache_lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @classmethod
    def get_instance(cls) -> "ResponseCache":
        """Get singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        with cls._lock:
            cls._instance = None

    @staticmethod
    def compute_key(
        model_id: str,
        prompt_version: str,
        query: str,
        doc_ids: list[str],
        raw_text: str,
    ) -> str:
        """Compute deterministic cache key.

        Args:
            model_id: LLM model identifier
            prompt_version: Prompt template version
            query: User query
            doc_ids: Retrieved document IDs
            raw_text: Raw LLM response

        Returns:
            SHA256 hash as cache key
        """
        key_data = json.dumps({
            "model_id": model_id,
            "prompt_version": prompt_version,
            "query": query,
            "doc_ids": sorted(doc_ids),
            "raw_text": raw_text,
        }, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, key: str) -> Optional[CacheEntry]:
        """Get cached entry if exists and not expired.

        Args:
            key: Cache key

        Returns:
            CacheEntry or None
        """
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.is_expired():
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                self._misses += 1
                return None
            # Update LRU order
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            self._hits += 1
            return entry

    def set(
        self,
        key: str,
        raw_response: str,
        parsed_json: Optional[dict],
        structured_response: Optional["StructuredResponse"],
        validation_result: bool,
        reason_code: ReasonCode,
        fallback_used: str,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Cache a parsed response.

        Args:
            key: Cache key
            raw_response: Original LLM response
            parsed_json: Parsed JSON dict (if any)
            structured_response: Validated response (if any)
            validation_result: Whether validation passed
            reason_code: Reason code for result
            fallback_used: Which fallback was used
            ttl_seconds: Cache TTL (defaults to online TTL)
        """
        if ttl_seconds is None:
            ttl_seconds = self.DEFAULT_TTL_ONLINE

        entry = CacheEntry(
            raw_response=raw_response,
            parsed_json=parsed_json,
            structured_response=structured_response,
            validation_result=validation_result,
            reason_code=reason_code,
            fallback_used=fallback_used,
            created_at=time.time(),
            ttl_seconds=ttl_seconds,
        )

        with self._cache_lock:
            # Evict if at capacity
            while len(self._cache) >= self._max_size and self._access_order:
                oldest_key = self._access_order.pop(0)
                self._cache.pop(oldest_key, None)

            self._cache[key] = entry
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._cache_lock:
            self._cache.clear()
            self._access_order.clear()

    def get_stats(self) -> dict:
        """Get cache statistics."""
        with self._cache_lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
            }


class CountQualifier(str, Enum):
    """Qualifier for count values."""
    EXACT = "exact"
    AT_LEAST = "at_least"
    APPROX = "approx"


@dataclass
class StructuredResponse:
    """Structured response schema for LLM outputs.

    This is the contract between the LLM and the application.
    All responses should be parseable into this schema.

    Schema versioning (P4):
    - schema_version: Used for backward compatibility
    - Breaking changes bump major version (1.0 -> 2.0)
    - Additive changes keep minor version
    """
    answer: str
    items_shown: int = 0
    items_total: Optional[int] = None
    count_qualifier: Optional[Literal["exact", "at_least", "approx"]] = None
    transparency_statement: Optional[str] = None
    sources: list[dict] = field(default_factory=list)
    schema_version: str = CURRENT_SCHEMA_VERSION

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "schema_version": self.schema_version,
            "answer": self.answer,
            "items_shown": self.items_shown,
            "items_total": self.items_total,
            "count_qualifier": self.count_qualifier,
            "transparency_statement": self.transparency_statement,
            "sources": self.sources,
        }

    def generate_transparency_message(self) -> str:
        """Generate a consistent transparency message from numeric fields.

        This avoids phrasing drift by generating from structured data.
        """
        if self.items_total is None:
            return ""

        if self.count_qualifier == "at_least":
            return f"Showing {self.items_shown} of at least {self.items_total} total items"
        elif self.count_qualifier == "approx":
            return f"Showing {self.items_shown} of approximately {self.items_total} total items"
        else:
            if self.items_shown < self.items_total:
                return f"Showing {self.items_shown} of {self.items_total} total items"
            else:
                return f"Showing all {self.items_total} items"


class ValidationError(Exception):
    """Raised when response validation fails."""
    pass


class ResponseValidator:
    """Validates structured responses against schema and invariants.

    Supports version-gated validation for backward compatibility (P4).
    """

    # Required fields per schema version
    REQUIRED_FIELDS_V1 = {"answer", "items_shown"}

    @classmethod
    def get_required_fields(cls, version: str) -> set[str]:
        """Get required fields for a schema version."""
        # Currently only v1.0, add more as versions evolve
        if version.startswith("1."):
            return cls.REQUIRED_FIELDS_V1
        # Default to latest
        return cls.REQUIRED_FIELDS_V1

    @classmethod
    def validate(cls, data: dict) -> tuple[bool, list[str], ReasonCode]:
        """Validate response data against schema and invariants.

        Args:
            data: Dictionary to validate

        Returns:
            Tuple of (is_valid, list of error messages, reason_code)
        """
        errors = []
        reason_code = ReasonCode.SUCCESS

        # Get schema version (default to current if not specified)
        version = data.get("schema_version", CURRENT_SCHEMA_VERSION)

        # Warn if unsupported version (but still try to validate)
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            logger.warning(f"Unsupported schema version: {version}, using {CURRENT_SCHEMA_VERSION}")
            version = CURRENT_SCHEMA_VERSION

        # Check required fields
        required_fields = cls.get_required_fields(version)
        for field_name in required_fields:
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")
                reason_code = ReasonCode.SCHEMA_MISSING_FIELD

        if errors:
            return False, errors, reason_code

        # Type validation
        if not isinstance(data.get("answer"), str):
            errors.append("'answer' must be a string")
            reason_code = ReasonCode.SCHEMA_TYPE_ERROR

        if not isinstance(data.get("items_shown"), int):
            errors.append("'items_shown' must be an integer")
            reason_code = ReasonCode.SCHEMA_TYPE_ERROR
        elif data["items_shown"] < 0:
            errors.append("'items_shown' must be >= 0")
            reason_code = ReasonCode.INVARIANT_VIOLATION

        items_total = data.get("items_total")
        if items_total is not None:
            if not isinstance(items_total, int):
                errors.append("'items_total' must be an integer or null")
                reason_code = ReasonCode.SCHEMA_TYPE_ERROR
            elif items_total < 0:
                errors.append("'items_total' must be >= 0")
                reason_code = ReasonCode.INVARIANT_VIOLATION
            elif isinstance(data.get("items_shown"), int) and items_total < data["items_shown"]:
                errors.append("'items_total' must be >= 'items_shown'")
                reason_code = ReasonCode.INVARIANT_VIOLATION

        qualifier = data.get("count_qualifier")
        if qualifier is not None:
            valid_qualifiers = {"exact", "at_least", "approx"}
            if qualifier not in valid_qualifiers:
                errors.append(f"'count_qualifier' must be one of: {valid_qualifiers}")
                reason_code = ReasonCode.SCHEMA_TYPE_ERROR

        if errors:
            return False, errors, reason_code

        return True, [], ReasonCode.SUCCESS

    @classmethod
    def parse_and_validate(cls, json_str: str) -> tuple[Optional[StructuredResponse], list[str], ReasonCode]:
        """Parse JSON string and validate.

        Args:
            json_str: JSON string to parse

        Returns:
            Tuple of (StructuredResponse or None, list of error messages, reason_code)
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return None, [f"JSON parse error: {e}"], ReasonCode.INVALID_JSON

        is_valid, errors, reason_code = cls.validate(data)
        if not is_valid:
            return None, errors, reason_code

        return StructuredResponse(
            answer=data["answer"],
            items_shown=data["items_shown"],
            items_total=data.get("items_total"),
            count_qualifier=data.get("count_qualifier"),
            transparency_statement=data.get("transparency_statement"),
            sources=data.get("sources", []),
            schema_version=data.get("schema_version", CURRENT_SCHEMA_VERSION),
        ), [], ReasonCode.SUCCESS


class ResponseParser:
    """Parses LLM responses with fallback chain."""

    # JSON code block pattern
    JSON_BLOCK_PATTERN = re.compile(r'```(?:json)?\s*(\{.*?\})\s*```', re.DOTALL)
    # Standalone JSON object pattern
    JSON_OBJECT_PATTERN = re.compile(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', re.DOTALL)

    @classmethod
    def extract_json(cls, text: str) -> Optional[str]:
        """Extract JSON from text, handling markdown code blocks.

        Args:
            text: Raw LLM response text

        Returns:
            Extracted JSON string or None
        """
        # Try markdown code block first
        match = cls.JSON_BLOCK_PATTERN.search(text)
        if match:
            return match.group(1).strip()

        # Try to find standalone JSON object
        match = cls.JSON_OBJECT_PATTERN.search(text)
        if match:
            return match.group(0).strip()

        return None

    @classmethod
    def repair_json(cls, broken_json: str) -> Optional[str]:
        """Attempt to repair malformed JSON.

        Common repairs:
        - Add missing closing braces
        - Fix trailing commas
        - Quote unquoted keys

        Args:
            broken_json: Potentially malformed JSON string

        Returns:
            Repaired JSON string or None if unrepairable
        """
        if not broken_json:
            return None

        repaired = broken_json.strip()

        # Remove trailing commas before closing braces/brackets
        repaired = re.sub(r',\s*([}\]])', r'\1', repaired)

        # Count braces to check balance
        open_braces = repaired.count('{')
        close_braces = repaired.count('}')

        if open_braces > close_braces:
            repaired += '}' * (open_braces - close_braces)

        # Try to parse
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            return None

    @classmethod
    def parse_with_fallbacks(
        cls,
        response_text: str,
        enable_metrics: bool = True,
    ) -> tuple[Optional[StructuredResponse], str]:
        """Parse response with full fallback chain.

        Fallback order:
        1. Direct JSON parse
        2. Extract JSON from markdown/text
        3. JSON repair
        4. Return parse failure info

        Args:
            response_text: Raw LLM response
            enable_metrics: Whether to record metrics (default True)

        Returns:
            Tuple of (StructuredResponse or None, fallback_used or error message)
        """
        metrics = ResponseMetrics.get_instance() if enable_metrics else None
        total_start = time.time()

        # Fallback A: Try direct parse
        parse_start = time.time()
        response, errors, reason_code = ResponseValidator.parse_and_validate(response_text)
        if metrics:
            metrics.record_latency("parse", (time.time() - parse_start) * 1000)

        if response:
            if metrics:
                metrics.increment("direct_parse_ok")
                metrics.record_latency("total", (time.time() - total_start) * 1000)
            return response, "direct_parse"

        # Fallback B: Try extracting JSON from text
        extract_start = time.time()
        extracted = cls.extract_json(response_text)
        if metrics:
            metrics.record_latency("extract", (time.time() - extract_start) * 1000)

        if extracted:
            response, errors, reason_code = ResponseValidator.parse_and_validate(extracted)
            if response:
                if metrics:
                    metrics.increment("extract_ok")
                    metrics.record_latency("total", (time.time() - total_start) * 1000)
                return response, "extracted_json"

            # Fallback C: Try repairing extracted JSON
            repair_start = time.time()
            repaired = cls.repair_json(extracted)
            if metrics:
                metrics.record_latency("repair", (time.time() - repair_start) * 1000)

            if repaired:
                response, errors, reason_code = ResponseValidator.parse_and_validate(repaired)
                if response:
                    if metrics:
                        metrics.increment("repair_ok")
                        metrics.record_latency("total", (time.time() - total_start) * 1000)
                    return response, "repaired_json"

        # All fallbacks failed
        if metrics:
            metrics.increment("final_failed")
            metrics.record_failure(reason_code)
            metrics.record_latency("total", (time.time() - total_start) * 1000)

        # Fallback D would be a retry with stricter constraints (done at caller level)
        # Fallback E would be LLM-based extraction (done at caller level)

        return None, f"parse_failed: {'; '.join(errors)}"


# JSON schema for LLM system prompt (P4: includes schema_version)
RESPONSE_SCHEMA = """
{
    "schema_version": "1.0",
    "answer": "Your response text here",
    "items_shown": <number of items in this response>,
    "items_total": <total items in database, or null if unknown>,
    "count_qualifier": "exact" | "at_least" | "approx" | null,
    "sources": [{"title": "...", "type": "ADR|Principle|Policy|Vocabulary"}]
}
"""

RESPONSE_SCHEMA_INSTRUCTIONS = f"""
CRITICAL: You MUST respond with valid JSON matching this schema:
{{
    "schema_version": "{CURRENT_SCHEMA_VERSION}",
    "answer": "Your response text here",
    "items_shown": <integer: number of items mentioned in your answer>,
    "items_total": <integer or null: total items in database from COLLECTION COUNTS>,
    "count_qualifier": "exact" | "at_least" | "approx" | null,
    "sources": [{{"title": "source title", "type": "ADR|Principle|Policy|Vocabulary"}}]
}}

Rules:
- Response MUST be valid JSON only - no markdown, no prose outside JSON
- schema_version: always include "{CURRENT_SCHEMA_VERSION}"
- items_shown: count of items you're showing in this answer
- items_total: the total from COLLECTION COUNTS (not your guess)
- count_qualifier: use "exact" for precise counts, "at_least" for minimums, "approx" for estimates
- If COLLECTION COUNTS says "ADR: 18 total", then items_total=18 and count_qualifier="exact"
"""


# =============================================================================
# Convenience Functions for Observability
# =============================================================================

def get_parse_stats() -> dict:
    """Get combined parsing and cache statistics.

    Returns:
        Dictionary with metrics, cache stats, and SLO metrics
    """
    metrics = ResponseMetrics.get_instance()
    cache = ResponseCache.get_instance()

    return {
        "parsing": metrics.get_stats(),
        "cache": cache.get_stats(),
        "slo": {
            "success_rate": metrics.get_success_rate(),
            "schema_version": CURRENT_SCHEMA_VERSION,
        },
    }


def reset_stats() -> None:
    """Reset all metrics and cache (useful for testing)."""
    ResponseMetrics.reset()
    ResponseCache.reset()
