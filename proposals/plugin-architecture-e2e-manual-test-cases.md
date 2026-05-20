# AInstein Plugin Architecture — Functional E2E Test Plan

**Scope:** Hand-run functional verification of the post-supersession
plugin architecture: 3 plugins — `ainstein-kernel` (role: kernel),
`esa-workflow`, `enterpower-architecture` (authoritative);
`ainstein-core` deleted; kernel invariants live; the interactive viewer
known-unwired/deferred.

## Why this plan exists (read first)

The automated suite (911 passed / 102 skipped) is **logic-level**. The
102 skips are exactly the live behavioral paths (Weaviate/LLM/token
gated). Functional testing = running those paths plus the seams the
suite structurally cannot reach.

**The single highest-value target.** The irreversible Phase-6 deletion
of `ainstein-core` stands on KB-structural-equivalence + author
authorization — **not** the plan's formal per-skill parity audit. So the
one thing functional testing must establish, because nothing else has,
is: **do enterpower's superseding skills actually produce usable
archimate / principle / repo output now that ainstein-core's are gone?**
If you run only one thing, run **Tier B / B2**.

## Disciplines (carry into every case)

- **Skip-set diff, not pass-count.** Tier B should move env-gated tests
  skipped→passed. Record which moved; assert **none** slid pass→skip.
- **Structural-equivalence gate.** All LLM-generated output (golden
  answers, archimate/principle bodies) is judged by *shape*
  (schema/element-set/format), never byte-identity — LLM output is
  non-deterministic.
- **Paired positive control** for every assert-absence / assert-refusal
  (kernel-can't-disable needs domain-can-disable; fail-fast needs
  boots-when-present). A refusal test is vacuous without proof the path
  can otherwise act.
- **Untested intersections in one ordered pass.** kernel-split ×
  persona-tag-union (B3) and viewer × hook (S3) are asserted together,
  not as separate tests — separate tests let the silent combination
  through.
- **Run, log, reproduce.** The KB gate especially: capture logged output;
  never assert "PASS" without the reproducible transcript.

## Environment matrix

| Tier | Needs | Run where |
|---|---|---|
| **A — structural / invariant** | repo + `uv run aion chat`; no LLM/Weaviate | anywhere; run first (catches structural breakage before spending LLM/Weaviate) |
| **B — behavioral** | provisioned stack: Weaviate (engagement used `:8090`), LLM provider (gpt-5.2), `GITHUB_TOKEN`, Node/npm for enterpower's Vite MCP | provisioned env only |

| Item | Value |
|---|---|
| Start | `uv run aion chat` (binds `127.0.0.1`) |
| Chat UI | `http://localhost:8081/` |
| Plugin Management UI | `http://localhost:8081/plugins` (`/skills` 308-redirects here) |
| Mutation endpoint (used in A6) | `PUT /api/plugins/{plugin}/skills/{skill}/enabled` |
| Expected aggregate | 15 skills: 4 kernel + 2 esa-workflow (skosmos + esa-document-ontology) + 9 enterpower |

> "Pass" = every *Expected* bullet observed. Seam cases (S1–S3) pass by
> being **honestly characterized and reported**, never by being green.

---

# TIER A — kernel invariants & structure (cheap, run anywhere first)

### A1 — Boot + per-plugin attribution *(UI)*
- **Validates:** discovery of the committed bundled set; kernel-presence
  invariant doesn't false-trip on the real set; contribution attribution.
- **Steps:**
  1. `uv run aion chat`; watch console; open `http://localhost:8081/`.
  2. Open `http://localhost:8081/plugins`; inspect skills and owning plugin.
- **Expected:**
  - Boots with no "No plugins discovered" / "No `role: kernel` plugin
    discovered" error; chat UI accepts input.
  - Exactly **15** skills; owners exactly:
    - `ainstein-kernel` (4): ainstein-identity, persona-orchestrator,
      response-formatter, rag-quality-assurance
    - `esa-workflow` (2): skosmos-vocabulary, esa-document-ontology
      (`inject_mode: always` — moved here from the kernel; ESA-specific)
    - `enterpower-architecture`: archimate-oxc-generator,
      archimate-oxc-view-generator, archimate-tools, archimate-viewer,
      archimate-visual-composer, principle-generator,
      principle-quality-assessor, repo-to-archimate,
      repo-architecture-explorer
  - **No** `ainstein-core`; **no** `archimate-generator` /
    `archimate-view-generator` (old names) anywhere.

### A2 — Kernel skill cannot be disabled + domain skill can *(UI; one pass)*
- **Validates:** kernel non-removability on the mutation path, with its
  mandatory positive control in the same pass.
- **Steps:**
  1. `/plugins` → toggle a kernel skill off (e.g. `persona-orchestrator`).
  2. In the same session, toggle a domain skill off then on
     (e.g. `repo-architecture-explorer`).
- **Expected:**
  - Kernel toggle **rejected** with a kernel-policy error; skill stays
    enabled after reload.
  - Domain toggle **succeeds** both ways (proves the refusal is the
    policy firing, not a broken path).

### A3 — Slash surface reflects enable state *(UI)*
- **Validates:** invocable-skills contribution = enabled ∧ on_demand.
- **Steps:** `/plugins` → disable `principle-quality-assessor`; in chat
  send `/principle-quality-assessor`; re-enable; send it again.
- **Expected:** disabled → does not resolve; re-enabled → resolves.

### A4 — Discovery fail-fast + boots-when-present *(engineer-assisted, not UI; one pass)*
- **Validates:** kernel-presence startup invariant + its positive control.
- **Steps:**
  1. Temporarily make the kernel undiscoverable (rename
     `plugins/ainstein-kernel/` aside, **or** flip its
     `.ainstein-plugin/plugin.json` `role` to `domain`). Start
     `uv run aion chat`.
  2. Restore it exactly; start again.
- **Expected:**
  - Step 1: startup **hard-fails** with *"No `role: kernel` plugin
    discovered…"* naming `ainstein-kernel`.
  - Step 2: boots cleanly (positive control — failure is the policy, not
    a broken boot).

### A5 — Load-time force-enable of a disabled kernel skill + domain control *(engineer-assisted; one pass)*
- **Validates:** Invariant 2 (kernel skill disabled in YAML is
  force-enabled at load) is kernel-scoped, not enable-everything.
- **Steps:**
  1. In `ainstein-kernel/.ainstein-plugin/skills-registry.yaml` set one
     kernel skill `enabled: false`. Boot. Check console + `/plugins`.
  2. Revert. In `esa-workflow`'s registry set `skosmos-vocabulary`
     `enabled: false`. Boot. Check `/plugins`. Revert.
- **Expected:**
  - Step 1: a WARNING is logged; the kernel skill is **active** in
    `/plugins` despite the YAML.
  - Step 2: the domain skill **stays disabled** (force-enable did not
    fire — proves it's kernel-scoped).
  - Restore both edits afterward; A1 attribution unchanged.

### A6 — Mutation rejection at the API + domain control *(API; optional, same path as A2)*
- **Steps:** `PUT /api/plugins/ainstein-kernel/skills/persona-orchestrator/enabled`
  body `{"enabled": false}`; then the same call on
  `esa-workflow` / `skosmos-vocabulary`.
- **Expected:** kernel call rejected (policy error); domain call
  succeeds. (API-level confirmation of A2's path.)

---

# TIER B — the supersession actually works (provisioned stack)

### B1 — KB no-regression gate *(UI; run, log, reproduce)*
- **Validates:** the KB path survived the domain supersession.
  rag-quality-assurance is kernel; **esa-document-ontology is now in
  `esa-workflow`** (`inject_mode: always`) — so the "document 22"
  disambiguation depends on esa-workflow being deployed/enabled (a
  deployment-contract consequence of the Decision-2 reversal, not a
  regression). This is the gate the ainstein-core deletion rested on.
- **Steps (chat, capture each transcript):**
  1. `What ADRs exist in the system?`
  2. `What PCPs exist in the system?`
  3. `What are the consequences of ADR.29?`
  4. `What is document 22?`
  5. `What is ADR 12?`
- **Expected (structural, not byte-identical):**
  1. ≈ **18** ADRs.
  2. **31+** principles (≈41).
  3. ADR.29 OAuth/OIDC consequences (security + architecture
     implications).
  4. **Disambiguates** ADR.22 (priority-based scheduling) vs PCP.22
     (Omnichannel Multibranded) and asks which — *the
     ontology-dependent proof the kernel KB path survived*.
  5. ADR.12 → CIM (IEC 61970/61968/62325).
- **Record:** save the 5 transcripts as the reproducible gate evidence.

### B2 — ★ MUST-RUN: enterpower superseding skills produce usable output *(UI + plugin scripts)*
> This is the **substitute for the waived per-skill parity audit** — the
> only evidence the irreversible deletion didn't remove working
> capability. Pre-flagged: enterpower's OXC output is **non-parity by
> design** vs the deleted `archimate-generator` (different format) — do
> **not** expect byte-equivalence to old output; verify it is **valid
> OXC** and that downstream consumers still function.

- **B2a — ArchiMate OXC generation + validation**
  1. Chat: `/archimate-oxc-generator`, give a 2–3 sentence system
     (an app + a service + a data store).
  2. Download the produced artifact.
  3. Chat: `/archimate-tools validate` against that model **and/or** run
     enterpower's own validation script on the file.
  - **Expected:** a well-formed **ArchiMate 3.2 Open Exchange XML**
    artifact card; validation **passes**; contains elements +
    relationships.
- **B2b — Principle generate + assess**
  1. `/principle-generator` with a one-line topic.
  2. `/principle-quality-assessor` against the result.
  - **Expected:** a TOGAF-aligned principle (statement/rationale/
    implications) and a quality assessment — both produce their
    artifacts.
- **B2c — Repo → ArchiMate → explorer**
  1. `/repo-to-archimate` on a small public repo.
  2. Continue into `repo-architecture-explorer`.
  - **Expected:** analysis completes; a **self-contained interactive
    HTML explorer** artifact is produced and opens standalone.

### B3 — Persona routing on the real 3-plugin set × tag-union *(UI; one ordered pass)*
- **Validates:** the long-flagged untested intersection — kernel-split ×
  `_build_skill_tags_addendum` cross-plugin union (split changed plugin
  count/order).
- **Steps (same session):**
  1. Send an archimate-intent query (e.g. *"generate an ArchiMate model
     for a simple ordering system"*).
  2. Send a vocabulary-intent query (e.g. a SKOSMOS term lookup).
  3. Send a retrieval query (e.g. `What is ADR 12?`).
- **Expected (assert together):**
  - (1) routes to **enterpower**'s archimate skill — no error on a dead
    `ainstein-core` reference, no misroute.
  - (2) routes to **esa-workflow** skosmos; (3) to the **kernel** KB path.
  - The classification correctly spans kernel + esa-workflow + enterpower
    tags (no domain's tags missing).

### B4 — Direct-response behavior *(UI)*
- **Steps:** `Who are you?`; then `What's the weather?`
- **Expected:** identity answer with **no** KB search; polite scope
  decline with **no** KB search.

### B5 — Multi-turn synthesis *(UI)*
- **Steps:** `What ADRs exist in the system?` → follow up `Is there a
  common theme among them?`
- **Expected:** the follow-up **synthesizes** across turn 1 (no re-list,
  no "which ADRs?").

---

# KNOWN-FRAGILE SEAMS — CHARACTERIZE, DO NOT VALIDATE

> These are known-uncertain. The report must state their **actual
> behavior**; they must **not** be reported green by omission.

### S1 — Interactive viewer (KNOWN UNWIRED / deferred)
- **Status:** reworking `archimate-visual-composer` / `archimate-viewer`
  off the Vite/MCP preview server is explicitly deferred; the `preview`
  MCP server ships but no skill declares `mcp_servers: [preview]`.
- **Steps:** invoke `/archimate-viewer` and the visual-composer path.
- **Report (not pass/fail):** record the *actual* outcome — graceful
  message / error / hang / silent no-op. Do **not** record "works".

### S2 — Hook ↔ artifact-materialization seam
- **Status:** AInstein stores artifacts in SQLite; enterpower's
  `archimate-view-post-write.sh` expects a filesystem path. Whether
  Phase-3 artifact-materialization is actually wired for enterpower is
  **unverified**.
- **Steps:** produce an enterpower artifact that should trigger the
  post-write hook.
- **Report:** does the hook fire at all? Does it receive a usable real
  path or a SQLite filename / nothing? State the true status; do not
  assume the materialization capability is active.

### S3 — Viewer × hook intersection *(one ordered pass)*
- Run S1 and S2 in sequence on the same generated model and record the
  combined behavior — the silent failure most likely lives in their
  combination, not either alone.

---

## Result summary

| Case | Tier | Pass / Fail / (S = characterized) | Notes (actual vs expected) |
|---|---|---|---|
| A1 | A | | |
| A2 | A | | |
| A3 | A | | |
| A4 | A | | |
| A5 | A | | |
| A6 | A | | |
| B1 (×5) | B | | logged transcripts attached? |
| **B2a/b/c** | B | | **must-run — waived-parity substitute** |
| B3 | B | | |
| B4 | B | | |
| B5 | B | | |
| S1 | seam | characterized | actual behavior: |
| S2 | seam | characterized | hook fired? path type: |
| S3 | seam | characterized | combined behavior: |

**Acceptance:**
- **Tier A** (A1–A5) all pass — structural integrity + kernel invariants
  with controls.
- **Tier B**: B1 logged + structurally equivalent (incl. doc-22
  disambiguation); **B2a/b/c the gating must-run** (waived-parity
  substitute); B3–B5 pass.
- **Seams S1–S3**: **characterized and honestly reported**, never
  green-by-omission. A "works" claim for S1/S2 without evidence is a
  failed report, not a passed seam.
- Apply skip-set diff: confirm Tier B unskipped the env-gated suites and
  **nothing slid pass→skip**.
