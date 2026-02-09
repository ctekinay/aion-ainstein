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

#### Core Behavior

| Scenario | System Behavior |
|----------|-----------------|
| SKOSMOS match found | Use SKOSMOS definition, cite SKOSMOS in sources |
| SKOSMOS returns nothing | Abstain OR ask clarifying question (never invent) |
| SKOSMOS timeout | Indicate inability to verify terminology |

#### Caching Requirements

| Requirement | Specification |
|-------------|---------------|
| Cache type | LRU in-memory (upgrade to Redis if needed) |
| TTL | 5-30 minutes (configurable via settings) |
| Cache key | Normalized term (lowercase, trimmed) |
| Max entries | 1000 terms (configurable) |

#### Timeout Requirements

| Requirement | Specification |
|-------------|---------------|
| Lookup timeout | 200-500ms (configurable) |
| Fallback on timeout | Label response as "unverified terminology" |
| No hallucination | Never invent definition on timeout |

#### Observability (see Gap F)

Counters:
- `skosmos_lookup_total` - All lookup attempts
- `skosmos_hit_total` - Cache or SKOSMOS hit
- `skosmos_miss_total` - Term not found
- `skosmos_timeout_total` - Lookup exceeded timeout
- `skosmos_cache_hit_total` - Served from cache

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

### Requirements

#### Counters (Prometheus-style)

```python
# Abstention metrics
rag_abstention_total{reason="no_results"}
rag_abstention_total{reason="low_confidence"}
rag_abstention_total{reason="terminology_not_found"}
rag_abstention_total{reason="entity_not_found"}

# SKOSMOS metrics (from Gap A)
skosmos_lookup_total
skosmos_hit_total
skosmos_miss_total
skosmos_timeout_total
skosmos_cache_hit_total

# Embedding metrics
embedding_request_total
embedding_fail_total
embedding_fallback_total  # BM25 fallback used

# Circuit breaker metrics (for Gap D)
circuit_breaker_state{service="embeddings"}  # open/half-open/closed
circuit_breaker_trip_total{service="embeddings"}
```

#### Structured Logging

All logs must include:
- `request_id` - Correlation ID for the request
- `timestamp` - ISO 8601 format
- `level` - INFO, WARN, ERROR
- `component` - Which system component

Example:
```json
{
  "request_id": "req-abc123",
  "timestamp": "2026-02-09T10:30:00Z",
  "level": "INFO",
  "component": "skosmos_client",
  "event": "lookup_complete",
  "term": "CIMXML",
  "hit": true,
  "latency_ms": 45
}
```

### Implementation Location

| File | Changes |
|------|---------|
| `src/observability.py` | New: Metrics registry and counters |
| `src/elysia_agents.py` | Add metric increments |
| `src/skosmos_client.py` | Add SKOSMOS metrics |
| `src/config.py` | Add observability settings |

### Acceptance Criteria

- [ ] All listed counters are implemented and increment correctly
- [ ] Structured logs include request_id on all entries
- [ ] Metrics can be exported (JSON endpoint or Prometheus format)
- [ ] Dashboard or CLI command to view current metrics

---

## Gap B: Per-Collection Threshold Tuning (AFTER A + F)

### Problem Statement

Current global thresholds may not be optimal for each collection:
- SKOSMOS vocabulary queries need different thresholds than ADR queries
- Tuning without evaluation harness leads to "tuning to noise"

### Requirements

#### Evaluation Harness

| Requirement | Specification |
|-------------|---------------|
| Golden set file | `data/evaluation/golden_queries.jsonl` |
| Format | `{"query": "...", "expected_doc_ids": [...], "expected_doc_types": [...]}` |
| Versioning | Commit-hash pinned, changes require review |
| Minimum size | 50+ queries covering all collections |

#### Evaluation Script

Location: `scripts/eval_rag_quality.py`

```bash
# Usage
python scripts/eval_rag_quality.py --config config/thresholds.yaml

# Output
{
  "timestamp": "2026-02-09T10:30:00Z",
  "config_hash": "abc123",
  "golden_set_hash": "def456",
  "metrics": {
    "precision": 0.85,
    "recall": 0.90,
    "abstention_rate": 0.05,
    "p95_latency_ms": 450
  },
  "per_collection": {
    "ADR_Ollama": {"precision": 0.88, "recall": 0.92},
    "Vocabulary_Ollama": {"precision": 0.95, "recall": 0.85}
  }
}
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

## Phase 5 Entry Checklist

Before starting implementation:

- [ ] All Phase 4 tests pass
- [ ] Branch `claude/phase5-hallucination-prevention-*` created
- [ ] This plan reviewed and approved
- [ ] Golden set `data/evaluation/golden_queries.jsonl` exists (minimum 20 queries)

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

*Approved: 2026-02-09*
*Order rationale: Correctness first (A), then observability (F), then quality tuning (B), then resilience (D), then UX (C+E)*
