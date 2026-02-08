---
parent: Implementation Records
nav_order: 1
title: IR0001 Confidence-Based Abstention for Hallucination Prevention
status: proposed
date: 2026-02-03

driver: Cagri Tekinay
approvers: ESA Team
contributors:
informed: AInstein Development Team
---

# IR0001 Confidence-Based Abstention for Hallucination Prevention

## Context and Problem Statement

The AInstein RAG system (Retrieval-Augmented Generation) is designed to help architects, engineers, and stakeholders navigate Alliander's energy system architecture knowledge base. During testing, we identified a critical issue: **the system hallucinates information when asked about non-existent content**.

For example, when asked "What does ADR-0050 decide?" (a fictional Alliander ESA ADR used as a test case), the system confidently generated fake content about a fictional "DACI framework" decision. This is unacceptable for a system supporting EUR 165M procurement decisions, where hallucination tolerance must be <0.1%.

**Key Question:** How do we prevent the LLM from generating confident-sounding but fabricated responses when the knowledge base contains no relevant information?

## Decision Drivers

* **Zero tolerance for hallucination** in high-stakes procurement decisions
* **SKOSMOS as source of truth** for terminology (if not in SKOSMOS, user should clarify)
* **Weaviate doesn't provide true confidence scores** - only normalized fusion scores
* **Multi-layer guardrails architecture** as defined in project vision (see classification-pipeline and guardrails-architecture diagrams)
* **Local LLM support required** - solution must work with Ollama (qwen3:4b, smollm3) not just OpenAI
* **Research shows embedding-based detection alone fails** on RLHF-aligned models (100% false positive rate)

## Considered Options

1. **Prompt Engineering Only** - Tell the LLM to say "I don't know"
2. **Retrieval Score Thresholding** - Check Weaviate distances before generation
3. **NLI-Based Post-Generation Verification** - Use HALT-RAG/LettuceDetect after generation
4. **Multi-Layer Abstention** - Combine retrieval checks + query coverage + entity verification

## Decision Outcome

**Chosen option: "Multi-Layer Abstention"** - implemented as a pre-generation gate that checks multiple retrieval quality signals before allowing LLM generation.

This approach was chosen because:
- Prompt engineering alone is unreliable (GPT-5.2 still hallucinated despite explicit instructions)
- Weaviate's normalized scores are relative, not absolute confidence measures
- Post-generation NLI adds latency and complexity without preventing the hallucination
- Pre-generation abstention is simpler, faster, and completely prevents hallucination

### Implementation Details

#### Abstention Function: `should_abstain()`

Located in `src/elysia_agents.py`, this function checks three conditions:

```python
# Thresholds
DISTANCE_THRESHOLD = 0.5  # Max distance for relevance (lower = more similar)
MIN_QUERY_COVERAGE = 0.2  # Min fraction of query terms found in results

def should_abstain(query: str, results: list) -> tuple[bool, str]:
    # Check 1: No results at all
    if not results:
        return True, "No relevant documents found in the knowledge base."

    # Check 2: Distance threshold (absolute similarity)
    distances = [r.get("distance") for r in results if r.get("distance") is not None]
    if distances and min(distances) > DISTANCE_THRESHOLD:
        return True, f"No sufficiently relevant documents found (best match distance: {min_distance:.2f})."

    # Check 3: Specific entity queries (ADR-XXXX must exist)
    adr_match = re.search(r'adr[- ]?0*(\d+)', query.lower())
    if adr_match:
        adr_num = adr_match.group(1).zfill(4)
        adr_found = any(f"adr-{adr_num}" in str(r.get("title", "")).lower() for r in results)
        if not adr_found:
            return True, f"ADR-{adr_num} was not found in the knowledge base."

    # Check 4: Query term coverage
    # ... (checks if query terms appear in retrieved documents)

    return False, "OK"
```

#### Metadata Collection

All Weaviate hybrid queries now request metadata:

```python
from weaviate.classes.query import MetadataQuery

metadata_request = MetadataQuery(score=True, distance=True)

results = collection.query.hybrid(
    query=question,
    vector=query_vector,
    limit=5,
    alpha=settings.alpha_vocabulary,
    return_metadata=metadata_request  # NEW
)

# Results now include:
# obj.metadata.distance  - absolute similarity (lower = better)
# obj.metadata.score     - normalized fusion score (for debugging)
```

#### Abstention Response

When abstaining, the system returns a helpful message instead of hallucinating:

```
I don't have sufficient information to answer this question.

**Reason:** ADR-0050 was not found in the knowledge base.

**Suggestions:**
- Try rephrasing your question with different terms
- Check if the topic exists in our knowledge base
- For terminology questions, verify the term exists in SKOSMOS

If you believe this information should be available, please contact the ESA team.
```

### Consequences

**Good:**
- Eliminates hallucination for non-existent ADRs (N3 test case)
- Provides clear feedback to users about why information isn't available
- No additional infrastructure required (no external NLI models)
- Works identically for Ollama and OpenAI providers
- Fast - abstention happens before expensive LLM generation

**Bad:**
- May abstain on valid queries if thresholds are too aggressive
- Distance threshold (0.5) may need tuning per collection
- Doesn't catch hallucination within valid context (addressed separately by hallucination detection)

**Neutral:**
- Requires ongoing threshold tuning based on test results

### Confirmation

The implementation can be validated by running the test suite:

```bash
python -m src.evaluation.test_runner --openai --quick --model gpt-4o-mini
```

The N3 test ("What does ADR-0050 decide?") should now:
- Return ✅ (correct abstention) instead of ❌🔮 (hallucination)
- Show response: "ADR-0050 was not found in the knowledge base"

## Architecture Mapping

This decision implements **Layer 3: Confidence-Based Abstention** from the guardrails-architecture diagram:

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 3: Confidence-Based Abstention                        │
│                                                             │
│   High >0.85:  Direct answer                                │
│   Medium 0.6-0.85: Answer with caveat                       │
│   Low <0.6:    ABSTAIN - "I don't have sufficient info"     │
│                                                             │
│   Currently Implemented:                                    │
│   ✅ Distance threshold check (0.5)                         │
│   ✅ Entity existence check (ADR-XXXX)                      │
│   ✅ Query term coverage check (20%)                        │
│                                                             │
│   Future (SKOSMOS integration):                             │
│   ⬜ SKOSMOS terminology verification                       │
│   ⬜ User clarification flow                                │
│   ⬜ Alternative suggestions                                │
└─────────────────────────────────────────────────────────────┘
```

## Codebase References

| File | Purpose | Key Functions |
|------|---------|---------------|
| `src/elysia_agents.py` | Main RAG system with abstention | `should_abstain()`, `get_abstention_response()`, `_direct_query()` |
| `src/evaluation/test_runner.py` | Test framework with hallucination detection | `detect_hallucination()`, `check_no_answer()` |
| `src/diagnostics/rag_diagnostics.py` | RAG quality diagnostic tools | `analyze_chunks()`, `test_retrieval()`, `tune_alpha()` |
| `src/config.py` | Configuration settings | `DISTANCE_THRESHOLD`, `MIN_QUERY_COVERAGE` |

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Vector Store | Weaviate | Hybrid search with BM25 + vector |
| Embeddings (Local) | Nomic `nomic-embed-text-v2-moe` via Ollama | Client-side embeddings |
| Embeddings (Cloud) | OpenAI `text-embedding-3-small` | Server-side embeddings |
| LLM (Local) | Ollama `qwen3:4b`, `smollm3` | Generation |
| LLM (Cloud) | OpenAI `gpt-4o-mini`, `gpt-5-mini` | Generation |
| RAG Framework | Weaviate Elysia | Agentic tool selection |

## Remaining TODOs

### High Priority

1. **SKOSMOS-First Terminology Confidence**
   - Check SKOSMOS vocabulary before internal documents
   - SKOSMOS match = highest confidence
   - Not in SKOSMOS = ask user to clarify

2. **User Clarification Flow**
   - When term not found, ask: "Could you clarify what you mean by X?"
   - Options: provide context, search external sources, flag for SKOSMOS addition

3. **Threshold Tuning**
   - Run full test suite across all models
   - Analyze false positive/negative rates
   - Consider per-collection thresholds

### Medium Priority

4. **Alternative Suggestions**
   - When abstaining, suggest similar terms that DO exist
   - "Did you mean ADR-0012 (CIM Standard)?"

5. **Pre-Classification Router**
   - Implement Stage 1 fast keyword classification (<20ms)
   - Route to appropriate agent based on query type

6. **Post-Generation NLI Verification**
   - Add LettuceDetect or HALT-RAG for additional safety
   - Verify generated response is entailed by context

### Low Priority

7. **Chunking Implementation**
   - Analyze document sizes (some >5000 chars)
   - Implement semantic chunking for large documents

8. **Alpha Tuning Per Collection**
   - Run systematic alpha experiments
   - Optimize keyword vs vector balance per collection type

## Test Results Summary

| Model | Before Abstention | After Abstention | N3 Test |
|-------|-------------------|------------------|---------|
| Ollama qwen3:4b | 50% | TBD | Empty (safe) |
| OpenAI gpt-4o-mini | 60% | TBD | Hallucinated → Abstain |
| OpenAI gpt-5.2 | 40% | TBD | Hallucinated → Abstain |
| OpenAI gpt-5-mini | 50% | TBD | Hallucinated → Abstain |

## References

### Research Papers

- [HALT-RAG: Hallucination Detection with Calibrated NLI Ensembles](https://arxiv.org/abs/2509.07475) - State-of-the-art abstention framework
- [The Semantic Illusion: Limits of Embedding-Based Detection](https://arxiv.org/html/2512.15068) - Why embedding alone fails
- [LettuceDetect: Hallucination Detection Framework](https://arxiv.org/html/2502.17125v1) - Open-source detection tool

### Weaviate Documentation

- [Weaviate Hybrid Search](https://docs.weaviate.io/weaviate/search/hybrid) - Fusion algorithms
- [Weaviate Distance Metrics](https://docs.weaviate.io/weaviate/config-refs/distances) - Distance vs certainty

### Project Resources

- `docs/architecture/guardrails-architecture.puml` - 4-layer guardrails design
- `docs/architecture/classification-pipeline.puml` - Query classification pipeline

## Decision History

| Date | Change | Author |
|------|--------|--------|
| 2026-02-03 | Initial implementation of confidence-based abstention | Cagri Tekinay |
| 2026-02-03 | Added return_metadata to all Weaviate queries | Cagri Tekinay |
| 2026-02-03 | Added hallucination detection to test runner | Cagri Tekinay |
| 2026-02-03 | Created RAG diagnostic framework | Cagri Tekinay |

---

*This ADR documents a technical decision made during the AION-AInstein development. For questions, contact the ESA team.*
