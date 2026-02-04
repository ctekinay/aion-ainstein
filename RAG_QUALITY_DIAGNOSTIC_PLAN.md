# RAG Quality Diagnostic Plan

## Executive Summary

This document outlines a systematic approach to diagnose and improve RAG quality in AION-AInstein. The plan is organized into 4 phases, each targeting a specific layer of the RAG pipeline.

**Current Configuration Summary:**
- Embedding: nomic-embed-text-v2-moe (768 dimensions)
- Chunking: 6000 chars with 500 char overlap
- Hybrid Search: alpha=0.5 (50% vector, 50% BM25)
- Retrieval Limits: ADR=8, Principles=6, Policies=4, Vocab=4
- Content Truncation: 800 characters per document
- LLM: Qwen3:4b (32K context) / SmolLM3 (8K context)

---

## Phase 1: Establish Baseline Metrics & Test Cases

### 1.1 Create Gold Standard Test Set
Create 20-30 test questions across categories with expected answers:

| Category | Example Question | Expected Answer Source |
|----------|-----------------|----------------------|
| **Vocabulary** | "What is a switchgear?" | Vocabulary collection |
| **ADR Specific** | "Why did we choose Kafka over RabbitMQ?" | Specific ADR |
| **Principle Application** | "What principles guide our API design?" | Principles collection |
| **Cross-Domain** | "How do our security policies affect data architecture?" | Multiple collections |
| **Factual Detail** | "What is the status of ADR-042?" | Exact metadata match |

### 1.2 Define Quality Metrics

**Retrieval Metrics:**
- **Precision@K**: Of K retrieved docs, how many are relevant?
- **Recall@K**: Of all relevant docs, how many were retrieved in top K?
- **MRR (Mean Reciprocal Rank)**: Position of first relevant document

**Generation Metrics:**
- **Faithfulness**: Does response use only retrieved context? (no hallucination)
- **Answer Relevance**: Does response actually answer the question?
- **Completeness**: Does response include all key information?

### 1.3 Establish Current Baseline
Run all test cases through both providers (Ollama/OpenAI) and record:
- Retrieval time
- Generation time
- Retrieved document IDs
- Response quality scores (manual 1-5 rating)

**Deliverable:** Baseline spreadsheet with scores for comparison

---

## Phase 2: Diagnose Retrieval Quality

### 2.1 Retrieval Inspection Tool
Build or use existing tooling to inspect:
```
For each test question:
  1. Show the query vector (first 10 dimensions)
  2. Show top 10 retrieved documents with scores
  3. Show BM25 scores separately from vector scores
  4. Highlight which docs are actually relevant
```

### 2.2 Chunking Analysis

**Current Issues to Investigate:**
- Are chunks too large (6000 chars = ~1500 tokens)?
- Is important information split across chunk boundaries?
- Is chunk overlap (500 chars) sufficient?

**Experiments:**
| Experiment | Chunk Size | Overlap | Hypothesis |
|------------|-----------|---------|------------|
| A (current) | 6000 | 500 | Baseline |
| B | 2000 | 400 | Smaller chunks = more precise retrieval |
| C | 4000 | 600 | Medium chunks with more overlap |
| D | Semantic | Variable | Section-based chunking |

### 2.3 Hybrid Search Tuning

**Current Config:** alpha=0.5 (equal BM25 and vector)

**Experiments:**
| Alpha | BM25 Weight | Vector Weight | Best For |
|-------|-------------|---------------|----------|
| 0.3 | 70% | 30% | Keyword-heavy queries |
| 0.5 | 50% | 50% | Current baseline |
| 0.7 | 30% | 70% | Semantic/conceptual queries |
| 0.8 | 20% | 80% | Abstract questions |

**Test:** Run same queries with different alpha values, compare Precision@5

### 2.4 Retrieval Limit Analysis

**Current Limits:** ADR=8, Principles=6, Policies=4, Vocab=4

**Questions:**
- Are we retrieving enough documents?
- Are we retrieving too many (noise)?
- Should limits be query-dependent?

**Experiment:** Compare quality with limits of 3, 5, 10, 15

### 2.5 Content Truncation Impact

**Current:** Retrieved docs truncated to 800 characters

**Issue:** Critical information may be cut off

**Experiment:**
- Increase to 1500 chars and compare
- Remove truncation entirely (monitor context length)

---

## Phase 3: Diagnose Generation Quality

### 3.1 Prompt Engineering Analysis

**Current Ollama Prompt Issues:**
- Is the system prompt too restrictive?
- Is context formatting optimal?
- Are instructions clear for small models?

**Experiments:**
| Prompt Variant | Change | Hypothesis |
|----------------|--------|------------|
| A (current) | Baseline | - |
| B | Add "think step by step" | Better reasoning |
| C | Numbered context items | Easier reference |
| D | Shorter system prompt | Less confusion |
| E | Few-shot examples | Learn response style |

### 3.2 Context Formatting

**Current Format:**
```
CONTEXT (use ONLY this information to answer):
[Document 1 content]
[Document 2 content]
...
```

**Alternative Formats to Test:**
```
# Format B: Structured with metadata
## Source 1: ADR-042 (Status: Accepted)
[content]

## Source 2: Principle - API Design
[content]
```

```
# Format C: Relevance-ordered with scores
[HIGHLY RELEVANT] ADR-042: ...
[RELEVANT] Principle-15: ...
[SOMEWHAT RELEVANT] Policy-3: ...
```

### 3.3 Model Comparison

| Model | Context | Speed | Quality (expected) |
|-------|---------|-------|-------------------|
| SmolLM3 | 8K | Fast | Lower |
| Qwen3:4b | 32K | Medium | Medium |
| Qwen3:8b | 32K | Slower | Higher |
| Mistral 7B | 32K | Slower | Higher |

**Recommendation:** Test Qwen3:4b vs Qwen3:8b if hardware permits

### 3.4 Hallucination Detection

Create test cases where:
1. Answer IS in context → Should answer correctly
2. Answer is NOT in context → Should say "I don't know"
3. Answer is PARTIALLY in context → Should answer partial + admit gaps

---

## Phase 4: Optimize & Iterate

### 4.1 A/B Testing Framework

For each change, run full test suite and compare:
```
Baseline Score: X
With Change A: Y
Improvement: (Y-X)/X * 100%
```

### 4.2 Recommended Optimization Order

Based on typical RAG issues, prioritize:

1. **High Impact, Low Effort:**
   - [ ] Increase content truncation (800 → 1500 chars)
   - [ ] Tune alpha per query type
   - [ ] Improve prompt formatting

2. **High Impact, Medium Effort:**
   - [ ] Re-chunk with smaller chunk size (2000-3000 chars)
   - [ ] Add reranking step (if available)
   - [ ] Structured context formatting

3. **Medium Impact, High Effort:**
   - [ ] Semantic chunking by document structure
   - [ ] Query expansion/rewriting
   - [ ] Upgrade to larger local model (8B)

### 4.3 Configuration Recommendations

Based on current analysis, recommended first changes:

```python
# config.py changes to try:

# Chunking (requires re-ingestion)
MAX_CHUNK_SIZE = 3000  # Reduced from 6000
CHUNK_OVERLAP = 400    # Adjusted

# Retrieval
DEFAULT_ALPHA = 0.6    # Slightly favor vector search
CONTENT_MAX_CHARS = 1500  # Increased from 800

# Limits (increase for better recall)
ADR_LIMIT = 10         # Increased from 8
PRINCIPLE_LIMIT = 8    # Increased from 6
```

---

## Quick Diagnostic Checklist

Before deep investigation, check these common issues:

- [ ] **Empty/bad embeddings?** Check for zero vectors in Weaviate
- [ ] **Wrong collection queried?** Verify query routing logic
- [ ] **doc_type filter too restrictive?** Check if "content" filter excludes relevant docs
- [ ] **Index documents retrieved?** Ensure index.md files are properly filtered
- [ ] **Think tags in output?** Verify strip_think_tags() is working
- [ ] **Timeout issues?** Check if responses are being cut off
- [ ] **Context overflow?** Monitor if context exceeds model limits

---

## Implementation Priority

| Priority | Task | Estimated Impact |
|----------|------|-----------------|
| P0 | Create test suite with 20 questions | Foundation |
| P0 | Run baseline metrics | Foundation |
| P1 | Increase content truncation to 1500 | High |
| P1 | Test alpha=0.7 for semantic queries | Medium-High |
| P2 | Re-chunk at 3000 chars | High (requires re-ingestion) |
| P2 | Structured context formatting | Medium |
| P3 | Test larger model (Qwen3:8b) | Medium (needs resources) |

---

## Next Steps

1. **Immediate:** User provides 5-10 example questions where quality is poor
2. **Day 1:** Run retrieval inspection on failed questions
3. **Day 2:** Implement quick wins (truncation, alpha tuning)
4. **Day 3:** A/B test with baseline
5. **Week 1:** Re-chunking experiment if needed
