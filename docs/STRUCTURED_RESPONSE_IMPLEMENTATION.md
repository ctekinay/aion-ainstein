# Structured Response Implementation

## Technical Implementation Document

**Version:** 1.0
**Date:** 2026-02-07
**Status:** Production Ready
**Module:** `src/response_schema.py`

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Architecture Overview](#architecture-overview)
4. [Component Details](#component-details)
   - [Structured Response Schema](#structured-response-schema)
   - [Response Validator](#response-validator)
   - [Response Parser](#response-parser)
   - [Metrics Tracking (P3)](#metrics-tracking-p3)
   - [Response Caching (P3)](#response-caching-p3)
   - [Schema Versioning (P4)](#schema-versioning-p4)
5. [Integration Guide](#integration-guide)
6. [API Reference](#api-reference)
7. [Configuration](#configuration)
8. [Testing](#testing)
9. [Observability & SLOs](#observability--slos)
10. [Future Considerations](#future-considerations)

---

## Executive Summary

This document describes the enterprise-grade structured response system implemented for AION-AINSTEIN's LLM output validation. The system replaces regex-based response validation with deterministic JSON schema validation, providing:

- **Deterministic validation** - Schema-based invariant checking
- **Observability** - Metrics, latency tracking, and reason codes
- **Resilience** - Multi-stage fallback chain with JSON repair
- **Performance** - LRU caching with TTL support
- **Extensibility** - Schema versioning for backward compatibility

---

## Problem Statement

### Previous Approach (Rejected)
```python
# Regex-based validation - UNRELIABLE
has_counts = re.search(r'\d+\s+of\s+\d+', response)
```

**Issues:**
- Surface-form matching misses semantic intent
- Phrasing drift causes false negatives
- No structured data for downstream processing
- Impossible to set meaningful SLOs

### New Approach (Implemented)
```python
# Deterministic schema validation
structured, fallback = ResponseParser.parse_with_fallbacks(response)
if structured:
    assert structured.items_total >= structured.items_shown  # Invariant
```

**Benefits:**
- Binary pass/fail on schema compliance
- Structured data for transparency generation
- Measurable success rates for SLOs
- Controlled fallback chain

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        LLM Response                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ResponseParser                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Direct Parse │──│ Extract JSON │──│ Repair JSON  │          │
│  │   (Stage A)  │  │   (Stage B)  │  │   (Stage C)  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                 │                 │                    │
│         ▼                 ▼                 ▼                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              ResponseValidator                           │   │
│  │  • Schema validation (required fields, types)           │   │
│  │  • Invariant checks (items_total >= items_shown)        │   │
│  │  • Version-gated validation                              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
          ┌─────────────────┐     ┌─────────────────┐
          │ StructuredResponse│     │ ResponseMetrics │
          │ (Success Path)    │     │ (All Paths)     │
          └─────────────────┘     └─────────────────┘
                    │                       │
                    ▼                       ▼
          ┌─────────────────┐     ┌─────────────────┐
          │ ResponseCache   │     │ External Export │
          │ (Optional)      │     │ (Prometheus/etc)│
          └─────────────────┘     └─────────────────┘
```

---

## Component Details

### Structured Response Schema

The JSON contract between the LLM and the application:

```python
@dataclass
class StructuredResponse:
    answer: str                          # Required: The response text
    items_shown: int = 0                 # Required: Count of items in response
    items_total: Optional[int] = None    # Total items in database
    count_qualifier: Optional[str] = None  # "exact" | "at_least" | "approx"
    transparency_statement: Optional[str] = None
    sources: list[dict] = field(default_factory=list)
    schema_version: str = "1.0"          # P4: Version tracking
```

**JSON Schema (LLM Prompt):**
```json
{
    "schema_version": "1.0",
    "answer": "Your response text here",
    "items_shown": 5,
    "items_total": 18,
    "count_qualifier": "exact",
    "sources": [{"title": "ADR.21", "type": "ADR"}]
}
```

### Response Validator

Validates responses against schema and invariants:

```python
class ResponseValidator:
    REQUIRED_FIELDS_V1 = {"answer", "items_shown"}

    @classmethod
    def validate(cls, data: dict) -> tuple[bool, list[str], ReasonCode]:
        # 1. Check required fields
        # 2. Validate types
        # 3. Check invariants (items_total >= items_shown)
        # 4. Return (is_valid, errors, reason_code)
```

**Invariants Enforced:**
| Invariant | Condition |
|-----------|-----------|
| `items_shown >= 0` | Non-negative shown count |
| `items_total >= 0` | Non-negative total count |
| `items_total >= items_shown` | Total must include shown |
| `count_qualifier ∈ {"exact", "at_least", "approx", null}` | Valid qualifier |

### Response Parser

Multi-stage fallback chain for robust parsing:

```python
class ResponseParser:
    @classmethod
    def parse_with_fallbacks(cls, response_text: str) -> tuple[Optional[StructuredResponse], str]:
        # Stage A: Direct JSON parse
        # Stage B: Extract JSON from markdown/text
        # Stage C: Repair malformed JSON
        # Stage D: Return failure with reason
```

**Fallback Chain:**
```
┌────────────────────────────────────────────────────────────────┐
│ Stage A: Direct Parse                                          │
│   Input: '{"answer": "...", "items_shown": 5}'                │
│   Result: ✓ Success → return (response, "direct_parse")       │
└────────────────────────────────────────────────────────────────┘
                              │ Failure
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ Stage B: Extract JSON                                          │
│   Input: 'Here is the answer: ```json\n{...}\n```'            │
│   Extract: {...}                                               │
│   Result: ✓ Success → return (response, "extracted_json")     │
└────────────────────────────────────────────────────────────────┘
                              │ Failure
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ Stage C: Repair JSON                                           │
│   Input: '{"answer": "test", "items_shown": 5,'  (trailing ,) │
│   Repair: Remove trailing comma, balance braces               │
│   Result: ✓ Success → return (response, "repaired_json")      │
└────────────────────────────────────────────────────────────────┘
                              │ Failure
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ Stage D: Return Failure                                        │
│   Result: (None, "parse_failed: <reason>")                    │
│   Metrics: increment("final_failed"), record_failure(reason)  │
└────────────────────────────────────────────────────────────────┘
```

### Metrics Tracking (P3)

Thread-safe singleton for observability:

```python
class ResponseMetrics:
    # Counters
    _counters = {
        "direct_parse_ok": 0,
        "repair_ok": 0,
        "extract_ok": 0,
        "final_failed": 0,
    }

    # Latency tracking per stage
    _latencies = {
        "parse": StageLatency(),
        "extract": StageLatency(),
        "repair": StageLatency(),
        "total": StageLatency(),
    }

    # Reason codes for failures
    _reason_codes = {
        "success": 0,
        "invalid_json": 0,
        "schema_missing_field": 0,
        "schema_type_error": 0,
        "invariant_violation": 0,
    }
```

**Reason Codes:**
| Code | Description |
|------|-------------|
| `SUCCESS` | Parse and validation succeeded |
| `INVALID_JSON` | JSON syntax error |
| `SCHEMA_MISSING_FIELD` | Required field missing |
| `SCHEMA_TYPE_ERROR` | Field has wrong type |
| `INVARIANT_VIOLATION` | Business rule violated |
| `EXTRACTION_FAILED` | Could not extract JSON from text |
| `REPAIR_FAILED` | JSON repair unsuccessful |

### Response Caching (P3)

LRU cache with TTL for performance optimization:

```python
class ResponseCache:
    DEFAULT_TTL_ONLINE = 300   # 5 minutes
    DEFAULT_TTL_CI = 3600      # 1 hour
    MAX_CACHE_SIZE = 1000

    @staticmethod
    def compute_key(model_id, prompt_version, query, doc_ids, raw_text) -> str:
        # Deterministic SHA256 hash
```

**Cache Entry Structure:**
```python
@dataclass
class CacheEntry:
    raw_response: str
    parsed_json: Optional[dict]
    structured_response: Optional[StructuredResponse]
    validation_result: bool
    reason_code: ReasonCode
    fallback_used: str
    created_at: float
    ttl_seconds: float
```

### Schema Versioning (P4)

Backward-compatible schema evolution:

```python
CURRENT_SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_VERSIONS = {"1.0"}

# Version-gated validation
@classmethod
def get_required_fields(cls, version: str) -> set[str]:
    if version.startswith("1."):
        return cls.REQUIRED_FIELDS_V1
    # Future: add V2 fields
    return cls.REQUIRED_FIELDS_V1
```

**Versioning Rules:**
| Change Type | Version Bump | Example |
|-------------|--------------|---------|
| Additive (new optional field) | Minor (1.0 → 1.1) | Add `confidence` field |
| Breaking (remove/rename field) | Major (1.0 → 2.0) | Rename `answer` → `response` |
| Both versions supported | Transition period | Parse both 1.x and 2.x |

---

## Integration Guide

### Basic Usage

```python
from src.response_schema import ResponseParser, get_parse_stats

# Parse LLM response
response_text = '{"answer": "Here are the ADRs", "items_shown": 5, "items_total": 18}'
structured, fallback_used = ResponseParser.parse_with_fallbacks(response_text)

if structured:
    print(f"Answer: {structured.answer}")
    print(f"Showing {structured.items_shown} of {structured.items_total}")
    print(structured.generate_transparency_message())
else:
    print(f"Parse failed: {fallback_used}")

# Check metrics
stats = get_parse_stats()
print(f"Success rate: {stats['slo']['success_rate']:.2%}")
```

### Integration with Elysia Agents

```python
# In src/elysia_agents.py
from .response_schema import (
    ResponseParser,
    RESPONSE_SCHEMA_INSTRUCTIONS,
)

class ElysiaRAGSystem:
    async def _direct_query(self, question: str, ...):
        # Add schema instructions to system prompt
        system_prompt = BASE_PROMPT + RESPONSE_SCHEMA_INSTRUCTIONS

        # Get raw LLM response
        raw_response = await self._generate_with_ollama(system_prompt, user_prompt)

        # Parse with fallbacks
        structured, fallback_used = ResponseParser.parse_with_fallbacks(raw_response)

        if structured:
            transparency = structured.generate_transparency_message()
            response_text = f"{structured.answer}\n\n{transparency}"
        else:
            response_text = raw_response  # Graceful degradation

        return response_text, results
```

### Using the Cache

```python
from src.response_schema import ResponseCache, ReasonCode

cache = ResponseCache.get_instance()

# Compute cache key
cache_key = cache.compute_key(
    model_id="ollama/qwen2.5",
    prompt_version="v1.0",
    query="What ADRs exist?",
    doc_ids=["adr-21", "adr-22"],
    raw_text=raw_response
)

# Check cache first
cached = cache.get(cache_key)
if cached:
    return cached.structured_response, cached.fallback_used

# Parse and cache
structured, fallback = ResponseParser.parse_with_fallbacks(raw_response)
cache.set(
    cache_key,
    raw_response=raw_response,
    parsed_json=structured.to_dict() if structured else None,
    structured_response=structured,
    validation_result=structured is not None,
    reason_code=ReasonCode.SUCCESS if structured else ReasonCode.INVALID_JSON,
    fallback_used=fallback,
    ttl_seconds=300  # 5 minutes
)
```

### External Metrics Export

```python
from src.response_schema import ResponseMetrics

metrics = ResponseMetrics.get_instance()

# Prometheus example
def prometheus_exporter(metric_name: str, value: int):
    from prometheus_client import Gauge
    gauge = Gauge(metric_name, f"Response parsing metric: {metric_name}")
    gauge.set(value)

metrics.set_exporter(prometheus_exporter)

# StatsD example
def statsd_exporter(metric_name: str, value: int):
    import statsd
    client = statsd.StatsClient()
    client.gauge(metric_name, value)

metrics.set_exporter(statsd_exporter)
```

---

## API Reference

### ResponseParser

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `parse_with_fallbacks` | `response_text: str, enable_metrics: bool = True` | `tuple[Optional[StructuredResponse], str]` | Parse with full fallback chain |
| `extract_json` | `text: str` | `Optional[str]` | Extract JSON from markdown/text |
| `repair_json` | `broken_json: str` | `Optional[str]` | Attempt to repair malformed JSON |

### ResponseValidator

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `validate` | `data: dict` | `tuple[bool, list[str], ReasonCode]` | Validate against schema |
| `parse_and_validate` | `json_str: str` | `tuple[Optional[StructuredResponse], list[str], ReasonCode]` | Parse and validate JSON string |
| `get_required_fields` | `version: str` | `set[str]` | Get required fields for schema version |

### ResponseMetrics

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `get_instance` | - | `ResponseMetrics` | Get singleton instance |
| `reset` | - | `None` | Reset singleton (for testing) |
| `increment` | `counter: str, value: int = 1` | `None` | Increment counter |
| `record_latency` | `stage: str, latency_ms: float` | `None` | Record stage latency |
| `record_failure` | `reason: ReasonCode` | `None` | Record failure reason |
| `get_stats` | - | `dict` | Get all metrics |
| `get_success_rate` | - | `float` | Calculate SLO metric |
| `set_exporter` | `exporter: Callable[[str, int], None]` | `None` | Set external exporter |

### ResponseCache

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `get_instance` | - | `ResponseCache` | Get singleton instance |
| `reset` | - | `None` | Reset singleton (for testing) |
| `compute_key` | `model_id, prompt_version, query, doc_ids, raw_text` | `str` | Compute deterministic cache key |
| `get` | `key: str` | `Optional[CacheEntry]` | Get cached entry |
| `set` | `key, raw_response, parsed_json, structured_response, validation_result, reason_code, fallback_used, ttl_seconds` | `None` | Cache parsed response |
| `clear` | - | `None` | Clear all entries |
| `get_stats` | - | `dict` | Get cache statistics |

### Convenience Functions

| Function | Returns | Description |
|----------|---------|-------------|
| `get_parse_stats()` | `dict` | Combined metrics, cache, and SLO stats |
| `reset_stats()` | `None` | Reset all metrics and cache |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| N/A | - | Currently no environment-based configuration |

### Constants (in `response_schema.py`)

| Constant | Value | Description |
|----------|-------|-------------|
| `CURRENT_SCHEMA_VERSION` | `"1.0"` | Current schema version |
| `ResponseCache.DEFAULT_TTL_ONLINE` | `300` | Cache TTL for online traffic (5 min) |
| `ResponseCache.DEFAULT_TTL_CI` | `3600` | Cache TTL for CI runs (1 hour) |
| `ResponseCache.MAX_CACHE_SIZE` | `1000` | Maximum cache entries |

---

## Testing

### Unit Test Example

```python
import pytest
from src.response_schema import (
    ResponseParser, ResponseValidator, StructuredResponse,
    ResponseMetrics, ResponseCache, ReasonCode,
    get_parse_stats, reset_stats,
)

class TestResponseSchema:
    def setup_method(self):
        reset_stats()  # Clean state for each test

    def test_direct_parse(self):
        json_str = '{"answer": "test", "items_shown": 5, "items_total": 10}'
        result, fallback = ResponseParser.parse_with_fallbacks(json_str)

        assert result is not None
        assert fallback == "direct_parse"
        assert result.items_shown == 5
        assert result.items_total == 10

    def test_extract_from_markdown(self):
        md_text = '```json\n{"answer": "test", "items_shown": 3}\n```'
        result, fallback = ResponseParser.parse_with_fallbacks(md_text)

        assert result is not None
        assert fallback == "extracted_json"

    def test_invariant_violation(self):
        # items_total < items_shown should fail
        invalid = {"answer": "test", "items_shown": 10, "items_total": 5}
        is_valid, errors, reason = ResponseValidator.validate(invalid)

        assert not is_valid
        assert reason == ReasonCode.INVARIANT_VIOLATION
        assert "'items_total' must be >= 'items_shown'" in errors

    def test_metrics_tracking(self):
        ResponseParser.parse_with_fallbacks('{"answer": "a", "items_shown": 1}')
        ResponseParser.parse_with_fallbacks('not json')

        stats = get_parse_stats()
        assert stats["parsing"]["counters"]["direct_parse_ok"] == 1
        assert stats["parsing"]["counters"]["final_failed"] == 1
        assert stats["slo"]["success_rate"] == 0.5
```

### Integration Test (from test_implementation_quality.py)

```python
async def test_transparency(self) -> TestSuite:
    """Test transparency features using structured output validation."""
    from src.response_schema import ResponseParser, ResponseValidator

    response, _ = await self.elysia.query("What ADRs exist?")

    # Parse structured response
    structured, fallback_used = ResponseParser.parse_with_fallbacks(response)

    if structured:
        # Deterministic validation of invariants
        has_items_shown = structured.items_shown >= 0
        has_items_total = structured.items_total is not None
        valid_invariant = structured.items_total >= structured.items_shown

        passed = has_items_shown and has_items_total and valid_invariant
```

---

## Observability & SLOs

### Key Metrics

| Metric | Type | SLO Target | Alert Threshold |
|--------|------|------------|-----------------|
| `success_rate` | Gauge | ≥ 99.5% | < 95% |
| `direct_parse_ok` | Counter | High | N/A |
| `extract_ok` | Counter | Low | Spike > 10% |
| `repair_ok` | Counter | Very Low | Spike > 5% |
| `final_failed` | Counter | Near Zero | Any sustained increase |
| `latency.total.avg_ms` | Gauge | < 50ms | > 200ms |

### Dashboard Queries (Prometheus)

```promql
# Success rate
sum(response_parse_direct_parse_ok + response_parse_extract_ok + response_parse_repair_ok)
/
sum(response_parse_direct_parse_ok + response_parse_extract_ok + response_parse_repair_ok + response_parse_final_failed)

# Fallback rate (extract + repair)
(response_parse_extract_ok + response_parse_repair_ok)
/
(response_parse_direct_parse_ok + response_parse_extract_ok + response_parse_repair_ok)

# Cache hit rate
response_cache_hits / (response_cache_hits + response_cache_misses)
```

### Alerting Rules

```yaml
groups:
  - name: response_parsing
    rules:
      - alert: LowParseSuccessRate
        expr: response_parse_success_rate < 0.95
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Response parsing success rate below 95%"

      - alert: HighFallbackRate
        expr: response_parse_extract_ok / response_parse_direct_parse_ok > 0.1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High JSON extraction fallback rate"
```

---

## Future Considerations

### Planned Enhancements

1. **Schema Version 1.1** (Additive)
   - Add `confidence` field for response confidence scoring
   - Add `metadata` field for arbitrary key-value pairs

2. **Schema Version 2.0** (Breaking)
   - Rename `answer` to `response` for consistency
   - Add `citations` array with structured source references
   - Deprecate `transparency_statement` in favor of generated messages

3. **Advanced Caching**
   - Redis backend for distributed caching
   - Cache warming for common queries
   - Negative caching for known failures

4. **Enhanced Repair**
   - LLM-based JSON repair for complex cases
   - Learning from repair patterns

### Migration Path

```python
# Support both v1 and v2 during transition
SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1.1", "2.0"}

@classmethod
def get_required_fields(cls, version: str) -> set[str]:
    if version.startswith("1."):
        return {"answer", "items_shown"}
    elif version.startswith("2."):
        return {"response", "items_shown", "citations"}
    return cls.REQUIRED_FIELDS_V1  # Fallback
```

---

## Appendix

### Full Module Path

```
src/response_schema.py
```

### Dependencies

- Python 3.11+
- Standard library only (json, re, hashlib, threading, time, dataclasses, enum, typing)

### Related Files

| File | Purpose |
|------|---------|
| `src/elysia_agents.py` | Integration with RAG system |
| `tests/test_implementation_quality.py` | Integration tests |
| `docs/STRUCTURED_RESPONSE_IMPLEMENTATION.md` | This document |

### Commit History

| Commit | Description |
|--------|-------------|
| `fd34503` | Add enterprise-grade structured JSON response schema |
| `ab2a930` | Add P3 metrics tracking, caching, and P4 schema versioning |

---

*Document generated: 2026-02-07*
*Last updated: 2026-02-07*
