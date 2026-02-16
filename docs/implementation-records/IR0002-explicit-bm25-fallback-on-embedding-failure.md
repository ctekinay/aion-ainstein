---
parent: Implementation Records
nav_order: 2
title: IR0002 Explicit BM25 Fallback on Embedding Failure
status: accepted
date: 2026-02-08

driver: Claude Code
approvers: Lead Dev
contributors: Dev Team
informed: AInstein Development Team
---

# IR0002 Explicit BM25 Fallback on Embedding Failure

## Context and Problem Statement

The AInstein RAG system uses **hybrid search** (combining BM25 keyword search with vector semantic search) for document retrieval. The hybrid search requires both a text query and a vector embedding of that query.

When the Ollama embedding service fails (network timeout, service unavailable, model not loaded), the previous implementation:
1. Caught the exception
2. Set `query_vector = None`
3. Still called `collection.query.hybrid()` with `vector=None`

**The Problem:** Passing `None` as the vector to hybrid search is undefined behavior. Weaviate may:
- Ignore the vector component entirely (effectively doing keyword-only search, but unpredictably)
- Return an error
- Produce degraded or random results

This violates the principle of **explicit degradation** - the system should clearly and predictably fall back to a known-good mode, not rely on undefined behavior.

> **Scope note:** This issue specifically affects the Ollama provider path, where collections use `vectorizer: none` and embeddings are computed client-side (workaround for Weaviate bug #8406). OpenAI collections use server-side vectorization and would handle missing client vectors differently. This ADR addresses the Ollama path only.

## Decision Drivers

* **Explicit over implicit:** Code should clearly express intent, not rely on library quirks
* **Graceful degradation:** System must continue working when Ollama is unavailable
* **Predictable behavior:** Same failure mode should produce same fallback behavior
* **Observability:** Operators should know when fallback is active (via logs)
* **Minimal change:** P0 fix should have smallest possible blast radius

## Considered Options

1. **Do Nothing** - Continue passing `None` to hybrid(), hope Weaviate handles it
2. **Return Empty Results** - Fail closed, return no results on embedding failure
3. **Retry with Backoff** - Keep trying to get embeddings, potentially blocking for minutes
4. **Circuit Breaker with Zero Vector** - Return `[0.0] * 768` as fallback embedding
5. **Explicit BM25 Fallback** - Use `collection.query.bm25()` instead of `hybrid()`

## Decision Outcome

**Chosen option: "Explicit BM25 Fallback"** - When embedding generation fails, explicitly switch to keyword-only BM25 search.

### Why Not Other Options?

| Option | Problem |
|--------|---------|
| Do Nothing | Undefined behavior, unpredictable results |
| Return Empty | Too aggressive, user gets no results for valid queries |
| Retry with Backoff | Blocks user, doesn't help if Ollama is truly down |
| Zero Vector | **Actively harmful** - zero vector still participates in hybrid scoring, biasing results toward documents that happen to be "close" to the zero vector in embedding space |

### Why Explicit BM25?

1. **BM25 is a real search algorithm** - It's what hybrid search uses for the keyword component anyway
2. **No vector = no vector search** - Logically correct: if we can't compute a vector, don't do vector search
3. **Known quality characteristics** - BM25 behavior is well-understood and documented
4. **Already in Weaviate** - No new dependencies or infrastructure

## Implementation Details

### Code Changes

**File:** `src/chat_ui.py` (lines 717-726)

```python
# Before
query_vector = None
if provider == "ollama":
    try:
        query_vector = embed_text(question)
    except Exception as e:
        logger.error(f"Failed to compute query embedding: {e}")

# After
query_vector = None
use_keyword_only = False
if provider == "ollama":
    try:
        query_vector = embed_text(question)
    except Exception as e:
        logger.warning(f"Embedding failed, using keyword-only search: {e}")
        use_keyword_only = True
```

**File:** `src/chat_ui.py` (each collection query, e.g., lines 738-751)

```python
# Before
results = collection.query.hybrid(
    query=question,
    vector=query_vector,  # Could be None!
    limit=adr_limit,
    alpha=settings.alpha_default,
    filters=content_filter,
)

# After
if use_keyword_only:
    results = collection.query.bm25(
        query=question,
        limit=adr_limit,
        filters=content_filter,
    )
else:
    results = collection.query.hybrid(
        query=question,
        vector=query_vector,
        limit=adr_limit,
        alpha=settings.alpha_default,
        filters=content_filter,
    )
```

### Key Design Decisions

1. **Single flag, not per-collection:** One `use_keyword_only` flag controls all collections. If embedding failed once, it will fail again - no point retrying for each collection.

2. **Warning, not error:** Changed log level from `error` to `warning` because we're handling the failure gracefully. Errors imply something is broken; warnings indicate degraded operation.

3. **No retry in this path:** The `embed_text()` function does not have retry logic (only `embed_batch()` does). Adding retries here is a P1 improvement; for P0, immediate fallback to BM25 is the safest approach.

4. **Filters still applied:** BM25 queries still use the same `content_filter` as hybrid queries. Filtering logic is unchanged.

## Consequences

### Good

* **Predictable behavior:** Embedding failure always results in BM25 search
* **Continued operation:** Users get search results even when Ollama is down
* **Observable:** Log message clearly indicates fallback mode
* **Minimal code change:** ~30 lines changed, no new dependencies
* **Same API surface:** Return type and structure unchanged

### Bad

* **Reduced quality:** BM25 is less capable than hybrid search for semantic queries
  - "What's the policy on renewable energy?" may miss documents about "sustainable power"
  - Acceptable for P0 fix; P1 could add retry with circuit breaker

* **No operator notification:** Logs aren't dashboards; extended fallback may go unnoticed
  - P2 could add metrics: `rag_embedding_fallback_total`

### Neutral

* **Performance:** BM25 is actually faster than hybrid (no vector computation on Weaviate side)
* **Consistency:** All 4 collections use same fallback logic

## Architecture Mapping

This decision relates to the **Retrieval Layer** in the RAG architecture:

```
┌─────────────────────────────────────────────────────────────┐
│ User Query                                                  │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Embedding Generation (Ollama)                               │
│                                                             │
│   Success: query_vector = [0.12, -0.34, ...]               │
│   Failure: use_keyword_only = True  ← THIS DECISION        │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Weaviate Query                                              │
│                                                             │
│   Normal:   hybrid(query, vector, alpha)                   │
│   Fallback: bm25(query)  ← THIS DECISION                   │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Results → Abstention Check → LLM Generation → Response     │
└─────────────────────────────────────────────────────────────┘
```

## Why Not Circuit Breaker with Zero Vector?

This was explicitly rejected after lead dev review. The reasoning:

**Zero vector is actively harmful, not neutral:**

```python
# What seems logical:
if embedding_fails:
    return [0.0] * 768  # "Neutral" fallback

# What actually happens in hybrid search:
score = alpha * vector_similarity(query_vec, doc_vec) + (1-alpha) * bm25_score

# With zero vector:
vector_similarity([0,0,...,0], doc_vec) = ???
# This isn't "ignore vector" - it's "compare to arbitrary point in space"
# Documents that happen to be near the origin get boosted/penalized
```

**The correct mental model:**
- `None` vector → "I don't have a vector" → undefined behavior
- Zero vector → "Compare to the zero point" → wrong behavior
- No vector search at all → "Skip vector scoring" → correct behavior

## Future Improvements (Out of Scope for P0)

| Priority | Improvement | Rationale |
|----------|-------------|-----------|
| P1 | Circuit breaker pattern | Don't hammer Ollama if it's down; fail fast |
| P1 | Retry with exponential backoff | Transient failures may recover |
| P2 | `rag_embedding_fallback_total` metric | Dashboard visibility |
| P2 | Health check endpoint | Is Ollama up before we need it? |
| P3 | Graceful degradation notification | Tell user "using simplified search" |

## Codebase References

| File | Purpose | Key Changes |
|------|---------|-------------|
| `src/chat_ui.py` | Main retrieval function | `use_keyword_only` flag, BM25 fallback |
| `src/weaviate/embeddings.py` | Embedding client | No changes (already raises on failure) |
| `src/skills/filters.py` | Filter construction | No changes (filters work with BM25) |

## Validation

To verify this fix works correctly:

1. **Unit test (manual):**
   ```python
   # Simulate Ollama being down
   with patch('src.weaviate.embeddings.embed_text', side_effect=Exception("Connection refused")):
       results, context, time_ms = await perform_retrieval("What ADRs exist?")
       assert len(results) > 0  # Should still get results via BM25
   ```

2. **Integration test:**
   ```bash
   # Stop Ollama
   docker stop ollama

   # Query should still work (with warning in logs)
   curl -X POST http://localhost:8000/chat -d '{"question": "What ADRs exist?"}'

   # Check logs for: "Embedding failed, using keyword-only search"
   ```

3. **Log verification:**
   ```
   WARNING - Embedding failed, using keyword-only search: Connection refused
   ```
   (Not ERROR - we handled it gracefully)

## Decision History

| Date | Change | Author |
|------|--------|--------|
| 2026-02-08 | Initial implementation of explicit BM25 fallback | Claude Code |
| 2026-02-08 | Reviewed and approved by lead dev | Lead Dev |

---

*This ADR documents a technical decision made during the AION-AInstein development. For questions, contact the ESA team.*
