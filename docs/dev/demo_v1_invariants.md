# Demo v1 Invariants

Gate-keeper checklist for pre-demo scope. Every change must satisfy all
invariants below. No new routing features unless they appear here.

## DEMO v1 FREEZE (active)

Only changes allowed:
1. Fix a newly discovered failing probe or gold test
2. Add/adjust a test first (red → green)
3. Don't expand routing scope

Everything else goes to the post-demo backlog.

**CI gate**: `make test-demo` must pass before any merge.

## Routing Invariants

| # | Invariant | Enforced by |
|---|-----------|-------------|
| D1 | Prefixed doc ref (ADR.12, PCP.22, DAR.12D) → exact lookup path, no hybrid | `test_canonical_lookup_no_hybrid` |
| D2 | Bare number (22, 0022) with single match → resolved, patches signals → lookup | `test_bare_0022_resolved_takes_lookup_path` |
| D3 | Bare number with multiple doc-type matches → clarification prompt, no hybrid | `test_bare_0022_ambiguous_returns_clarification`, `test_clarification_path_no_hybrid` |
| D4 | Bare number with no matches → falls through to semantic | `test_bare_number_no_match_falls_to_semantic` |
| D5 | Cheeky query (doc ref + no retrieval verb) → conversational, no retrieval | `TestCheekyQueries` (10 queries) |
| D6 | Unscoped "List all ADRs" → list path, confidence ≥ 0.95 | `test_list_wins_over_other_intents` |
| D7 | Scoped "List principles about interop" → semantic path, not list dump | `test_scores_show_list_penalty_with_qualifier` |
| D8 | COUNT query → count path | `TestCountScoringGate` |
| D9 | Semantic query → hybrid path, winner=semantic_answer, conventions excluded | `test_semantic_wins_scoring_gate`, `test_semantic_excludes_conventions_from_results` |
| D10 | Decision chunk selected deterministically (decision non-empty is primary) | `TestDecisionSelectorTierPrecedence` |

## Traceability Invariants

| # | Invariant | Enforced by |
|---|-----------|-------------|
| T1 | Every query emits a `ROUTE_TRACE` JSON log line | `TestRouteTrace` |
| T2 | Trace contains: path, winner, scores, signals, threshold_met | `test_trace_lookup_exact_for_adr_0012` |
| T3 | List path trace shows intent=list, winner=list | `test_trace_list_for_list_query` |
| T4 | Trace includes telemetry: bare_number_resolution, semantic_postfilter_dropped, followup_injected | ROUTE_TRACE JSON |

## Response Format Invariants

| # | Invariant | Enforced by |
|---|-----------|-------------|
| R1 | Lookup answer includes blockquote + canonical ID + file path | `test_adr_0012_end_to_end` |
| R2 | Clarification response lists all candidates with canonical IDs | `test_bare_0022_ambiguous_returns_clarification` |
| R3 | Conversational response suggests how to rephrase | `_conversational_response` |

## Change Discipline

Every new change must have:
1. A probe (realistic query in `smoke_probes.py` or `gold_routing_suite.py`)
2. A unit test
3. A trace expectation
4. A failure mode check (what could this break?)

If any change can't satisfy those four, it's too risky for pre-demo.

## Done for Demo v1

- Scoring gate architecture (signals → weights → winner)
- Prefixed doc-ref exact lookup with Decision chunk selection
- Bare-number resolution (single match → lookup, ambiguous → clarification)
- Cheeky query gate (10 queries, all conversational)
- List/count/semantic routing via scoring gate
- Generic semantic winner signal (has_generic_semantic)
- Post-retrieval filter for conventions/template/index
- Follow-up binding via last_doc_refs injection
- Structured ROUTE_TRACE with telemetry
- Gold routing suite (32 tests) + unit tests (150 tests)
- CI gate: `make test-demo`

## Out of Scope (Post-Demo Backlog)

- DocumentIdentity / alias layer (uuid/registry/file key unification)
- Full Elysia conversation memory (Tree pool keyed by conversation_id)
- Cross-agent context sharing
- Multi-turn disambiguation flows beyond single clarification
- Expand follow-up markers (only if a gold test fails)
- New routing branches or heuristics
