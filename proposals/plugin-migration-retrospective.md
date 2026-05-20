# From Skill-Based to Plugin-Based AInstein — Migration Retrospective

**Author:** Cagri Tekinay
**Audience:** Engineering maintainers, architecture reviewers, leadership, audit/governance
**Scope:** AInstein migration from a root-bundled skill set to a behavior-tiered plugin architecture (Plugin-Centered Architecture Program, Phases 0–6)
**Status:** Phases 0–5 landed; post-supersession drift cleanup landed; **kernel policy hardening landed and independently verified** (exact boundary in §9); Phase-6 deletion executed under an **explicit waiver** (§10)
**Governance boundary:** Personal review remote only (`origin/main` @ `6c0d6ec`); Alliander upstream **untouched** (`9f8fdd2`) unless explicitly approved
**Compliance posture:** All engagement-identifier tokens — AI-tool names, the personal account handle, personal email address, personal repository name, and the agent-config directory — verified **0** across the pushed tree (this line describes them by category by construction; it does not enumerate the literals). External-plugin human author attribution is **deliberately retained per Decision 1** — authorship of an externally-authored plugin, not a forbidden token and not an incomplete scrub.

---

## Executive abstract (leadership-ready)

I moved AInstein from an implicit monolith (a repo-root skill bundle) to
a plugin-centered architecture with explicit roles and contracts:

- **One mechanism** for all skills/plugins.
- **Behavior-tiered roles:** `kernel` (always-on host behavior) vs
  `domain` (invocable capability). ESA-specificity is config, not a tier.
- **Explicit contribution surfaces** instead of implicit persona/registry
  coupling.
- **Capability-scoped provider precedence** (deterministic, not
  load-order behavior).
- **Two-sided host/plugin capability versioning**.
- **Artifact-materialization host capability** for file-oriented plugin
  hooks, with SQLite authority preserved.

Final bundled set: `ainstein-kernel` (kernel), `esa-workflow`
(domain), `enterpower-architecture` (domain, authoritative architecture
provider). Aggregate: **15 skills (4 kernel + 2 esa-workflow + 9
enterpower)** — `esa-document-ontology` was moved kernel→esa-workflow by
later author decision (see Decision 2), so the kernel is 4, not 5.

Deletion of the legacy `ainstein-core` plugin was performed under an
explicit **waiver**, not a fully executed formal Phase-6 per-skill
parity gate. This distinction is intentional, documented here, and must
not be reclassified (§10, §D).

---

# Part A — Program narrative (first-person retrospective)

## 1. Why I did this

AInstein started as a thin orchestration layer with one implicit,
de-facto-monolithic skill set at the repo root: a single `skills/` tree,
one `skills-registry.yaml`, one `thresholds.yaml`. The host and the
plugin were conflated. That blocked the operating model my team actually
uses: we author domain capabilities (ArchiMate, principles, repo
analysis) as standalone plugins in an external authoring environment,
then embed them into AInstein, with AInstein as the host/orchestration
substrate.

With root bundling, AInstein carried *competing default copies* of
architecture-domain skills that `enterpower-architecture` already owned.
Name collisions were managed by `conflicts_with`, which masked the real
relationship: authoritative provider vs. transitional duplicate. My
target was one plugin mechanism with four explicit boundaries: role,
contribution, provider, and host capability.

## 2. Decisions I adopted

1. **Kernel-only host shipment boundary.** AInstein ships kernel
   behavior by default; domain value arrives via domain plugins. A bare
   AInstein routes and converses but has no architecture capability
   until a domain plugin is deployed. This is an honest
   product/deployment-contract change my team owns — not a regression.
2. **`esa-document-ontology` → esa-workflow (REVERSED).** Originally
   kept in the kernel (ingestion- and query-critical: the "document 22"
   ADR/PCP disambiguation degrades without it). **Later overridden by
   explicit author decision**: the ESA ADR/PCP/DAR ontology is
   ESA-specific, not generic host behavior, so it moved to the
   `esa-workflow` domain plugin. It stays `inject_mode: always` so
   behavior is preserved when esa-workflow is enabled. Owned
   consequence: it is no longer kernel-protected (disableable) and a
   deployment without esa-workflow loses ADR/PCP/DAR disambiguation —
   the same class of deployment-contract trade-off as Decision 1.
3. **Behavior-tiered, not ESA-tiered.** `role: kernel` vs `role: domain`
   is the only architectural axis. SKOSMOS (ESA workflow) is a domain
   plugin, not "special".
4. **Enterpower is the architecture-domain authority.** AInstein's
   legacy copies were transitional and were removed under an explicit
   waiver path (§10).

## 3. Target architecture (landed)

| Plugin | role | Skills |
|---|---|---|
| `ainstein-kernel` | kernel | ainstein-identity, persona-orchestrator, response-formatter, rag-quality-assurance |
| `esa-workflow` | domain | skosmos-vocabulary, esa-document-ontology (`inject_mode: always`) |
| `enterpower-architecture` | domain | archimate-oxc-generator, archimate-oxc-view-generator, archimate-tools, archimate-viewer, archimate-visual-composer, principle-generator, principle-quality-assessor, repo-to-archimate, repo-architecture-explorer |

Aggregate: **15 skills**. Same loader, same registry, same `SKILL.md`
format — kernel-ness is a declared role the host enforces, not a second
code path.

## 4. What I changed (platform contracts & runtime)

- **4.1 Manifest contract (additive).** `.ainstein-plugin/plugin.json`
  gained `role`, `manifest_version`, `requires_host_api`. Legacy
  manifests still load via safe defaults; unknown `role` rejected early.
- **4.2 Host-capability contract (two-sided versioning).** The host now
  publishes its own capability set + versions
  (`HOST_CAPABILITIES`/`host_supports()`, e.g.
  `artifact_materialization@1`), so a plugin's `requires_host_api` is
  evaluated against an explicit host declaration. `requires_host_api`
  alone is half a contract.
- **4.3 Named contribution model.** Implicit coupling replaced by named
  accessors — `classification_tags()`, `invocable_skills()`,
  `execution_routes()`, `mcp_contributions()` — and consumers
  (persona, slash router, routing, MCP bridge) rewired to them.
- **4.4 Capability-scoped provider precedence.** Precedence is
  per-capability, deterministic, kernel-excluded, lifecycle-aware.
  `conflicts_with` is kept only as legacy migration input, not the
  resolver — so directory sort-order is no longer a behavioral input.
- **4.5 Artifact materialization (`artifact_materialization@1`).**
  First-class, versioned, per-plugin opt-in host capability projecting
  the SQLite artifact store onto a real path for file-touching hooks.
  Authority model: SQLite authoritative; materialized files ephemeral;
  no automatic sync-back. Non-declaring plugins keep filename-only
  semantics unchanged.
- **4.6 Kernel policy.** `role: kernel` plugins are non-removable,
  non-shadowable, implicitly always-loaded — enforced at discovery, at
  load, and on every mutation path. Precise boundary in §9.
- **4.7 Repository layout.** Three committed plugins under `plugins/`,
  whitelisted in `.gitignore` with per-plugin junk re-assertion; the old
  root `skills/` set removed; `ainstein-core` deleted entirely.

## 5. Sequencing and rationale

Hard-part order: **contribution + versioning → materialization → split
→ deletion**. I introduced structural change only after the
observability/contract surfaces existed, with a characterization harness
as the cross-phase invariant so behavior drift could not pass silently.

## 6. Verification strategy

- **6.1 Evidence split.** Class (a) *deterministic* goldens (the four
  contribution-point outputs + per-skill storage envelope) asserted
  byte-identical across phases; class (b) *LLM-backed* captures
  (generated bodies) compared structurally only — byte-asserting
  non-deterministic generation is the "identical answers" trap.
- **6.2 Anti-vacuity.** A golden-freshness guard fails if zero
  plugins/skills were exercised. Every assert-refusal is paired with a
  positive control proving the mechanism can fire. Risk intersections
  are asserted in single ordered scenarios.
- **6.3 Skip-set governance.** Pass-count is insufficient; I diffed the
  *skip-set* vs. baseline every phase to catch a test silently sliding
  pass→skip (coverage loss masked as "0 regressions").

## 7. Major challenges and how I resolved them

- **7.1 Plugin-scoped shared-references (A0 invariant).** A group's
  `shared_references: X` only merges `<that plugin>/shared-references/X/`
  into its members — there is **no cross-plugin path**; a severed
  co-location silently no-ops (reference loss, not an error). Enterpower
  shipped flat shared-refs while its group declared
  `shared_references: archimate-shared`. I moved the files into the
  `archimate-shared/` subdir, fixed prose paths, and verified
  `archimate-oxc-generator` actually receives the merged refs. Migration
  rule learned: move group entry + binding + files atomically.
- **7.2 Threshold-routing risk (the #1 risk).** Abstention/retrieval/
  truncation are consumed via `get_skill_tuning('rag-quality-assurance',
  …)`, owner-routed. Moving rag-quality-assurance to `ainstein-kernel`
  meant its `thresholds.yaml` had to move with it, or KB limits/
  abstention silently regress to defaults. Locked with an explicit
  regression test.
- **7.3 Supersession drift cleanup.** Deleting `ainstein-core` left
  stale references in operator-facing runtime text (one fail-fast
  literally told operators to restore the deleted directory), the e2e
  fixture body, docs, and synthetic test names. I missed some on the
  first pass and over-narrowed a closure claim ("only 3 lines in 1
  file") that was false (50 lines / 14 files). I corrected the process:
  exhaustive enumeration + invite independent `git grep`, never certify
  scope on assertion. Separated accurate historical provenance from
  stale operational text; deleted the superseded RFC.

## 8. Lessons learned

1. Characterize before you move — deterministic goldens as a cross-phase
   invariant turn "asserted parity" into reproducible evidence.
2. Skip-set diff, not pass-count — a smaller skip-set is a regression.
3. Assert-refusal without a paired positive control is untrustworthy.
4. Shared-references is plugin-local; move group+binding+files
   atomically — cross-plugin = silent no-op.
5. Provider precedence must be designed (capability-scoped), not
   discovered (load-order).
6. Two-sided versioning removes host/plugin contract ambiguity.
7. Kernel policy must be enforced beyond the convenient mutation path —
   at discovery and load too.
8. **A waiver stays a waiver in every final record** — never silently
   reclassified as a passed gate. Own false claims plainly; enumerate
   instead of asserting "only X".

## 9. Kernel policy — precise enforcement boundary

Stated precisely to avoid both over- and under-claiming.

### 9.1 Landed and verified
- **Mutation paths:** kernel skill/group disable attempts are rejected
  (`set_skill_enabled`, `set_skill_enabled_in_plugin`,
  `set_group_enabled`) and kernel entries are excluded from
  `conflicts_with` / domain-provider precedence. (Commit `cc05858`.)
- **Discovery (startup):** `_require_kernel_plugin()` fails fast if
  plugins are discovered but none declares `role: kernel`. (Commit
  `55bb931`.)
- **Load:** a kernel skill marked `enabled: false` in registry YAML is
  force-enabled at load with a WARNING; domain skills are untouched
  (kernel-scoped, not enable-everything). (Commit `55bb931`.)
- Each with a paired positive control + the kernel×domain intersection
  asserted in one pass (`tests/test_phase4_kernel_split.py`).

### 9.2 Verification status
This is "done" by the doc's own bar — **enforcing code path + tests are
commit-linked** (`55bb931`), the full suite is green (911 passed / 102
skipped at `bde12f2`), and the discovery/load/mutation enforcement was
**independently reviewer-verified** this engagement
(`multi_registry.py` discovery fail-fast, load-time force-enable,
mutation rejection). There is **no open kernel-hardening item**.

## 10. Phase-6 governance status — waiver, not passed gate

**The formal gate was not executed.** The plan's per-skill parity gate
(storage-envelope byte-comparison + generated-body structure-equivalence
+ a committed reproducible regression diff per deleted path, with
`archimate-generator` pre-flagged non-parity by output format) was
**not** performed.

**The decision path I actually took:** explicit author waiver
("enterpower is the driver; those skills shouldn't exist in
ainstein-core"); compensating behavioral guard = the live KB structural
regression (5 golden queries, incl. the ontology-dependent doc-22
disambiguation); trace recorded in commit history (`4170c06`).

This is valid because it is my decision to own — **but it is a *waived*
gate, not a *passed* one, and must never be reclassified as "parity gate
passed".** If Alliander-readiness requires the formal gate, it must be
executed then; it has not been to date. (See §C.3, §D.)

## 11. Deferred follow-up

The enterpower interactive viewer (`archimate-visual-composer`,
`archimate-viewer`) remains Vite/MCP-preview-server oriented; the
`preview` MCP server ships but no skill declares `mcp_servers:
[preview]`, so it is intentionally unwired. Deferred objective:
artifact-native self-contained HTML output (same operational model as
`repo-architecture-explorer`), removing MCP-preview coupling for this
path. Tracked as O-02 (§C.4).

## 12. Current-state declaration

AInstein now runs as a plugin-centered architecture with explicit
roles, named contribution contracts, capability-scoped provider
precedence, two-sided host-capability versioning, and opt-in artifact
materialization. The migration objective is achieved at program level.
Kernel hardening is landed and verified (§9). Legacy deletion is
governed by an explicit, preserved waiver (§10). Remaining work is the
viewer artifactization (O-02) and, only if Alliander-readiness demands
it, the formal per-skill parity gate (O-03).

---

# Part B — Leadership brief

**What changed.** Replaced the monolithic root skill bundle with three
role-explicit plugins; made host behavior (kernel) vs invocable domain
capability structurally explicit; introduced deterministic
capability-scoped provider precedence and two-sided host/plugin
capability versioning; added an artifact-materialization host capability
for file-oriented plugin tooling.

**Why it matters.** Removes long-term dual-provider drift and load-order
coupling; aligns the architecture with the team's actual delivery model
(external plugin authoring + AInstein embedding); improves operability,
auditability, and migration safety.

**Risk posture.** Major migration risk classes were controlled via
deterministic characterization, anti-vacuity controls, skip-set
discipline, and a logged structural KB regression. Legacy deletion
happened under an explicit waiver, not a fully executed formal parity
gate (preserved as such, §10/§D).

**Remaining items.** Viewer artifact-native rework (O-02); formal
per-skill parity gate only if Alliander-readiness requires it (O-03,
currently waived). Kernel startup/load hardening is **complete and
verified** (not open).

---

# Part C — Technical annex (evidence & traceability)

## C.1 Milestone → commit → tests → outcome

SHAs are real, on `feature/plugin-architecture-migration`. Test outcome
verified this engagement: full suite **911 passed / 102 skipped** at
`bde12f2` (skips environment-gated; skip-set held vs. baseline).

| Milestone | Commit | Tests / files | Outcome |
|---|---|---|---|
| Phase 0 — characterization harness | `6eb2c08` | `tests/test_phase0_characterization.py` | Deterministic surfaces + freshness guard; re-baselined post-supersession |
| Phase 1 — manifest contract + host capability registry | `31f7023` | `tests/test_phase1_manifest_contract.py` | `role`/`manifest_version`/`requires_host_api` additive; `HOST_CAPABILITIES` |
| Phase 2a — precedence schema fields | `c9ef133` | `SkillRegistryEntry` (capability/precedence/lifecycle) | Additive schema |
| Phase 2b — precedence resolver + named accessors | `c2ad8c2` | `tests/test_phase2_provider_precedence.py` | Capability-scoped, deterministic, kernel-excluded |
| Phase 3 — artifact materialization | `45bec2c` | `tests/test_phase3_artifact_materialization.py` | Opt-in real-path + cleanup; SQLite authoritative |
| Phase 4 — split | `cc05858` | `tests/test_phase4_kernel_split.py` | 3-plugin split; kernel mutation-path policy |
| Phase 5 — supersession | `4170c06` | Phase-0 re-baseline + ownership checks | 15-skill aggregate; enterpower authoritative; A0 fix |
| Drift cleanup | `94f594c` | README/loader/registry/fixture text | Stale operator references corrected |
| Kernel hardening (Amendment 4) | `55bb931` | `tests/test_phase4_kernel_split.py` (added) | Discovery fail-fast + load force-enable + paired controls |
| RFC delete + 2 stale-ref misses | `bde12f2` | docs + 2 test files | Superseded RFC removed; misses fixed |

Predecessor program (context, already landed earlier): `b1ed5a9`
(Plugin manifest + loader) → `5e6eca5` (multi-plugin registry) →
`b762073` (bundled skills → ainstein-core layout) → `df2ca2d` (relocate
to `plugins/ainstein-core/`) → `cb43eda` (engagement-start HEAD).

## C.2 Reproduction transcript (run, log, archive)

```bash
# inventory / plugin surfaces (no LLM/Weaviate)
uv run python - <<'PY'
from pathlib import Path
from aion.skills.multi_registry import MultiPluginRegistry
from aion.skills.plugin import load_plugin_manifest
roots = [Path("plugins/ainstein-kernel"), Path("plugins/esa-workflow"),
         Path("plugins/enterpower-architecture")]
m = MultiPluginRegistry()
for r in sorted(roots): m.add_plugin_from_object(load_plugin_manifest(r))
m.load()
print("plugins:", m.list_plugins())
print("skill_count:", len(m.list_skills()))
print("owners sample:", {s: m.get_owner(s) for s in
      ["ainstein-identity","skosmos-vocabulary","archimate-tools"]})
print("groups:", [(g.name, g.shared_references, g.skills) for g in m.list_groups()])
PY

# phased subset + full suite
uv run pytest tests/test_phase0_characterization.py \
  tests/test_phase1_manifest_contract.py \
  tests/test_phase2_provider_precedence.py \
  tests/test_phase3_artifact_materialization.py \
  tests/test_phase4_kernel_split.py -q
uv run pytest -q                       # expect 911 passed / 102 skipped

# skip-set diff (not pass-count)
uv run pytest -q -rs > test_run_current.txt   # diff SKIPPED set vs. baseline

# KB structural regression (provisioned stack) — log, do not assert
for q in "What ADRs exist in the system?" "What PCPs exist in the system?" \
  "What are the consequences of ADR.29?" "What is document 22?" "What is ADR 12?"; do
  uv run aion query "$q"; done   # structural-equivalence, not byte-identity

# residual drift sweep
git grep -n "ainstein-core" -- . | grep -vE "provenance|deleted|superseded|re-baseline"
```

## C.3 Phase-6 waiver record

| Field | Value |
|---|---|
| Waived gate | Formal per-skill parity/deletion gate (byte storage-envelope + structural body + committed reproducible diff per deleted path) |
| Waiver authority | Cagri Tekinay (author/owner), explicit and repeated |
| Scope | Deletion of `plugins/ainstein-core/` (7 legacy architecture-domain skills + the archimate group/shared-refs unit) |
| Compensating check | Live KB structural regression (5 golden queries incl. doc-22 disambiguation); full suite 911/102 green |
| Trace | Commit `4170c06`; this retrospective §10 |
| Reclassification allowed? | **No** — "waived" ≠ "passed" in any final record |
| Reopen trigger | Alliander-readiness assessment requiring the formal gate |

## C.4 Open-items register

| ID | Item | Status |
|---|---|---|
| O-01 | Kernel startup/load strict invariant | **DONE** — commit `55bb931`, tests + reviewer-verified (§9) |
| O-02 | Enterpower viewer self-contained HTML artifactization | OPEN — deferred (§11) |
| O-03 | Formal per-skill parity gate for the Phase-6 deletion | OPEN — **waived**; required only if Alliander-readiness demands it (§10) |
| O-04 | Governance closeout packaging | OPEN — this document is part of it |

---

# Part D — Approval language (recommended verbatim)

> "Program approved as a staged migration architecture and
> implementation sequence. Kernel startup/load/mutation enforcement is
> landed and verified. **Phase-6 deletion is governed by an explicit
> waiver and is not retroactively certified by a formal per-skill parity
> gate unless that gate is explicitly re-executed and evidenced per
> deleted path.** 'Program approved' must never be read as 'Phase-6
> parity gate passed.'"

---

# Part E — State at a glance (one page)

- Architecture objective: **Achieved**
- Plugin model: **Uniform + behavior-tiered (kernel/domain)**
- Contribution model: **Named accessors; explicit surfaces**
- Provider model: **Capability-scoped deterministic precedence**
- Host contract: **Two-sided versioned capabilities**
- Artifact model: **SQLite-authoritative + opt-in ephemeral materialization**
- Supersession: **Landed (enterpower authoritative; 15 skills)**
- Kernel hardening: **Landed + verified (discovery + load + mutation)**
- Legacy deletion: **Executed under explicit waiver (not a passed gate)**
- Remaining: **viewer artifactization (O-02); formal parity gate only if Alliander-readiness requires (O-03)**
- Governance boundary: **personal remote only; Alliander untouched (`9f8fdd2`)**
- Compliance: **engagement-identifiers verified 0; author attribution retained by Decision 1 (not an incomplete scrub)**
- Verification: **full suite 911/102 green; KB structural regression logged; skip-set held**
