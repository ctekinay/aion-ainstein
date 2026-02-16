# Demo v1 Final Stabilization — Code Review

**Date**: 2026-02-16
**Scope**: Full architectural review of the stabilized demo v1 implementation
**Branch**: `claude/review-final-demo-SivTy`

---

## Executive Summary

The demo v1 stabilization is **well-engineered and demo-ready**. The scoring gate
architecture is clean, the invariant system is disciplined, and the test coverage
is thorough. The issues identified below are all post-demo improvements — none
are blockers.

**Verdict**: Ship the demo. Address findings in the post-demo backlog.

---

## 1. Architecture Assessment

### 1.1 Scoring Gate Design — Strong

The routing architecture in `src/agents/architecture_agent.py` follows a clean
three-stage pipeline:

```
_extract_signals() → _score_intents() → _select_winner()
```

**Strengths**:
- Signals are pure boolean features extracted from queries (lines 114-140)
- Weights are declarative and centralized in `_WEIGHTS` (lines 144-161)
- The winner selection uses argmax + threshold + margin gating (lines 215-238)
- The docstring at the top of the file explicitly forbids adding direct if-else
  routing branches — this is good architectural discipline

**The routing path coverage is complete for demo scope**:

| Path | Winner | Threshold | Tested by |
|------|--------|-----------|-----------|
| list | `list` | 1.5 | `TestListScoringGate`, `TestGoldListQueries` |
| count | `count` | 2.0 | `TestCountScoringGate`, `TestGoldCountQueries` |
| lookup_exact | `lookup_doc` | 2.0 | `TestGoldPrefixedLookup` |
| hybrid | `semantic_answer` | 1.0 | `TestGoldSemanticQueries` |
| conversational | fallback | N/A | `TestGoldCheekyQueries` |
| clarification | bare-number | N/A | `TestGoldBareNumberClarification` |

### 1.2 Bare-Number Resolution — Sound

The three-step bare-number flow (lines 474-506) is well-designed:
1. No prefixed doc ref → extract bare numbers
2. Query ADR and Principle collections by number field
3. Single match → resolve; multiple → clarification; none → fall through

The fallback chain is correct: prefixed refs take priority over bare numbers,
and bare number detection is skipped when prefixed refs exist (line 296).

### 1.3 Follow-up Binding — Correct

The follow-up binding at lines 497-506 correctly:
- Only activates when no doc ref AND last_doc_refs present AND follow-up marker detected
- Sets `has_retrieval_verb = True` to ensure the injected refs trigger lookup
- Explicit doc refs in the query override last_doc_refs (tested in gold suite)

### 1.4 Decision Chunk Selector — Robust

The 4-tier precedence in `_select_decision_chunk()` (lines 760-804) is well-
ordered and the Decision Drivers trap is explicitly tested. The negative
lookahead `(?!\s*Drivers)` in `_SECTION_DECISION_RE` prevents the known
false positive.

---

## 2. Test Infrastructure Assessment

### 2.1 CI Gate — Appropriate

The `make test-demo` target runs `test_gold_routing_suite.py` and
`test_architecture_agent.py` with `--maxfail=1`. The CI workflow
(`.github/workflows/ci.yml`) runs this on every PR and push to main.

**Observation**: The gate tests are hermetic (no Weaviate, no LLM). This is
correct for CI but means the gate only validates routing logic, not end-to-end
retrieval quality.

### 2.2 Gold Routing Suite — Comprehensive

The gold suite covers all 10 routing invariants (D1-D10) with realistic mock
data. The `_capture_trace()` helper is clean and reusable.

**Coverage count**: ~32 gold test cases + ~150 unit tests in
`test_architecture_agent.py`.

### 2.3 Test Fixture Duplication

Both `test_architecture_agent.py` and `test_gold_routing_suite.py` define
identical helper functions (`_make_chunk`, `_make_weaviate_object`,
`_make_fetch_result`, `_make_multi_collection_client`). These should be
extracted to `tests/conftest.py` post-demo to reduce maintenance burden.

---

## 3. Telemetry & Observability

### 3.1 ROUTE_TRACE — Well-Structured

The `RouteTrace` dataclass (lines 42-64) emits a JSON log line with all
relevant decision context: signals, scores, winner, threshold_met, path,
selected_chunk, and telemetry fields (bare_number_resolution,
semantic_postfilter_dropped, followup_injected).

The trace contract is tested by `TestRouteTrace` (4 test cases covering
lookup, conversational, list, and hybrid paths).

### 3.2 Observability Module

`src/observability.py` provides a clean metrics registry with Prometheus-
compatible export. Thread-safe counters and histograms are present. The
circuit breaker state tracker is minimal but functional.

---

## 4. Issues Found

### 4.1 Bug: `_post_filter_semantic_results` Accumulates Across Calls (Medium)

**File**: `src/agents/architecture_agent.py:1086-1088`

```python
self._last_postfilter_dropped = getattr(
    self, "_last_postfilter_dropped", 0
) + dropped
```

This *accumulates* the dropped count across multiple calls within the same
`query()` invocation (the method is called twice: once for ADR results and
once for principle results at lines 1130 and 1145). The `_handle_semantic_query`
method resets it at line 1116, so for a single query it is correct.

However, if the agent instance is reused across queries without going through
`_handle_semantic_query` (e.g., if someone calls `_post_filter_semantic_results`
directly), the counter would accumulate incorrectly. The current calling
pattern is safe, but the design is fragile.

**Recommendation**: Reset the counter at the start of `query()`, not inside
`_handle_semantic_query`.

### 4.2 `intent_router.py` Not Integrated into Agent Layer (Architectural Gap)

`src/intent_router.py` defines a full `IntentDecision` schema with heuristic
and LLM classifiers, but the `ArchitectureAgent` and `OrchestratorAgent` do
not use it. The agent has its own parallel scoring gate. The intent router is
used by `chat_ui.py` and `elysia_agents.py`.

This means there are **two independent routing systems**:
1. `intent_router.py` — used by the chat UI/Elysia layer
2. `architecture_agent._score_intents()` — used by the agent layer

**Impact for demo**: None. Both systems work independently. Post-demo, consider
unifying them or documenting their respective scopes clearly.

### 4.3 F-String Logging in Hot Path (Low)

9 instances of `logger.info(f"...")` and `logger.warning(f"...")` in the agent
critical path files. These evaluate the f-string even when the log level is
higher than INFO/WARNING.

**Notable**: `logger.info(f"ROUTE_TRACE {trace.to_json()}")` at line 587
calls `to_json()` on every query even if logging is disabled.

**Recommendation**: Use `logger.info("ROUTE_TRACE %s", trace.to_json())` or
guard with `if logger.isEnabledFor(logging.INFO)`.

### 4.4 `_fetch_all_objects` Pagination Safety Limit (Low)

The 10,000-object safety limit in `_fetch_all_objects()` (line 399) will
silently truncate results for very large collections. The warning is logged
but the caller receives a partial result without indication.

For demo scope this is fine (ADR/Principle collections are small), but
production use should surface this truncation to the caller.

### 4.5 Orchestrator Keyword Routing is Coarse (Low)

`OrchestratorAgent._route_query()` uses simple keyword counting to select
agents. Words like "system" and "communication" in `ARCHITECTURE_KEYWORDS`
are very broad and could cause false routing. Since the demo focuses on
`ArchitectureAgent` queries directly, this is not a demo risk.

### 4.6 Silent Exception Handlers in Non-Critical Files (Low)

9 instances of `except Exception` blocks that return default values without
logging in `doc_type_classifier.py`, `markdown_loader.py`, `skills/api.py`,
and `skills/filters.py`. These could mask configuration or parsing errors.
None are in the agent critical path.

---

## 5. Freeze Policy Compliance

The `docs/dev/demo_v1_invariants.md` freeze policy is well-defined and
enforced:

- **Change discipline**: 4-point checklist (probe, unit test, trace
  expectation, failure mode check)
- **CI gate**: `make test-demo` required before merge
- **Scope boundary**: 10 routing invariants (D1-D10), 4 traceability
  invariants (T1-T4), 3 response format invariants (R1-R3)
- **Out-of-scope items**: Clearly documented in the backlog section

The invariant table maps every behavioral guarantee to specific test names,
making it auditable.

---

## 6. Security Review

- **No hardcoded secrets**: All API keys use `pydantic-settings` with `.env`
  loading
- **No injection vectors**: Regex patterns operate on in-memory strings, not
  used in shell commands or SQL
- **Defense in depth**: `lookup_by_canonical_id()` includes a post-filter
  that strips mismatched canonical_ids even if Weaviate's filter is bypassed
- **`save_routing_policy()`**: Uses `_KNOWN_KEYS` allowlist to prevent
  arbitrary YAML injection (config.py:433-440)

---

## 7. Recommendations (Post-Demo Backlog)

| # | Item | Priority | Effort |
|---|------|----------|--------|
| 1 | Extract shared test fixtures to `conftest.py` | Medium | Small |
| 2 | Unify or document dual routing systems (intent_router vs scoring gate) | Medium | Medium |
| 3 | Replace f-string logging with lazy `%s` formatting in agent files | Low | Small |
| 4 | Reset `_last_postfilter_dropped` in `query()` instead of `_handle_semantic_query` | Low | Small |
| 5 | Surface `_fetch_all_objects` truncation to callers | Low | Small |
| 6 | Add logging to silent `except Exception` blocks in non-critical files | Low | Small |

---

## 8. Files Reviewed

| File | Lines | Role |
|------|-------|------|
| `src/agents/architecture_agent.py` | 1384 | Core routing + scoring gate |
| `src/agents/base.py` | 272 | Base agent + hybrid search |
| `src/agents/orchestrator.py` | 328 | Multi-agent coordination |
| `src/config.py` | 451 | Settings + config loading |
| `src/skills/filters.py` | 260 | Doc-type filtering |
| `src/intent_router.py` | 763 | Intent classification |
| `src/observability.py` | 337 | Metrics + structured logging |
| `src/weaviate/collections.py` | 928 | Schema definitions |
| `tests/test_architecture_agent.py` | 1993 | Unit tests (~150 cases) |
| `tests/test_gold_routing_suite.py` | 680 | Gold behavioral tests (~32 cases) |
| `.github/workflows/ci.yml` | 31 | CI pipeline |
| `Makefile` | 26 | Build targets |
| `docs/dev/demo_v1_invariants.md` | 81 | Freeze policy |
| `config/routing_policy.yaml` | 8 | Routing feature flags |
| `pyproject.toml` | 78 | Project config |
