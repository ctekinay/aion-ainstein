# RAG Accuracy Review: AION-AInstein vs. Blog Post Principles

**Date:** 2026-02-15
**Scope:** Review of AION-AInstein implementation against the "4 approaches to cut RAG hallucinations" framework.

---

## 1. Force Clarification Before Searching

**Blog claim:** Agent stops and asks "which variant?" for ambiguous queries.

**AInstein implementation:** Significantly more sophisticated.

Full intent classification pipeline (`src/intent_router.py`) with dual-mode classification
(heuristic regex + LLM-based), a configurable confidence threshold (`DEFAULT_CONFIDENCE_THRESHOLD = 0.55`),
and a `needs_clarification()` gate. Clarification responses are generated contextually via LLM
with fallback to a static menu.

Key routing code (`src/elysia_agents.py:2148-2154`):
```python
if needs_clarification(intent_decision, threshold=confidence_threshold):
    clarification = await build_clarification_response(intent_decision, question)
    return response, []
```

**Strengths:**
- Graded confidence (0.0-1.0) vs. binary ambiguity check
- Configurable thresholds per deployment
- Contextual clarification generation with LLM fallback
- `OutputShape.CLARIFICATION` as first-class response type

**Gap:** Clarification triggers on *intent ambiguity* only. Entity-level disambiguation
(e.g., "Which ADR about data?" when multiple exist) is not implemented.

---

## 2. Query Decomposition

**Blog claim:** Break requests into sub-queries, run in parallel, combine dense+sparse results.

**AInstein implementation:** Partial.

- **Hybrid search (dense+sparse):** Implemented via `collection.query.hybrid()` with configurable alpha
  (`alpha_vocabulary: 0.6`, `alpha_semantic: 0.7`). Solid.
- **Parallel multi-agent execution:** Orchestrator (`src/agents/orchestrator.py`) queries multiple
  specialized agents concurrently via `asyncio.gather()`.

**Gap:** No explicit query decomposition step. Complex queries are not structurally broken into
sub-queries before search. Decomposition is implicit — the LLM in the Elysia decision tree
may call multiple tools, but there's no deterministic decomposition layer.

---

## 3. Filtering (Most Effective)

**Blog claim:** Apply metadata filters before retrieval. Use `target_directory` path strings.

**AInstein implementation:** Significantly ahead.

- **Config-driven doc_type taxonomy** (`config/taxonomy.default.yaml`) with canonical types,
  aliases, and per-route allow-lists
- **Positive (allow-list) filtering** (`src/skills/filters.py`) using
  `Filter.by_property("doc_type").contains_any(allowed_types)` — handles null/missing values correctly
- **Dynamic filter construction** based on query content (approval keywords → include DAR types)
- **Intent-aware collection routing** — orchestrator scores queries per agent, intent router
  determines entity scope (ADR, PCP, Policy, Vocab, Multi)
- **Fallback guardrails** — controlled in-memory filtering with safety caps
  (`max_fallback_scan_docs: 10000`) and observability metrics

**Strengths vs. blog approach:**
- Structured metadata filters vs. raw filesystem paths
- Canonical taxonomy with aliases vs. hardcoded directory strings
- Collection-level scoping with four distinct collections
- Fallback metrics and guardrails for migration scenarios

**Minor gap:** Semantic search tools (`search_architecture_decisions`, `search_principles`)
don't apply `doc_type` filters — only list tools use `build_document_filter()`.

---

## 4. Context Pruning

**Blog claim:** Prune old search results from long conversations. Drop heavy intermediate data.

**AInstein implementation:** Different architecture makes this largely N/A.

- **TTL-based semantic cache** (`_RESPONSE_CACHE`, 5min TTL, 100 entries)
- **Content truncation at tool level** (`content_max_chars: 800`, `elysia_content_chars: 500`)
- **Deterministic bypasses** for list/count/comparison queries (no LLM involved)
- **Per-request Tree instances** — no conversation-level context accumulation

**Gap:** No explicit conversation history pruning. Each query is stateless.
`followup_binding_enabled: true` suggests multi-turn intent is planned — that layer
will need a pruning strategy.

---

## Additional Anti-Hallucination Measures (Not in Blog Post)

AInstein implements several approaches the blog post doesn't cover:

1. **Abstention/grounding gate** — refuses to answer when retrieval quality is poor
   (`should_abstain()`, grounding gate with configurable `abstain_gate_enabled`)
2. **SKOSMOS terminology verification** — validates technical terms against vocabulary index
   before answering terminology queries
3. **Structured response contract** — deterministic JSON validation with schema versioning,
   retry logic, and controlled failure responses
4. **Identity enforcement** — scrubs internal component names from user-facing output
5. **Observability** — metrics on fallback usage, abstention triggers, parse success rates
6. **Deterministic paths** — list/count/comparison queries bypass the LLM entirely,
   eliminating hallucination risk for those query types

---

## Summary

| Principle | Blog Post | AInstein | Verdict |
|---|---|---|---|
| 1. Clarification | Simple binary gate | Graded confidence + LLM clarification | Ahead (gap: entity disambiguation) |
| 2. Query Decomposition | Explicit decomposition | Implicit via multi-agent + Elysia tree | Gap (no structural decomposition) |
| 3. Filtering | `target_directory` string | Typed metadata taxonomy + allow-lists | Significantly ahead |
| 4. Context Pruning | Drop old retrieval data | TTL cache + truncation + stateless queries | Different architecture |

**Bottom line:** The blog post's advice is solid for a first pass. AInstein's implementation is
a couple of engineering generations ahead in filtering and clarification, roughly aligned on
hybrid search, and has a genuine gap in explicit query decomposition. The abstention gate,
SKOSMOS verification, and deterministic paths are significant additions not covered by the blog.
