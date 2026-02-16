# Chunking vs Full-Doc Embedding Experiment

**Date:** 2026-02-13
**Timestamp:** 2026-02-13T12:11:48.485179

## Objective

Compare retrieval accuracy between two embedding strategies:
- **Chunked**: Each document section (Context, Decision, Considered Options, etc.) stored as a separate vector
- **Full-Doc**: Entire document stored as a single vector

Both use hybrid search (BM25 + vector) with the same alpha setting.

## Summary

| Metric | Chunked | Full-Doc |
|--------|---------|----------|
| Precision@5 | 71.43% | 71.43% |
| Avg Latency | 92ms | 85ms |
| Queries Tested | 7 | 7 |

## Per-Query Results

### Chunked Strategy

| Query | Expected | Found | Rank | Top Score | Latency |
|-------|----------|-------|------|-----------|---------|
| What does ADR-0012 decide? | 0012 | Yes | 3 | 0.800 | 152ms |
| What is the domain language decision? | 0012 | Yes | 1 | 0.963 | 82ms |
| OAuth decision for API authentication | 0029 | Yes | 1 | 0.952 | 83ms |
| Tell me about ADR.0025 | 0025 | Yes | 3 | 0.825 | 85ms |
| What decision was made about event-driven architecture? | 0030 | No | - | 0.795 | 84ms |
| API design principles | 0010 | Yes | 1 | 0.904 | 78ms |
| Security principles for ESA | 0003 | No | - | 0.853 | 83ms |

### Full-Doc Strategy

| Query | Expected | Found | Rank | Top Score | Latency |
|-------|----------|-------|------|-----------|---------|
| What does ADR-0012 decide? | 0012 | Yes | 2 | 0.797 | 90ms |
| What is the domain language decision? | 0012 | Yes | 1 | 0.901 | 80ms |
| OAuth decision for API authentication | 0029 | Yes | 1 | 1.000 | 88ms |
| Tell me about ADR.0025 | 0025 | Yes | 2 | 0.790 | 90ms |
| What decision was made about event-driven architecture? | 0030 | No | - | 0.778 | 80ms |
| API design principles | 0010 | Yes | 1 | 0.916 | 83ms |
| Security principles for ESA | 0003 | No | - | 1.000 | 83ms |

## Analysis

### Both strategies fail on the same 2 queries — due to invalid test expectations

1. **"What decision was made about event-driven architecture?"** (expected: ADR-0030)
   - ADR-0030 is actually "Identification Based on Market Participant Persona" — not about event-driven architecture.
   - No ADR in the corpus covers event-driven architecture.
   - **Root cause:** Incorrect test expectation. Query replaced with "How should market participants be identified?"

2. **"Security principles for ESA"** (expected: PCP-0003)
   - PCP-0003 does not exist. Principles start at PCP-0010.
   - The closest security-related principle is PCP-0011 "Need to Know".
   - **Root cause:** Non-existent document ID. Query replaced with "Data confidentiality and access control principles" → PCP-0011.

### Corrected effective precision

Excluding the two invalid queries, both strategies achieved **5/5 (100%)** on valid queries.

### Strategy-specific observations

| Observation | Chunked | Full-Doc |
|-------------|---------|----------|
| Semantic queries (natural language) | Rank 1 for 3/3 valid | Rank 1 for 3/3 valid |
| Exact-match queries (by ID/number) | Rank 3 for both | Rank 2 for both |
| Top score on best hit | 0.963 | 1.000 |
| Avg latency | 92ms | 85ms (8% faster) |

- **Full-doc produces higher confidence scores** on strong matches (1.0 vs 0.963 for OAuth query).
- **Exact-match by document number** is weak in both strategies — neither BM25 nor vector search handles "ADR-0012" or "ADR.0025" well. Both strategies fall back to the approval record chunks/titles that contain the ID string.
- **Latency advantage for full-doc** is modest (8%) but consistent — fewer vectors to search.

## Conclusion

Based on precision@5, both strategies performed **equally** (100% on valid queries).
Latency: **full-doc** was 1.1x faster on average.

### Recommendation

**Full-doc embedding** is the recommended strategy for this corpus size (36 ADRs + 62 principles).
With equivalent precision and lower latency, the simpler full-doc approach avoids chunking complexity
while delivering the same retrieval quality.

**Next steps:**
- Re-run experiment with the corrected 2 queries to confirm 100% precision for both strategies
- Consider adding a dedicated ID-lookup path for exact-match queries ("ADR-0012", "ADR.0025") that bypasses vector search
- Re-evaluate if the corpus grows significantly or documents become much longer
