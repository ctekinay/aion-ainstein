# Intent Router Replacement Plan: Developer Impact Assessment & Analysis

**Date:** 2025-02-17
**Reviewer:** Claude (automated code review)
**Scope:** EmbeddingClassifier replacing ArchitectureAgent scoring gate only (not `intent_router.py`)

---

## Executive Summary

The plan is **well-designed and implementable** within the described scope. The core diagnosis is correct: the signal-based router (`_extract_signals` → `_score_intents` → `_select_winner`) cannot generalize beyond its keyword lists, and each patch creates a false sense of progress. The embedding-based replacement is the right architectural move.

This analysis identifies **8 discrepancies** between the plan's assumptions and the actual codebase, **3 risks** that need mitigation before implementation begins, and provides the complete file impact assessment requested in the Developer Impact Assessment Checklist.

---

## Part 1: Plan Accuracy vs. Actual Codebase

### 1.1 Correct Assumptions

The plan accurately describes:

- The scoring gate architecture at `src/agents/architecture_agent.py:150-277` — signals, weights, thresholds, margin
- The `_WEIGHTS` dict structure (lines 183-200) and `_INTENT_THRESHOLDS` (lines 203-208)
- The `_normalize_doc_ids()` function (lines 298-320) returning `list[dict]` with `canonical_id`, `number_value`, `prefix`
- The follow-up binding logic at lines 581-592 using `_FOLLOWUP_MARKER_RE`
- The fallback behavior: doc ref + no retrieval verb → conversational (line 640)
- The `embed_text()` / `embed_texts()` API in `src/weaviate/embeddings.py` with 768-dim nomic-embed-text-v2-moe
- The existence of `routing_policy.yaml` as the feature flag surface

### 1.2 Discrepancies Found

#### D1: `_conversation_doc_refs` is NOT inside `ArchitectureAgent`

**Plan says:** Replace `_conversation_doc_refs` (described as part of the agent) with `SessionState.last_doc_refs`.

**Actual:** `_conversation_doc_refs` is a module-level dict in `src/chat_ui.py:903`, not in the agent. The agent receives `last_doc_refs` as a parameter to `query()` (line 497). The chat_ui layer manages the state:

```python
# chat_ui.py:903
_conversation_doc_refs: dict[str, list[dict]] = {}

# chat_ui.py:932 — passed into ArchitectureAgent.query()
last_doc_refs = _conversation_doc_refs.get(conversation_id)

# chat_ui.py:954 — cached after query completes
_conversation_doc_refs[conversation_id] = refs
```

**Impact:** The `SessionContext` class can still work, but it needs to either:
(a) Live in `chat_ui.py` and pass resolved refs to `query()` (same pattern as now), or
(b) Be instantiated per-conversation and stored in the agent, requiring `ArchitectureAgent` to become stateful.

**Recommendation:** Option (a). Keep `SessionContext` as a standalone module, but wire it in `chat_ui.py` where the conversation state already lives, passing resolved `last_doc_refs` to `query()` as today. This minimizes the integration surface.

---

#### D2: `chat_ui.py` Has Its Own Independent Follow-up System

**Plan says:** "chat_ui.py passthrough logic — Kept but simplified — session handles resolution."

**Actual:** `chat_ui.py` has a **complete independent follow-up subsystem** (lines 89-226) with:
- `_FOLLOWUP_RE` — verb + pronoun patterns ("list them", "show those")
- `_APPROVAL_FOLLOWUP_RE` — "who approved them?"
- `_CONTINUATION_FOLLOWUP_RE` — "what about those?"
- `_conversation_subjects` dict — per-conversation subject tracking
- `resolve_followup()` function — full resolution logic with 3 rewrite strategies
- A priority rule: if `_conversation_doc_refs` has cached refs for this conversation, **skip all rewrites** and let ArchitectureAgent handle it via `last_doc_refs` injection (line 177)

This is a **two-tier follow-up system**, not a single one:
1. **Tier 1 (chat_ui.py):** Subject-based rewriting ("list them" → "list dars") — fires only when no doc_refs are cached
2. **Tier 2 (ArchitectureAgent):** Pronoun-based ref injection ("show it" → inject last ADR.12) — fires only when `_FOLLOWUP_MARKER_RE` matches and `last_doc_refs` are provided

The plan's `SessionContext` needs to account for both tiers. If it only replaces Tier 2 inside the agent, Tier 1 in `chat_ui.py` still exists and may conflict.

**Recommendation:** In the integration section, explicitly document that `chat_ui.py`'s `resolve_followup()` is **left unchanged for v1**. SessionContext replaces only the agent-side follow-up binding (Tier 2). Consolidation of both tiers into `SessionContext` is a post-v1 task.

---

#### D3: `query()` Returns Before the Session Update Could Execute

**Plan's target flow says:**

```python
# Step 6: Update session (NEW)
self.session.update(question, winner, doc_refs)
```

**Actual:** The `query()` method (lines 491-670) has **early returns** on every route:
- Line 618: `return await self._handle_listing_query(...)`
- Line 624: `return await self._handle_count_query(...)`
- Line 632: `return response`
- Line 644: `return self._conversational_response(...)`
- Line 670: `return response`

The session update at the end of `query()` would never execute because every path returns before reaching it.

**Fix:** Either:
(a) Move `self.session.update()` before each `return` statement (error-prone, 5+ locations), or
(b) Use a `try/finally` pattern, or
(c) Handle the update outside `query()` in the caller (`chat_ui.py`), which already does this for `_conversation_doc_refs` at line 954.

**Recommendation:** Option (c). Keep session updates in `chat_ui.py` as it already does. This is consistent with discrepancy D1.

---

#### D4: `doc_refs` Format Mismatch

**Plan's interface says:**

```python
class SessionState:
    last_doc_refs: list[str]     # e.g. ["ADR.12", "PCP.12"]
```

**Actual format in the codebase:**

```python
# _normalize_doc_ids() returns:
[{"canonical_id": "ADR.12", "number_value": "0012", "prefix": "ADR"}]

# chat_ui.py caches same dict format at line 946-953
# ArchitectureAgent.query() receives same dicts as last_doc_refs
```

The entire pipeline — extraction, caching, injection, lookup — uses `list[dict]`, not `list[str]`. The `SessionContext.resolve_refs()` method needs to accept and return `list[dict]`, or you'll need adaptation layers at every boundary.

**Recommendation:** Change `SessionState.last_doc_refs` to `list[dict]` to match the existing interface. The `_has_anaphora()` logic doesn't depend on the ref format, so this is a type-signature change only.

---

#### D5: Bare-Number Resolution Is Missing from the Target Flow

**Plan's target flow:**

```python
# Step 1b: Bare-number resolution (KEPT)
doc_refs = _resolve_bare_numbers(question, doc_refs)
```

**Actual bare-number resolution (lines 527-579):** This is 50+ lines of branching logic that:
1. Calls `_extract_bare_numbers(question)` for pure bare-number queries
2. Calls `_extract_bare_numbers(question, prefixed_refs=signals.doc_refs)` for mixed queries like "Compare 22 and ADR.12"
3. Calls `self._resolve_bare_number_ref(bare_numbers[0])` which queries Weaviate
4. Has 3 possible outcomes: `resolved` (patch refs), `needs_clarification` (return early), `none` (continue)
5. For mixed-ref cases, includes already-known prefixed refs in the clarification candidates

The plan refers to this as `_resolve_bare_numbers(question, doc_refs)` — a function that doesn't exist. The actual implementation is interleaved with `signals` mutation and requires access to `self` (for Weaviate queries).

**Recommendation:** In the target flow, keep the bare-number resolution block essentially as-is. It operates on `doc_refs` (the entity list), not on intent signals, so it's compatible with the new architecture. Just feed its output into the classifier rather than into `_score_intents()`.

---

#### D6: The Plan Lists `_has_retrieval_intent` for Removal But Tests Import It Directly

**Plan says:** Remove `_RETRIEVAL_VERB_RE` (and by extension `_has_retrieval_intent()`).

**Actual:** `tests/test_architecture_agent.py` imports and directly tests `_has_retrieval_intent` at line 38:

```python
from src.agents.architecture_agent import (
    _extract_signals,
    _has_retrieval_intent,
    _score_intents,
    _select_winner,
)
```

And 5 test cases in `TestRetrievalVerbGate` (lines 243-274) directly test this function.

Similarly, `tests/test_gold_routing_suite.py` imports `_extract_signals`, `_score_intents`, `_select_winner` at lines 28-31, and uses them in at least 10 assertion blocks.

**Impact:** These tests will break on import, not just on assertion. You'll need to either:
- Rewrite them to test the classifier instead, or
- Keep the old functions as dead code during the parallel-run phase (contradicts the clean-cut goal)

**Recommendation:** During Week 1 (parallel run), keep the old functions available but deprecated. In Week 3 (cleanup), delete them and rewrite the tests. This is the pragmatic path — import errors are harder to manage than assertion failures.

---

#### D7: The `_detect_semantic_scope()` Function Already Exists

**Plan proposes:** A new `_determine_scope()` function.

**Actual:** `_detect_semantic_scope()` at line 113 already does roughly the same thing:

```python
def _detect_semantic_scope(question: str) -> str:
    has_principle = bool(_PRINCIPLE_SCOPE_RE.search(question))
    has_adr = bool(_ADR_SCOPE_RE.search(question))
    if has_principle and not has_adr:
        return "principle"
    if has_adr and not has_principle:
        return "adr"
    return "both"
```

And it even has a TODO comment (line 118-121):
```
TODO(post-demo): Replace this regex-based detector with a learned scope
classifier that combines intent + scope in a single pass.
```

**Recommendation:** Extend `_detect_semantic_scope()` rather than creating a new function. Add the doc-ref-based scope derivation as a higher-priority check (doc refs are structural, not semantic, so they should take precedence), then fall through to the existing regex for queries without refs.

---

#### D8: The `conversational` Intent Handling Differs from Plan

**Plan says:** `conversational` is the fallback when no intent passes threshold.

**Actual (line 640-644):**

```python
# Fallback: doc refs present but no retrieval verb → conversational
if signals.has_doc_ref and not signals.has_retrieval_verb:
    trace.intent = trace.intent or "conversational"
    trace.path = "conversational"
    self._emit_trace(trace)
    return self._conversational_response(question, signals.doc_refs)
```

The conversational path in the actual code is **conditional on doc refs being present AND no retrieval verb**. It's not a generic fallback — it's specifically the "cheeky query" gate. If no doc refs are present and no intent wins, the query falls through to semantic search (line 646-670), which is a different path than conversational.

The plan's target flow should reflect this: when the classifier returns low confidence and there are no doc refs, the correct fallback is semantic search, not conversational.

---

## Part 2: Component Analysis

### 2.1 Component 1: EmbeddingClassifier — Sound Design, Two Concerns

The centroid-based classifier design is appropriate for this use case:
- ~80 prototypes × 768 dimensions is trivial to compute
- Cosine similarity to centroids is deterministic and fast
- The threshold + margin gate mirrors the existing architecture (familiar to the team)
- The `explain()` method is valuable for debugging

**Concern 1: Prototype Imbalance.** The initial seed has uneven prototype counts:
- `conversational`: 11 examples
- `compare`: 11 examples
- `lookup_doc`: 12 examples
- `semantic_answer`: 13 examples
- `list`: 8 examples
- `count`: 6 examples
- `followup`: 12 examples

The `count` intent has only 6 prototypes vs. 13 for `semantic_answer`. With centroid-based classification, fewer prototypes mean less stable centroids. A query like "How many principles exist?" might drift toward `list` (8 prototypes including "What ADRs exist?") because the centroid hasn't been anchored by enough examples.

**Recommendation:** Pad `count` and `list` to at least 10 prototypes each. Examples to add:
- count: "Total number of principles", "How many policies are there?", "Count the decisions", "How many DARs exist?"
- list: "Show me every principle", "What decisions exist?"

**Concern 2: `followup` as an Embedding Intent.** Pronouns like "it", "that", "those" are function words with weak semantic content. In embedding space, "Show it" and "Show ADR.12" are very close because the embedding captures the imperative+show pattern, not the pronoun specificity. The classifier may struggle to distinguish `followup` from `lookup_doc`.

**Recommendation:** During parallel-run, specifically monitor `followup` vs. `lookup_doc` confusion. If it's problematic, consider keeping `followup` as a rule-based detection (the `_has_anaphora()` method in `SessionContext`) rather than an embedding-based intent. The classifier would then handle 6 intents, and followup detection would be a pre-classifier check. This is the pattern the plan already describes for entity extraction — some things are better rule-based.

### 2.2 Component 2: Prototype Bank — Good Maintenance Surface

The YAML-based prototype bank is the plan's strongest design choice. It converts the failure mode from "regex doesn't match → code change required" to "classifier misses → add 2 examples to YAML." This directly addresses the root cause.

**One addition:** Include a `_version` or `_last_updated` field at the top of the YAML for auditability:
```yaml
_meta:
  version: "1.0"
  last_updated: "2025-02-17"
  total_prototypes: 83
```

### 2.3 Component 3: SessionContext — Correct Direction, Wrong Location

As noted in discrepancies D1 and D3, the `SessionContext` design is correct in isolation but misplaced in the integration plan. The conversation state management **already happens in `chat_ui.py`**, and the plan's integration snippet assumes it happens inside `ArchitectureAgent.query()`.

The `_has_anaphora()` method is more comprehensive than the current `_FOLLOWUP_MARKER_RE`:
- Current regex requires `verb + pronoun` (e.g., "show it", "explain that")
- `_has_anaphora()` detects standalone pronouns ("it", "them", "those") which covers more cases

This is an improvement, but the broader detection surface means more false positives. A query like "Is it true that ADR.12 requires CIM?" contains "it" but isn't a follow-up. The word-boundary matching (`f" {m} " in f" {q} "`) helps, but "Is it true" would still match on "it".

**Recommendation:** Add a few negative examples to the anaphora detection, or use a short exclusion list for known false-positive patterns ("is it", "it is", "it's", "isn't it"). Keep the detection intentionally broad (as the plan suggests), but log when anaphora detection fires so you can monitor false positive rates.

### 2.4 Component 4: Scope Selection — Mostly Redundant

The proposed `_determine_scope()` is nearly identical to the existing `_detect_semantic_scope()` at `architecture_agent.py:113-129`, plus doc-ref prefix checking. The keyword fallback (`"principle" in q`) is the same logic as `_PRINCIPLE_SCOPE_RE.search(question)`.

**Recommendation:** Don't create a new function. Add doc-ref prefix checking to the top of `_detect_semantic_scope()`:

```python
def _detect_semantic_scope(question: str, doc_refs: list[dict] = None) -> str:
    # Priority 1: explicit doc refs
    if doc_refs:
        has_adr = any(r["prefix"] == "ADR" for r in doc_refs)
        has_pcp = any(r["prefix"] == "PCP" for r in doc_refs)
        if has_adr and has_pcp:
            return "both"
        if has_pcp:
            return "principle"
        if has_adr:
            return "adr"
    # Priority 2: existing regex detection (unchanged)
    has_principle = bool(_PRINCIPLE_SCOPE_RE.search(question))
    has_adr_kw = bool(_ADR_SCOPE_RE.search(question))
    ...
```

---

## Part 3: Developer Impact Assessment Checklist

### 1. Files Modified

| File | Change | Nature |
|------|--------|--------|
| `src/classifiers/embedding_classifier.py` | **NEW** | EmbeddingClassifier class + factory |
| `src/agents/session_context.py` | **NEW** | SessionContext + SessionState |
| `config/intent_prototypes.yaml` | **NEW** | Prototype bank |
| `config/routing_policy.yaml` | **MODIFIED** | Add `embedding_classifier_enabled: false` |
| `src/agents/architecture_agent.py` | **MODIFIED** | Replace scoring gate with classifier calls in `query()`, add compare handler, extend `_detect_semantic_scope()`, update `RouteTrace` dataclass |
| `src/chat_ui.py` | **MODIFIED** | Wire `SessionContext` into `stream_architecture_response()`, update `_conversation_doc_refs` management |
| `tests/test_embedding_classifier.py` | **NEW** | Classifier unit tests |
| `tests/test_session_context.py` | **NEW** | SessionContext unit tests |
| `tests/test_gold_routing_suite.py` | **MODIFIED** | Remove direct `_extract_signals`/`_score_intents`/`_select_winner` imports; adapt signal assertions to classifier output assertions |
| `tests/test_architecture_agent.py` | **MODIFIED** | Heavy rewrite: ~40 test methods that call `_extract_signals()`, `_score_intents()`, `_select_winner()`, or `_has_retrieval_intent()` directly |
| `tests/test_followup_binding.py` | **MODIFIED** | Adapt to SessionContext interface |
| `scripts/manual_demo_pack.py` | **MODIFIED** | Update trace assertions (signals dict → classifier scores) |

**Files NOT modified (confirmed):**
- `src/intent_router.py` — out of scope (Elysia path)
- `src/elysia_agents.py` — out of scope (uses `intent_router.py`, not ArchitectureAgent scoring gate)
- `src/meta_route.py` — unchanged (META intent handled upstream by Elysia's intent_router)
- `src/weaviate/embeddings.py` — used as-is (provides `embed_text`/`embed_texts`)
- `src/agents/base.py` — unchanged
- `src/config.py` — may need a settings field for the new flag, but minimal

### 2. Test Adaptation

**Must rewrite (import breakage):**
- `test_gold_routing_suite.py`: 3 imports (`_extract_signals`, `_score_intents`, `_select_winner`) + ~10 direct invocations
- `test_architecture_agent.py`: 4 imports (`_extract_signals`, `_has_retrieval_intent`, `_score_intents`, `_select_winner`) + ~40 direct invocations

**Must rewrite (assertion change):**
- Tests asserting `trace.get("signals", {}).get("has_doc_ref")` — replace with `trace.get("classifier", {}).get("intent")`
- Tests asserting `trace.get("scores")` — replace with classifier confidence/scores
- `TestRetrievalVerbGate` (5 tests) — delete entirely; functionality absorbed by classifier
- `TestListScoringGate`, `TestCountScoringGate`, `TestDocRefScoringGate` — rewrite to test classifier output
- `TestGenericSemanticSignal` — rewrite or delete

**Can stay as-is:**
- `TestIDNormalization` — tests `_normalize_doc_ids()`, which is kept
- `TestDecisionChunkSelection` — tests chunk selection logic, downstream of routing
- `TestQuoteFormatting` — tests quote extraction, independent of routing
- `TestBareNumberExtraction` — tests `_extract_bare_numbers()`, which is kept
- `TestBareNumberResolver` — tests `_resolve_bare_number_ref()`, which is kept
- `TestADR0012EndToEndSmoke` — tests full pipeline, should work if routing produces same result
- `TestPostFilterSemanticResults` — tests post-filter, independent of routing
- `TestSemanticFilterEffectiveness` — tests `build_adr_filter()`, independent of routing

**Estimated split:** ~40 tests need rewriting, ~60+ tests stay as-is, ~10 new tests to write.

### 3. Embedding Init Latency

~80 prototypes embedded via Ollama `embed_texts()` (batch mode):
- Batch API call: Ollama processes the batch in a single forward pass for nomic-embed-text-v2-moe
- Expected: **< 2 seconds** on local Ollama with GPU, **3-5 seconds** on CPU-only
- Centroid computation: 7 intents × mean of ~12 vectors × 768 dims ≈ negligible (< 1ms numpy)
- **Total expected: 2-5 seconds at agent startup**
- This runs once at init, not per query. Acceptable.

**Measurement suggestion:** Wrap `_build_centroids()` with a timing log:
```python
t0 = time.monotonic()
self._centroids = self._build_centroids()
logger.info("Centroid build: %.2fs for %d prototypes", time.monotonic() - t0, total_prototypes)
```

### 4. Memory Footprint

- 80 prototype vectors: 80 × 768 × 4 bytes = 245 KB
- 7 centroid vectors: 7 × 768 × 4 bytes = 21 KB
- Total: **~266 KB** — negligible
- Note: if using numpy arrays instead of Python lists, add ~100 bytes overhead per array. Still negligible.

### 5. Config Management

`intent_prototypes.yaml` should live alongside `routing_policy.yaml` in the existing `config/` directory:
```
config/
  routing_policy.yaml        # existing
  intent_prototypes.yaml     # new
  taxonomy.yaml              # existing (if present)
```

The factory function defaults to `config/intent_prototypes.yaml` — use a relative path from project root or `Path(__file__).parent.parent / "config"` for robustness.

### 6. Ollama Availability

**Current behavior:** If Ollama is down, `embed_text()` raises `httpx.HTTPError` (no silent fallback).

**Recommendation for classifier init:**
```python
def __init__(self, ...):
    try:
        self._centroids = self._build_centroids()
    except (httpx.HTTPError, httpx.ConnectError) as e:
        raise RuntimeError(
            f"EmbeddingClassifier init failed: Ollama unavailable at {embed_fn.__self__.base_url}. "
            f"Cannot build intent centroids. Original error: {e}"
        ) from e
```

At query time, if `embed_text()` fails:
```python
def classify(self, query: str) -> ClassificationResult:
    try:
        query_vec = self._embed_fn(query)
    except Exception:
        logger.error("Embedding failed for query, falling back to conversational")
        return ClassificationResult(
            intent="conversational", confidence=0.0, margin=0.0,
            scores={}, threshold_met=False, margin_ok=False,
        )
```

Fail fast at init (can't start without centroids), graceful degradation at query time (one bad embed shouldn't crash the service).

### 7. Thread Safety

`ArchitectureAgent` in the current codebase is **stateless** — it receives `last_doc_refs` as a parameter and has no mutable instance state for conversation tracking (that lives in `chat_ui.py`'s module-level dicts).

If `SessionContext` is added **inside** `ArchitectureAgent`, it becomes stateful. Since FastAPI handles requests concurrently:
- If there's one `ArchitectureAgent` instance shared across requests (current pattern via `_architecture_agent` global at `chat_ui.py:55`), `SessionContext` would be shared across all conversations → race conditions.
- Solution: `SessionContext` must be **per-conversation**, stored in the same place as `_conversation_doc_refs` (chat_ui.py's module-level dict), keyed by `conversation_id`.

**Recommendation:** Store `SessionContext` instances in `chat_ui.py`:
```python
_conversation_sessions: dict[str, SessionContext] = {}
```
Pass the resolved state into `query()` via the existing `last_doc_refs` parameter. This preserves the agent's statelessness.

### 8. `chat_ui.py` Impact

**Minimal if done correctly.** The plan's `SessionContext` replaces the agent-side `_FOLLOWUP_MARKER_RE` check, but `chat_ui.py`'s own `resolve_followup()` (lines 150-226) is a separate, independent system that handles subject-based rewrites ("list them" → "list dars").

For v1:
- `chat_ui.py`'s `resolve_followup()` stays **unchanged**
- `_conversation_doc_refs` caching at lines 903-959 stays **unchanged** (but could optionally be replaced by `SessionContext`)
- The `stream_architecture_response()` function continues to pass `last_doc_refs` into `query()`
- The new classifier lives inside `ArchitectureAgent.__init__()` and is called in `query()`

The only change in `chat_ui.py` is adding `embedding_classifier_enabled` to the routing policy read (if using the feature flag approach).

---

## Part 4: Risk Assessment

### Risk 1: Parallel-Run Divergence Masking Real Issues (Medium)

During parallel-run, both routers execute and disagreements are logged. The risk is that the team sees disagreements, adds prototypes to fix them, and declares victory — but the disagreements being fixed are the **easy cases** (the ones that also break the old router). The hard cases are novel phrasings that neither router has seen, and those won't show up in the parallel-run logs because they require user testing.

**Mitigation:** In addition to parallel-run logging, run the manual demo pack against the new classifier **before cutover**. The demo pack's adversarial cases (AD-1 through AD-10) are the closest proxy for novel user behavior.

### Risk 2: `followup` Intent Mislabeled as `lookup_doc` (Medium)

As noted in 2.1, embedding-based classification of follow-up queries ("Show it", "Tell me about that") may not reliably separate from `lookup_doc` ("Show ADR.12", "Tell me about ADR.12") because the pronoun is a low-signal token in embedding space.

**Mitigation:** If `followup` classification F1 is below 0.9 in testing, fall back to rule-based anaphora detection (which is already implemented in `SessionContext._has_anaphora()`). Use a hybrid: classify intent with 6 classes (no `followup`), then check `_has_anaphora()` + empty doc refs → `followup`. This is exactly how entity extraction works: structural parsing, not learned.

### Risk 3: `RouteTrace` Format Change Breaks Frontend (Low)

The frontend at `chat_ui.py:962` emits `route_trace` as an SSE event consumed by the UI. The `RouteTrace` dataclass has fields like `signals`, `scores`, `winner`. If these change shape (signals removed, scores become classifier scores), the frontend may break or display misleading information.

**Mitigation:** Keep the `RouteTrace` field names stable. Map classifier output to the existing schema:
```python
trace = RouteTrace(
    signals={"classifier_intent": result.intent, "classifier_confidence": result.confidence},
    scores=result.scores,  # dict[str, float] — same shape
    winner=result.intent,
    threshold_met=result.threshold_met,
    margin_ok=result.margin_ok,
    ...
)
```

---

## Part 5: Recommendations Summary

### Do Before Implementation

1. **Pad prototype counts** — ensure every intent has ≥ 10 prototypes (currently `count` has 6, `list` has 8)
2. **Fix doc_refs type** — change `SessionState.last_doc_refs` from `list[str]` to `list[dict]` matching the codebase convention
3. **Decide SessionContext location** — recommend `chat_ui.py` (per-conversation dict), not inside `ArchitectureAgent`
4. **Add `embedding_classifier_enabled: false`** to `routing_policy.yaml` with the removal-date comment

### Do During Implementation

5. **Keep old functions available during parallel-run** — import breakage in 50+ tests is worse than temporary dead code
6. **Extend `_detect_semantic_scope()` instead of writing `_determine_scope()`** — same logic, less new code
7. **Handle session updates in `chat_ui.py`**, not in `query()` (early returns prevent end-of-method execution)
8. **Consider making `followup` a rule-based pre-check** rather than an embedding intent — test embedding accuracy first, fall back to rules if needed

### Do After Implementation

9. **Consolidate `chat_ui.py`'s `resolve_followup()` with `SessionContext`** — two follow-up systems is confusing
10. **Evaluate `intent_router.py` migration** — can it use the same `EmbeddingClassifier` with Elysia-specific prototypes?
11. **Remove the feature flag** by the planned date (2025-03-15) if stable
12. **Add scope derivation from nearest prototypes** — post-v1 enhancement noted in plan

---

## Part 6: Revised Target Flow (Incorporating Findings)

```python
# In ArchitectureAgent.query():

async def query(self, question, ..., last_doc_refs=None):

    # Step 1: Entity extraction (KEPT — unchanged)
    doc_refs = _normalize_doc_ids(question)

    # Step 1b: Bare-number resolution (KEPT — unchanged, 50 lines)
    # [existing logic at lines 527-579 stays as-is]

    # Step 1c: Follow-up ref injection (MODIFIED — uses last_doc_refs from caller)
    # chat_ui.py's SessionContext resolves anaphora and passes last_doc_refs
    # Agent just checks: no current refs + last_doc_refs provided → inject
    if not doc_refs and last_doc_refs:
        doc_refs = last_doc_refs
        followup_injected = True

    # Step 2: Intent classification (NEW — replaces _extract_signals + _score_intents + _select_winner)
    if settings.embedding_classifier_enabled:
        result = self.classifier.classify(question)
        winner = result.intent
        threshold_met = result.threshold_met
        margin_ok = result.margin_ok
    else:
        # Legacy path (transitional — remove after 2025-03-15)
        signals = _extract_signals(question)
        scores = _score_intents(signals)
        winner, threshold_met, margin_ok = _select_winner(scores)

    # Step 3: Scope selection (EXTENDED — adds doc-ref priority to existing function)
    scope = _detect_semantic_scope(question, doc_refs=doc_refs)

    # Step 4: Route (KEPT — same dispatch, plus new compare handler)
    if winner == "list" and threshold_met and margin_ok:
        return await self._handle_listing_query(...)
    elif winner == "count" and threshold_met and margin_ok:
        return await self._handle_count_query(...)
    elif winner == "lookup_doc" and doc_refs:
        return await self._handle_lookup_query(...)
    elif winner == "compare" and len(doc_refs) >= 2:
        return await self._handle_compare_query(doc_refs, question)
    elif winner == "semantic_answer":
        return await self._handle_semantic_query(..., semantic_scope=scope)
    elif winner == "conversational" or (doc_refs and not threshold_met):
        return self._conversational_response(question, doc_refs)
    else:
        # Default: semantic search (matches current fallback behavior)
        return await self._handle_semantic_query(..., semantic_scope=scope)

# In chat_ui.py (caller):
# After query returns, update session (same location as current _conversation_doc_refs caching)
```

---

## Conclusion

The plan is sound in its core architecture — embedding-based classification, prototype bank, session context — but the integration section needs adjustment to match how the codebase actually manages state. The key insight is that **conversation state lives in `chat_ui.py`, not in `ArchitectureAgent`**, and the integration plan should reflect this.

The feature flag approach (Q1/A1) is the right call over git branches. The scope limitation to ArchitectureAgent only (Q2/A2) is correct. Writing a fresh compare handler (Q3/A3) is correct. Trusting the classifier over the retrieval-verb regex (Q4/A4) is correct but needs monitoring during parallel-run.

Total estimated files changed: 12 (3 new, 9 modified). Total tests needing rewrite: ~40. Tests staying as-is: ~60+. New tests to write: ~15.
