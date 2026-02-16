# Rollback Map

> Auto-generated fallback reference for AION-AINSTEIN routing and strictness changes.
> Regenerate with: `make rollback-map` or `bash scripts/dev/commit_overview.sh`

## Known Good Baseline

| Label | Commit | Description |
|-------|--------|-------------|
| **Pre-strictness baseline** | `130935f` | Server-side ADR filtering using doc_type allow-list — first deterministic routing commit. Everything before this is "classic" Elysia-only routing. |
| **Phase 4 stable** | `f2ed835` | Phase 4 compliance: server-side filtering and ambiguity-safe routing. Deterministic list serialization working, no follow-up binding or DAR extraction yet. |
| **Phase 5 stable** | `f9aea62` | SKOSMOS local-first terminology verification. All Phase 5 Gap A+F features landed. |
| **Portability refactor** | `d219dc5` | Externalized hardcoded logic to config. Taxonomy YAML introduced. |
| **Last known demo-safe** | `ccecd4f` | HEAD at time of this PR. All existing routes working but keyword-triggered. |

## Commit Groups

### Routing (keyword triggers, list detection, short-circuits)

| Commit | Message | Risk | Symptom Addressed |
|--------|---------|------|-------------------|
| `130935f` | Server-side ADR filtering using doc_type allow-list | Low | ADRs mixed with DARs in search results |
| `f2ed835` | Phase 4 compliance: Server-side filtering and ambiguity-safe routing | Medium | Ambiguous queries returning wrong doc types |
| `c875485` | Harden list routing: word-boundary regex, clarification for ambiguous lists | Medium | "What is an ADR?" triggering list_all_adrs |
| `26189ab` | Fix plural ADR routing, code review hardening, blue assistant theme | Low | "ADRs" not matching singular pattern |
| `62c6a84` | Add conceptual compare route + harden list detector precision | Medium | "What's the difference between ADR and PCP?" dumping a list |
| `ccecd4f` | Fix 'What is a DAR?' misrouted to list: add definitional doc-type route | Medium | "What is a DAR?" triggering list of 49 DARs |
| `bbb47fa` | Fix DAR listing regressions, add scope gating, extend follow-up resolution | High | DAR lists broken after prior fix, follow-ups failing |

### Formatter / Contract (response structure, JSON enforcement)

| Commit | Message | Risk | Symptom Addressed |
|--------|---------|------|-------------------|
| `92d225d` | Deterministic list response serialization for contract compliance | Low | List responses not matching JSON contract |
| `8aedf63` | Fix list transparency labels: use collection-specific names | Low | "Showing 5 of 18 items" instead of "5 of 18 ADRs" |
| `3cb755a` | Add raw fallback sanitizer and session regression test framework | Low | Protocol artifacts leaking into user responses |
| `d049407` | P0-P1 field feedback fixes: formatter fallback, PCP30 filter, meta route | Medium | Multiple field-reported issues |

### Approvals / DAR Extraction

| Commit | Message | Risk | Symptom Addressed |
|--------|---------|------|-------------------|
| `91552f7` | Add deterministic approval extraction and fix resource warnings | Medium | Approval queries returning hallucinated approvers |
| `638af17` | Fix DAR listing + deterministic short-circuit + PolicyDocument guard | Medium | DAR list broken, policies leaking into DAR results |
| `87735bf` | Add DAR table extraction tests and DAR vs non-DAR smoke test | Low | No test coverage for approval parsing |

### Meta Route (AInstein identity, system questions)

| Commit | Message | Risk | Symptom Addressed |
|--------|---------|------|-------------------|
| `7cf9f01` | AInstein identity layer + DAR topical-marker routing fix | Medium | "Who are you?" querying ADR collection |
| `d049407` | P0-P1 field feedback fixes (meta route component) | Low | Meta route missing some phrasings |

### Follow-Up Binding (conversational context)

| Commit | Message | Risk | Symptom Addressed |
|--------|---------|------|-------------------|
| `8edef4f` | Add follow-up binding: 'list them' resolves to last mentioned subject | Medium | "list them" after DAR discussion → no results |
| `bbb47fa` | Fix DAR listing regressions, add scope gating, extend follow-up resolution | High | Follow-up patterns not covering enough phrasings |

### Ingestion / Classification (doc_type, markdown parsing)

| Commit | Message | Risk | Symptom Addressed |
|--------|---------|------|-------------------|
| `5d519eb` | Fix template misclassification: numbered files always content | Low | ADR.0000 classified as template |
| `94a3b9a` | Add ESA Document Taxonomy contract and fix routing/enforcement issues | Medium | No formal taxonomy, ad-hoc doc_type values |
| `5c77b45` | Fix consequences regex to match ### headings and skip #### subsections | Low | Consequences section missing from ADR chunks |
| `45899da` | Rename doc/index.md to esa_doc_registry.md + deterministic ingestion rules | Low | index.md files ingested as content |

### SKOSMOS / Terminology Verification

| Commit | Message | Risk | Symptom Addressed |
|--------|---------|------|-------------------|
| `f9aea62` | Phase 5 Gap A+F: SKOSMOS local-first terminology verification | Medium | CamelCase terms not verified before answering |
| `e7c5530` | Fix term extraction regex and abstention logic | Low | Regex over-matching common words |

## Safe Revert Targets

| If you need to… | Revert to | What you lose |
|-----------------|-----------|---------------|
| Remove all keyword routing fixes | `d219dc5` (portability refactor) | All list detection hardening, conceptual compare, definitional routes, follow-up binding, DAR extraction |
| Remove only follow-up binding | Cherry-pick revert `8edef4f` + `bbb47fa` follow-up parts | Follow-up resolution only |
| Remove only meta route | Cherry-pick revert `7cf9f01` meta parts | AInstein identity responses |
| Remove DAR extraction | Cherry-pick revert `91552f7` + `638af17` | Deterministic approval parsing |
| Remove conceptual compare + definitional | Cherry-pick revert `62c6a84` + `ccecd4f` | "What is a DAR?" and "difference between" routes |
| Full reset to Phase 4 | `f2ed835` | Everything after Phase 4 compliance |
