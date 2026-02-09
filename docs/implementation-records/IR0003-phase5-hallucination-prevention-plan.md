---
parent: Implementation Records
nav_order: 3
title: IR0003 Phase 5 - Hallucination Prevention Enhancement Plan
status: approved
date: 2026-02-09

driver: Cagri Tekinay
approvers: ESA Team
contributors:
informed: AInstein Development Team
---

# IR0003 Phase 5 - Hallucination Prevention Enhancement Plan

## Executive Summary

Phase 5 enhances the hallucination prevention system established in IR0001. This plan follows enterprise RAG best practices:

1. **Correctness first** (prevent incorrect answers)
2. **Then quality tuning** (thresholds with evaluation harness)
3. **Then resilience** (circuit breaker, fallbacks)
4. **Then UX** (clarification, suggestions)

**Rationale**: Tuning thresholds before locking down the "terminology truth source" can produce confident-sounding hallucinations for missing terms — the worst failure mode.

## Implementation Order

| Priority | Gap | Name | Rationale |
|----------|-----|------|-----------|
| 1 | A | SKOSMOS-First Terminology | Lock down truth source before tuning |
| 2 | F | Minimal Observability | Prove improvements, enable debugging |
| 3 | B | Threshold Tuning | Quality tuning with evaluation harness |
| 4 | D | Circuit Breaker | Resilience for production |
| 5 | C+E | UX Improvements | Clarification and suggestions |

---

## Gap A: SKOSMOS-First Terminology Verification (REQUIRED)

### Problem Statement

When asked about terminology (e.g., "What is CIMXML?"), the system currently:
- Searches all collections without prioritizing SKOSMOS
- May return documents that mention a term without defining it
- Can hallucinate definitions for terms not in SKOSMOS

### Solution

Implement SKOSMOS-first lookup with explicit behavior for hit, miss, and timeout scenarios.

### Requirements

#### Terminology Intent Detection (Acceptance Condition 1)

The system MUST detect terminology queries using explicit pattern matching:

**Terminology Query Patterns (ROUTE TO SKOSMOS):**

| Pattern Type | Examples | Regex Pattern |
|--------------|----------|---------------|
| "What is X" | "What is CIMXML?", "What is CIM?" | `^what\s+is\s+(.+)\??$` |
| "Define X" | "Define voltage regulation" | `^define\s+(.+)$` |
| "Meaning of X" | "Meaning of asset management" | `^(meaning|definition)\s+of\s+(.+)$` |
| "CIM term X" | "CIM term transformer" | `^(cim|skosmos)\s+term\s+(.+)$` |
| "Explain the term X" | "Explain the term CGMES" | `^explain\s+(the\s+)?term\s+(.+)$` |
| "What does X mean" | "What does IEC 61970 mean?" | `^what\s+does\s+(.+)\s+mean\??$` |

**Non-Terminology Exclusions (DO NOT ROUTE TO SKOSMOS):**

| Pattern Type | Examples | Reason |
|--------------|----------|--------|
| ADR references | "ADR-0031", "What does ADR.0031 decide?" | Entity query, not terminology |
| List commands | "List ADRs", "Show all principles" | Retrieval query |
| Decision queries | "What is decided about TLS?" | Semantic query, not definition |
| "What" + action verb | "What should I use for encryption?" | Advice query |
| Specific document refs | "What is in the CIM policy?" | Document content query |

**Detection Logic:**

```python
def is_terminology_query(query: str) -> tuple[bool, str | None]:
    """
    Returns (is_terminology, extracted_term)

    MUST check exclusions FIRST before pattern matching.
    """
    query_lower = query.lower().strip()

    # EXCLUSION PATTERNS - check first
    exclusions = [
        r'adr[.\-\s]?\d+',           # ADR references
        r'^list\s+',                   # List commands
        r'^show\s+(all|me)',           # Show commands
        r'what\s+(should|can|will)',   # Advice queries
        r'(in|from)\s+the\s+\w+\s+(policy|adr|principle)',  # Document refs
        r'(decision|decided)\s+(about|on|for)',  # Decision queries
    ]
    for pattern in exclusions:
        if re.search(pattern, query_lower):
            return False, None

    # TERMINOLOGY PATTERNS - only if no exclusion matched
    terminology_patterns = [
        (r'^what\s+is\s+(?:a\s+|an\s+|the\s+)?(.+?)\??$', 1),
        (r'^define\s+(.+)$', 1),
        (r'^(?:meaning|definition)\s+of\s+(.+)$', 1),
        (r'^(?:cim|skosmos)\s+term\s+(.+)$', 1),
        (r'^explain\s+(?:the\s+)?term\s+(.+)$', 1),
        (r'^what\s+does\s+(.+?)\s+mean\??$', 1),
    ]
    for pattern, group in terminology_patterns:
        match = re.search(pattern, query_lower)
        if match:
            return True, match.group(group).strip()

    return False, None
```

**Test Cases for Intent Detection:**

| Test ID | Query | Expected Result | Reason |
|---------|-------|-----------------|--------|
| INTENT-01 | "What is CIMXML?" | `(True, "cimxml")` | Standard terminology |
| INTENT-02 | "Define voltage regulation" | `(True, "voltage regulation")` | Define pattern |
| INTENT-03 | "ADR-0031" | `(False, None)` | ADR reference exclusion |
| INTENT-04 | "List ADRs about security" | `(False, None)` | List command exclusion |
| INTENT-05 | "What is the TLS decision in ADRs?" | `(False, None)` | Decision query exclusion |
| INTENT-06 | "What should I use for encryption?" | `(False, None)` | Advice query exclusion |
| INTENT-07 | "CIM term transformer" | `(True, "transformer")` | CIM term pattern |

#### Core Behavior

| Scenario | System Behavior |
|----------|-----------------|
| SKOSMOS match found | Use SKOSMOS definition, cite SKOSMOS in sources |
| SKOSMOS returns nothing | Abstain OR ask clarifying question (never invent) |
| SKOSMOS timeout | Indicate inability to verify terminology |

#### SKOSMOS Client Behavior (Acceptance Condition 2)

**Locked-Down Specifications:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Timeout** | 300ms | p95 impact: adds ~300ms worst-case; p50 expected: ~50ms |
| **Cache TTL** | 10 minutes | Balance freshness vs. SKOSMOS load |
| **Cache Max Size** | 5,000 entries | ~500KB memory at ~100 bytes/entry |
| **Cache Type** | LRU in-memory | Simplest; upgrade to Redis if horizontal scaling needed |
| **Cache Key** | `normalize(term)` = lowercase, trim, collapse whitespace | Deterministic normalization |

**Failure Policy (ABSTAIN for strict correctness):**

| Scenario | Behavior | Metric |
|----------|----------|--------|
| SKOSMOS returns definition | Use definition, cite SKOSMOS | `skosmos_hit_total` |
| SKOSMOS returns nothing | **ABSTAIN** with reason `terminology_not_found` | `skosmos_miss_total` |
| SKOSMOS timeout (>300ms) | **ABSTAIN** with reason `terminology_timeout` | `skosmos_timeout_total` |
| SKOSMOS error (5xx, network) | **ABSTAIN** with reason `terminology_error` | `skosmos_error_total` |
| Cache hit | Return cached definition | `skosmos_cache_hit_total` |

**Rationale for ABSTAIN over "proceed unverified":**
- For pure terminology questions, an unverified answer is worse than no answer
- Users asking "What is X?" expect authoritative definitions
- "I cannot verify this terminology" is honest and actionable
- Avoids hallucinating definitions for made-up terms

**Required Counters (Prometheus-style):**

```python
# All counters MUST be implemented and increment correctly
skosmos_lookup_total         # All lookup attempts (hit + miss + timeout + error)
skosmos_hit_total            # Term found in SKOSMOS (not cache)
skosmos_miss_total           # Term not found (SKOSMOS returned empty)
skosmos_timeout_total        # Lookup exceeded 300ms
skosmos_error_total          # SKOSMOS returned error (5xx, network failure)
skosmos_cache_hit_total      # Served from local cache
```

**Client Interface Contract:**

```python
class SKOSMOSClient:
    def __init__(
        self,
        base_url: str,
        timeout_ms: int = 300,
        cache_ttl_seconds: int = 600,
        cache_max_size: int = 5000,
    ):
        ...

    def lookup(self, term: str) -> SKOSMOSResult:
        """
        Returns:
            SKOSMOSResult with:
            - found: bool
            - definition: str | None
            - source_uri: str | None
            - cached: bool
            - latency_ms: int

        Raises:
            SKOSMOSTimeout: if lookup exceeds timeout_ms
            SKOSMOSError: if SKOSMOS returns error

        Side effects:
            - Increments appropriate counter
            - Logs with request_id
        """
```

**Test Cases for SKOSMOS Client:**

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| SKOS-CLIENT-01 | Normal lookup, term exists | `found=True`, `skosmos_hit_total++` |
| SKOS-CLIENT-02 | Normal lookup, term not found | `found=False`, `skosmos_miss_total++` |
| SKOS-CLIENT-03 | Lookup exceeds 300ms | `SKOSMOSTimeout` raised, `skosmos_timeout_total++` |
| SKOS-CLIENT-04 | SKOSMOS returns 500 | `SKOSMOSError` raised, `skosmos_error_total++` |
| SKOS-CLIENT-05 | Second lookup for same term | `cached=True`, `skosmos_cache_hit_total++` |
| SKOS-CLIENT-06 | Cache expired (>10min) | Fresh lookup, `skosmos_lookup_total++` |

### Acceptance Criteria

```gherkin
Feature: SKOSMOS-First Terminology Verification

  Scenario: SKOSMOS match exists
    Given a terminology query "What is CIMXML?"
    And SKOSMOS contains the concept "CIMXML"
    When the system processes the query
    Then the response MUST use the SKOSMOS definition
    And the response MUST cite SKOSMOS in sources
    And skosmos_hit_total MUST increment

  Scenario: SKOSMOS returns nothing
    Given a terminology query "What is FooBarBaz?"
    And SKOSMOS does not contain "FooBarBaz"
    When the system processes the query
    Then the system MUST abstain OR ask clarifying question
    And the system MUST NOT invent a definition
    And skosmos_miss_total MUST increment
    And rag_abstention_total{reason="terminology_not_found"} MUST increment

  Scenario: SKOSMOS timeout
    Given a terminology query "What is CIMXML?"
    And SKOSMOS is slow (>500ms)
    When the system processes the query
    Then the response MUST indicate inability to verify
    And the system MUST NOT invent a definition
    And skosmos_timeout_total MUST increment

  Scenario: Ambiguous term
    Given a terminology query "What is CIM?"
    And SKOSMOS contains multiple CIM concepts
    When the system processes the query
    Then the system SHOULD ask for clarification
    Or the system SHOULD list all matching concepts
```

### Test Cases Required

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| SKOS-01 | Known term (CIMXML) | SKOSMOS definition cited |
| SKOS-02 | Unknown term (FooBar) | Abstention, no hallucination |
| SKOS-03 | Timeout simulation | "Unable to verify" message |
| SKOS-04 | Ambiguous term (CIM) | Clarification or list |
| SKOS-05 | Cache hit | Fast response, cache counter |

### Implementation Location

| File | Changes |
|------|---------|
| `src/skosmos_client.py` | New: SKOSMOS lookup with caching |
| `src/elysia_agents.py` | Integrate SKOSMOS-first for terminology |
| `src/config.py` | Add SKOSMOS timeout/cache settings |
| `tests/test_skosmos_integration.py` | New: All test scenarios |

---

## Gap F: Minimal Observability (REQUIRED EARLY)

### Problem Statement

Without observability, we cannot:
- Prove that Phase 5 changes improve quality
- Debug production issues
- Measure abstention rates and reasons

### Requirements (Acceptance Condition 3)

#### Counters with Labels (Prometheus-style)

```python
# Abstention metrics - WITH reason labels
rag_abstention_total{reason="no_results"}
rag_abstention_total{reason="low_confidence"}
rag_abstention_total{reason="terminology_not_found"}
rag_abstention_total{reason="terminology_timeout"}
rag_abstention_total{reason="entity_not_found"}

# SKOSMOS metrics - WITH backend label
skosmos_lookup_total{backend="skosmos"}
skosmos_hit_total{backend="skosmos"}
skosmos_miss_total{backend="skosmos"}
skosmos_timeout_total{backend="skosmos"}
skosmos_error_total{backend="skosmos"}
skosmos_cache_hit_total{backend="cache"}

# Embedding metrics - WITH collection label
embedding_request_total{collection="ADR_Ollama"}
embedding_fail_total{collection="ADR_Ollama"}
embedding_fallback_total{collection="ADR_Ollama"}

# Retrieval metrics - WITH collection label
retrieval_request_total{collection="ADR_Ollama"}
retrieval_latency_ms{collection="ADR_Ollama"}  # histogram buckets

# Circuit breaker metrics (for Gap D)
circuit_breaker_state{service="embeddings"}  # gauge: 0=closed, 1=half-open, 2=open
circuit_breaker_trip_total{service="embeddings"}
```

#### Request Correlation (REQUIRED)

All log entries and metrics MUST support request correlation:

**Required Log Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | string | UUID generated at request entry point |
| `route` | string | "tree" (multi-collection) or "direct" (single collection) |
| `fallback_flags` | list[str] | Active fallbacks: ["bm25_only", "skosmos_timeout", "circuit_open"] |
| `timestamp` | string | ISO 8601 with milliseconds |
| `level` | string | INFO, WARN, ERROR |
| `component` | string | "router", "skosmos", "weaviate", "llm" |

**Log Structure Contract:**

```python
@dataclass
class RequestContext:
    request_id: str
    route: Literal["tree", "direct"]
    fallback_flags: list[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)

    def add_fallback(self, flag: str) -> None:
        """Add fallback flag (e.g., 'bm25_only', 'skosmos_timeout')"""
        if flag not in self.fallback_flags:
            self.fallback_flags.append(flag)

    def to_log_context(self) -> dict:
        return {
            "request_id": self.request_id,
            "route": self.route,
            "fallback_flags": self.fallback_flags,
            "elapsed_ms": (datetime.utcnow() - self.start_time).total_seconds() * 1000,
        }
```

**Example Correlated Log Entries (same request_id):**

```json
{"request_id": "req-abc123", "timestamp": "2026-02-09T10:30:00.000Z", "level": "INFO", "component": "router", "event": "request_start", "route": "tree", "query": "What is CIMXML?"}
{"request_id": "req-abc123", "timestamp": "2026-02-09T10:30:00.050Z", "level": "INFO", "component": "skosmos", "event": "lookup_complete", "term": "CIMXML", "hit": true, "cached": false, "latency_ms": 45}
{"request_id": "req-abc123", "timestamp": "2026-02-09T10:30:00.120Z", "level": "INFO", "component": "router", "event": "request_complete", "route": "tree", "fallback_flags": [], "total_ms": 120}
```

**Fallback Scenario Example:**

```json
{"request_id": "req-def456", "timestamp": "2026-02-09T10:31:00.000Z", "level": "INFO", "component": "router", "event": "request_start", "route": "tree", "query": "List ADRs"}
{"request_id": "req-def456", "timestamp": "2026-02-09T10:31:00.320Z", "level": "WARN", "component": "skosmos", "event": "timeout", "term": null, "latency_ms": 300}
{"request_id": "req-def456", "timestamp": "2026-02-09T10:31:00.350Z", "level": "WARN", "component": "embeddings", "event": "circuit_open", "service": "embeddings"}
{"request_id": "req-def456", "timestamp": "2026-02-09T10:31:00.500Z", "level": "INFO", "component": "router", "event": "request_complete", "route": "tree", "fallback_flags": ["bm25_only", "circuit_open"], "total_ms": 500}
```

### Implementation Location

| File | Changes |
|------|---------|
| `src/observability.py` | New: Metrics registry, counters, RequestContext |
| `src/elysia_agents.py` | Add metric increments, pass RequestContext |
| `src/skosmos_client.py` | Add SKOSMOS metrics with request_id |
| `src/config.py` | Add observability settings |

### Acceptance Criteria

- [ ] All listed counters are implemented with labels and increment correctly
- [ ] `request_id` is generated at entry point and propagated through all components
- [ ] `route` field is set correctly ("tree" or "direct")
- [ ] `fallback_flags` accumulate as fallbacks activate
- [ ] Structured logs include all required fields
- [ ] Metrics can be exported (JSON endpoint or Prometheus format)
- [ ] CLI command `python -m src.observability --dump` shows current metrics

### Test Cases for Observability

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| OBS-01 | Normal request | Logs have same `request_id`, `fallback_flags=[]` |
| OBS-02 | SKOSMOS timeout | `fallback_flags` includes `"skosmos_timeout"` |
| OBS-03 | Circuit breaker open | `fallback_flags` includes `"circuit_open"` |
| OBS-04 | BM25 fallback | `fallback_flags` includes `"bm25_only"` |
| OBS-05 | Multiple fallbacks | `fallback_flags` contains all active flags |
| OBS-06 | Counter increment | Metrics match expected counts after N requests |

---

## Gap B: Per-Collection Threshold Tuning (AFTER A + F)

### Problem Statement

Current global thresholds may not be optimal for each collection:
- SKOSMOS vocabulary queries need different thresholds than ADR queries
- Tuning without evaluation harness leads to "tuning to noise"

### Requirements (Acceptance Condition 4)

#### Evaluation Harness

| Requirement | Specification |
|-------------|---------------|
| Golden set file | `data/evaluation/golden_queries.jsonl` |
| Format | See schema below |
| Versioning | **Git commit hash** in evaluation output; changes require PR review |
| Minimum size | 50+ queries covering all collections |

#### Golden Set Schema (Versioned)

```jsonl
// Each line is a JSON object with required fields
{
  "id": "GS-001",
  "query": "What is CIMXML?",
  "category": "terminology_hit",
  "expected": {
    "route": "skosmos",
    "abstain": false,
    "doc_types": ["Vocabulary"],
    "doc_ids": ["vocab-cimxml"],
    "source": "SKOSMOS"
  },
  "tags": ["skosmos", "positive"]
}
```

#### Required Test Categories (Negative Cases Included)

The golden set MUST include at least one query for each category:

| Category | Description | Min Count | Example Query |
|----------|-------------|-----------|---------------|
| `terminology_hit` | Known term in SKOSMOS | 5 | "What is CIMXML?" |
| `terminology_miss` | Unknown term NOT in SKOSMOS | 3 | "What is FooBarBaz?" |
| `terminology_ambiguous` | Term with multiple meanings | 2 | "What is CIM?" |
| `terminology_timeout` | Simulated SKOSMOS timeout | 2 | "Define TEST_TIMEOUT_TRIGGER" |
| `non_terminology_define` | Contains "define" but NOT terminology | 3 | "Define the TLS requirements in ADRs" |
| `non_terminology_list` | Contains list-like words | 3 | "List all principles about security" |
| `adr_retrieval` | ADR document query | 5 | "What does ADR-0012 decide?" |
| `principle_retrieval` | Principle document query | 3 | "What are the interoperability principles?" |
| `policy_retrieval` | Policy document query | 3 | "What is the data retention policy?" |
| `entity_not_found` | Query for non-existent entity | 3 | "What does ADR-9999 decide?" |
| `semantic_search` | Complex semantic query | 5 | "How do we ensure grid stability?" |
| `cross_collection` | Query spanning collections | 3 | "Security decisions and principles" |

**Total minimum: 40 queries** (10 used as seed, 30+ additions for coverage)

#### Negative Test Case Requirements

**Non-terminology queries that contain "define/list" words:**

```jsonl
{"id": "GS-NEG-001", "query": "Define the encryption requirements in ADR-0015", "category": "non_terminology_define", "expected": {"route": "adr", "abstain": false, "doc_types": ["ADR"]}}
{"id": "GS-NEG-002", "query": "List all ADRs about authentication", "category": "non_terminology_list", "expected": {"route": "adr", "abstain": false, "doc_types": ["ADR"]}}
{"id": "GS-NEG-003", "query": "What is decided about TLS versions?", "category": "non_terminology_define", "expected": {"route": "adr", "abstain": false, "doc_types": ["ADR"]}}
```

**SKOSMOS timeout simulation:**

```jsonl
{"id": "GS-TIMEOUT-001", "query": "Define __TEST_SKOSMOS_TIMEOUT__", "category": "terminology_timeout", "expected": {"route": "skosmos", "abstain": true, "reason": "terminology_timeout"}}
```

(The SKOSMOS client MUST recognize `__TEST_SKOSMOS_TIMEOUT__` as a test trigger and simulate timeout)

#### Evaluation Script (Acceptance Condition 5)

Location: `scripts/eval_rag_quality.py`

```bash
# Usage
python scripts/eval_rag_quality.py --config config/thresholds.yaml --output results.json

# Required output metrics
{
  "meta": {
    "timestamp": "2026-02-09T10:30:00Z",
    "config_hash": "abc123",
    "golden_set_hash": "def456",           # Git blob hash of golden_queries.jsonl
    "golden_set_version": "v1.2.0",         # Semantic version tag
    "total_queries": 50,
    "pass_count": 47,
    "fail_count": 3
  },
  "metrics": {
    "overall": {
      "precision": 0.85,
      "recall": 0.90,
      "f1": 0.87
    },
    "by_collection": {
      "ADR_Ollama": {"precision": 0.88, "recall": 0.92, "f1": 0.90, "count": 15},
      "Vocabulary_Ollama": {"precision": 0.95, "recall": 0.85, "f1": 0.90, "count": 10},
      "Principle_Ollama": {"precision": 0.82, "recall": 0.88, "f1": 0.85, "count": 8},
      "Policy_Ollama": {"precision": 0.80, "recall": 0.85, "f1": 0.82, "count": 7}
    },
    "abstention": {
      "total_rate": 0.05,
      "by_reason": {
        "no_results": 0.01,
        "low_confidence": 0.02,
        "terminology_not_found": 0.01,
        "terminology_timeout": 0.005,
        "entity_not_found": 0.005
      }
    },
    "latency": {
      "p50_ms": 120,
      "p95_ms": 450,
      "p99_ms": 800,
      "max_ms": 1200
    }
  },
  "failures": [
    {
      "id": "GS-015",
      "query": "...",
      "expected": {...},
      "actual": {...},
      "reason": "wrong_collection"
    }
  ]
}
```

**CI Integration:**

```yaml
# .github/workflows/rag-quality.yml
- name: Run RAG Quality Evaluation
  run: |
    python scripts/eval_rag_quality.py \
      --config config/thresholds.yaml \
      --output results.json \
      --baseline baseline.json

- name: Check for Regressions
  run: |
    python scripts/check_regression.py \
      --current results.json \
      --baseline baseline.json \
      --precision-threshold 0.05 \
      --recall-threshold 0.05
```

#### Threshold Configuration

Location: `config/thresholds.yaml`

```yaml
# Per-collection thresholds
collections:
  ADR_Ollama:
    distance_threshold: 0.45
    min_query_coverage: 0.20
  Vocabulary_Ollama:
    distance_threshold: 0.35
    min_query_coverage: 0.30
  Principle_Ollama:
    distance_threshold: 0.50
    min_query_coverage: 0.15
  Policy_Ollama:
    distance_threshold: 0.50
    min_query_coverage: 0.20

# Global fallback
default:
  distance_threshold: 0.50
  min_query_coverage: 0.20
```

### Acceptance Criteria

```gherkin
Feature: Evaluation-Driven Threshold Tuning

  Scenario: Threshold change produces diff report
    Given a golden set with 50+ queries
    And current thresholds in config/thresholds.yaml
    When I run scripts/eval_rag_quality.py
    Then I receive a report with before/after metrics
    And precision and recall are calculated per collection
    And p95 latency is measured

  Scenario: CI prevents silent regressions
    Given a PR that changes thresholds
    When CI runs the evaluation
    Then the PR shows metric diff
    And precision drop >5% fails the build
```

### Test Cases Required

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| THRESH-01 | Run eval with current config | Baseline metrics captured |
| THRESH-02 | Change threshold, re-run | Diff report generated |
| THRESH-03 | Precision drops >5% | CI fails |

---

## Gap D: Circuit Breaker for Embeddings (REQUIRED)

### Problem Statement

If the embedding service fails, the system should gracefully degrade to BM25-only search rather than failing completely.

### Requirements

#### Circuit Breaker States

| State | Behavior |
|-------|----------|
| Closed | Normal operation, embeddings used |
| Open | All requests use BM25 fallback |
| Half-Open | Test requests to check recovery |

#### Configuration

```yaml
circuit_breaker:
  embeddings:
    failure_threshold: 5  # Failures before opening
    success_threshold: 2  # Successes to close from half-open
    timeout_seconds: 30   # Time in open state before half-open
```

#### Explicit Fallback Behavior

| Scenario | Structured Response | Confidence | Log |
|----------|---------------------|------------|-----|
| Embeddings fail | BM25 results only | Reduced by 20% | `embedding_fallback_total` |
| Circuit open | BM25 results only | Reduced by 20% | `circuit_breaker_state{service="embeddings"}=open` |
| Recovery | Full hybrid search | Normal | `circuit_breaker_state{service="embeddings"}=closed` |

#### Confidence Reduction Definition (Acceptance Condition 6)

**Where "confidence" lives:**

The structured response schema includes a `retrieval_quality` object:

```python
@dataclass
class RetrievalQuality:
    """Retrieval quality metadata in structured response."""

    confidence_score: float          # 0.0 to 1.0
    confidence_level: str            # "high", "medium", "low"
    fallback_active: bool            # True if any fallback is active
    fallback_reasons: list[str]      # ["bm25_only", "circuit_open", ...]
    degraded: bool                   # True if confidence was reduced

    @classmethod
    def from_retrieval(
        cls,
        base_score: float,
        fallback_flags: list[str],
    ) -> "RetrievalQuality":
        """
        Calculate confidence with fallback penalty.

        Args:
            base_score: Raw confidence from retrieval (0.0-1.0)
            fallback_flags: Active fallback modes

        Returns:
            RetrievalQuality with adjusted confidence
        """
        # 20% reduction = multiply by 0.8
        FALLBACK_PENALTY = 0.8

        fallback_active = len(fallback_flags) > 0
        adjusted_score = base_score * FALLBACK_PENALTY if fallback_active else base_score

        return cls(
            confidence_score=round(adjusted_score, 3),
            confidence_level=cls._score_to_level(adjusted_score),
            fallback_active=fallback_active,
            fallback_reasons=fallback_flags,
            degraded=fallback_active,
        )

    @staticmethod
    def _score_to_level(score: float) -> str:
        if score >= 0.85:
            return "high"
        elif score >= 0.60:
            return "medium"
        else:
            return "low"
```

**Structured Response Contract:**

```python
@dataclass
class RAGResponse:
    """Complete RAG response with transparency metadata."""

    answer: str
    sources: list[Source]
    retrieval_quality: RetrievalQuality
    transparency: TransparencyStatement

@dataclass
class TransparencyStatement:
    """User-facing transparency about response quality."""

    statement: str | None            # Human-readable quality note
    show_to_user: bool               # Whether to display statement

    @classmethod
    def from_quality(cls, quality: RetrievalQuality) -> "TransparencyStatement":
        if quality.degraded:
            reasons = ", ".join(quality.fallback_reasons)
            return cls(
                statement=f"This response uses simplified search ({reasons}). Results may be less comprehensive.",
                show_to_user=True,
            )
        elif quality.confidence_level == "low":
            return cls(
                statement="Limited relevant information found. Consider rephrasing your question.",
                show_to_user=True,
            )
        else:
            return cls(statement=None, show_to_user=False)
```

**Example Response with Fallback:**

```json
{
  "answer": "The ADR-0012 decides on using CIM as the canonical data model...",
  "sources": [...],
  "retrieval_quality": {
    "confidence_score": 0.68,
    "confidence_level": "medium",
    "fallback_active": true,
    "fallback_reasons": ["bm25_only", "circuit_open"],
    "degraded": true
  },
  "transparency": {
    "statement": "This response uses simplified search (bm25_only, circuit_open). Results may be less comprehensive.",
    "show_to_user": true
  }
}
```

**Test Cases for Confidence Reduction:**

| Test ID | Scenario | Base Score | Fallback Flags | Expected Adjusted Score |
|---------|----------|------------|----------------|------------------------|
| CONF-01 | Normal operation | 0.85 | [] | 0.85 (no change) |
| CONF-02 | BM25 fallback | 0.85 | ["bm25_only"] | 0.68 (0.85 × 0.8) |
| CONF-03 | Circuit open | 0.90 | ["circuit_open"] | 0.72 (0.90 × 0.8) |
| CONF-04 | Multiple fallbacks | 0.80 | ["bm25_only", "circuit_open"] | 0.64 (0.80 × 0.8) |
| CONF-05 | Low base + fallback | 0.50 | ["bm25_only"] | 0.40 → abstain |

### Acceptance Criteria

```gherkin
Feature: Circuit Breaker for Embeddings

  Scenario: Circuit opens after failures
    Given 5 consecutive embedding failures
    When the next query arrives
    Then circuit_breaker_state{service="embeddings"} = "open"
    And the query uses BM25-only search
    And embedding_fallback_total increments

  Scenario: Circuit enters half-open after timeout
    Given circuit is open
    And 30 seconds have passed
    When the next query arrives
    Then circuit_breaker_state{service="embeddings"} = "half_open"
    And one embedding request is attempted

  Scenario: Circuit closes after recovery
    Given circuit is half-open
    And 2 consecutive embedding successes
    Then circuit_breaker_state{service="embeddings"} = "closed"
    And normal hybrid search resumes

  Scenario: Structured response during fallback
    Given circuit is open
    When a query returns results
    Then the response includes fallback_mode: true
    And confidence scores are reduced by 20%
```

### Implementation Location

| File | Changes |
|------|---------|
| `src/circuit_breaker.py` | New: Circuit breaker implementation |
| `src/weaviate/embeddings.py` | Integrate circuit breaker |
| `src/elysia_agents.py` | Handle fallback mode in responses |
| `tests/test_circuit_breaker.py` | All state transition tests |

---

## Gap C + E: UX Improvements (NICE TO HAVE)

### Gap C: Clarification Questions

When the system cannot confidently answer:
- Offer clarification options
- Suggest similar terms that exist

### Gap E: Alternative Suggestions

When abstaining:
- "Did you mean ADR-0012 (CIM Standard)?"
- Show top 3 similar items

### Acceptance Criteria

- [ ] Clarification question appears when term is ambiguous
- [ ] Alternative suggestions shown when abstaining
- [ ] User can select alternatives without retyping

**Note**: These are UX improvements and do not block Phase 5 completion unless product explicitly requires them.

---

## Phase 4 Invariants (MUST PRESERVE)

Before implementing Phase 5, verify these Phase 4 outcomes remain intact:

| Invariant | Test | Command |
|-----------|------|---------|
| Deterministic list responses | Lists return same order | `pytest tests/test_deterministic_lists.py` |
| No list route misrouting | ADR references don't misroute | `pytest tests/test_list_routing.py` |
| Migration invariants | doc_type correctly set | `python scripts/verify_doc_identity.py` |

---

## Enterprise Acceptance Conditions (REQUIRED BEFORE CODING)

All 6 conditions must be met before Phase 5 implementation begins:

| # | Condition | Section | Status |
|---|-----------|---------|--------|
| 1 | **Terminology Intent Detection**: Explicit patterns + exclusions defined | Gap A | ✅ Defined |
| 2 | **SKOSMOS Client Behavior**: Timeout (300ms), Cache (10min/5k), Failure policy (ABSTAIN), Counters | Gap A | ✅ Defined |
| 3 | **Request Correlation**: `request_id`, `route`, `fallback_flags` in all logs | Gap F | ✅ Defined |
| 4 | **Golden Set Versioning**: Commit-hash pinned, includes all required negative cases | Gap B | ✅ Defined |
| 5 | **Threshold Tuning Metrics**: precision/recall by collection, abstention by reason, p50/p95 latency, JSON output | Gap B | ✅ Defined |
| 6 | **Circuit Breaker Confidence**: Defined as `RetrievalQuality.confidence_score` field with 20% reduction rule | Gap D | ✅ Defined |

---

## Phase 5 Entry Checklist

Before starting implementation:

- [ ] All Phase 4 tests pass
- [ ] Branch `claude/phase5-hallucination-prevention-*` created
- [ ] This plan reviewed and approved
- [ ] All 6 Enterprise Acceptance Conditions confirmed in this document
- [ ] Golden set `data/evaluation/golden_queries.jsonl` exists (minimum 40 queries with required categories)

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Hallucination rate (terminology) | 0% | For queries with SKOSMOS match, response cites SKOSMOS |
| Abstention rate change | <5% increase | Measured on golden set |
| p95 latency | <100ms added | Measured on SKOSMOS lookup path |
| Precision | >85% | On golden set |
| Recall | >80% | On golden set |

---

## Timeline

| Week | Deliverable |
|------|-------------|
| 1 | Gap A: SKOSMOS-first implementation + tests |
| 1 | Gap F: Minimal observability (counters + structured logs) |
| 2 | Gap B: Evaluation harness + threshold tuning |
| 2 | Gap D: Circuit breaker implementation |
| 3 | Gap C+E: UX improvements (if required) |
| 3 | Integration testing + documentation |

---

## References

- [IR0001: Confidence-Based Abstention](./IR0001-confidence-based-abstention-for-hallucination-prevention.md)
- [IR0002: BM25 Fallback](./IR0002-explicit-bm25-fallback-on-embedding-failure.md)
- [Architecture Overview](../ARCHITECTURE.md)

---

## Decision History

| Date | Change | Author |
|------|--------|--------|
| 2026-02-09 | Initial Phase 5 plan with A→F→B→D→C/E order | Cagri Tekinay |
| 2026-02-09 | Added 6 Enterprise Acceptance Conditions | Cagri Tekinay |
| 2026-02-09 | Defined terminology intent detection patterns + exclusions | Cagri Tekinay |
| 2026-02-09 | Locked SKOSMOS client: 300ms timeout, 10min/5k cache, ABSTAIN policy | Cagri Tekinay |
| 2026-02-09 | Added request correlation (request_id, route, fallback_flags) | Cagri Tekinay |
| 2026-02-09 | Expanded golden set schema with negative test categories | Cagri Tekinay |
| 2026-02-09 | Added eval script output requirements (precision/recall, p50/p95, JSON) | Cagri Tekinay |
| 2026-02-09 | Defined confidence reduction as RetrievalQuality contract field | Cagri Tekinay |

---

*Approved: 2026-02-09*
*Order rationale: Correctness first (A), then observability (F), then quality tuning (B), then resilience (D), then UX (C+E)*
*Enterprise conditions: All 6 acceptance criteria documented and approved*
