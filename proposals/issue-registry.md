# AInstein — Issue Registry

Tracked, structured registry of identified runtime/behavioral defects
(distinct from: the migration-program open-items in
`plugin-migration-retrospective.md` §C.4, and the freeform local
backlog). Each issue carries enough root cause + evidence that a fix can
start without re-diagnosis. **Fix design is intentionally NOT recorded
here** — this registry tracks *what is broken and why*, not how to fix it.

**Status legend:** `OPEN` (diagnosed, not fixed) · `IN-PROGRESS` ·
`FIXED` (committed + verified) · `WONTFIX` (with rationale).

**Severity:** `CRITICAL` (core capability broken for all users) ·
`HIGH` (wrong/dangerous output or major UX failure) · `MED` · `LOW`.

| ID | Severity | Status | Title |
|---|---|---|---|
| ISS-001 | HIGH | OPEN | Vocabulary agent loops on SKOSMOS, hits tool-call limit + returns non-authoritative answer |
| ISS-002 | CRITICAL | OPEN | ArchiMate generation emits YAML, never OXC XML — "No XML found in output" |
| ISS-003 | HIGH | OPEN | Repo-analysis clone failures surface only in the UI (no server-side log); private repos fail unauthenticated |

---

## ISS-001 — Vocabulary agent loops on SKOSMOS for simple definition queries

- **Severity:** HIGH — both an efficiency failure (16 tool calls /
  41.6 s for what should be 1–2 calls) **and** a correctness failure
  (the answer ignored the authoritative definition and synthesized from
  LLM knowledge).
- **Status:** OPEN — diagnosed, not fixed.
- **Identified:** 2026-05-19 (live query "What is active power?").
- **Area:** `src/aion/agents/vocabulary_agent.py`,
  `src/aion/tools/skosmos.py`,
  `plugins/esa-workflow/skills/skosmos-vocabulary/SKILL.md`,
  `src/aion/config/runtime.yaml` (`agents.max_tool_calls`).

**Symptom:** "What is active power?" → Vocabulary agent ran ~16
`skosmos_search` calls (`'active power'`×3, `'p'`×2, `'ActivePower'`×2,
`activePower`, `PowerFlow`, `SvPowerFlow`, list-vocabularies, plus
`concept_details` on the *wrong* hits) → `Tool call limit reached
(16/15)`. Final answer led with an LLM-synthesized `P = V·I·cosφ`
explanation and an "Active Power Violation" tangent.

**Root cause (verified):**
- The authoritative definition **exists and is search hit #1**: EURLEX
  "Active power" (`…/eli/terms/631-20`) →
  `skosmos_concept_details` returns *"The real component of the apparent
  power at fundamental frequency…"*. Not missing, not ambiguous.
- `skosmos_search` returns hits with `definition: ''` **by design**
  (definitions only via `skosmos_concept_details`). The empty field
  reads to the LLM as "not found," triggering re-search.
- The mandatory step-2 (`concept_details` on the first hit) is
  **advisory prose** in the SKILL.md/docstrings; nothing in code forces
  it. The agent never fetched details for the correct hit.
- **No repeat-query dedup/short-circuit** anywhere (each `@agent.tool`
  only calls `check_iteration_limit()`); identical searches re-run at
  full budget cost.
- SKILL.md exhaustiveness guidance (lines ~69–75) has **no
  stop-condition** counterweight; "active power" spanning EURLEX/CIM/
  ESAV invites a survey.
- `max_tool_calls` has no `vocabulary_agent` key → default 15; the cap
  only truncates the thrash, it is not the cause.

---

## ISS-002 — ArchiMate generation emits YAML, never OXC XML

- **Severity:** CRITICAL — core ArchiMate generation is broken
  end-to-end for every user; the saved artifact is unusable raw YAML,
  not importable Open Exchange XML.
- **Status:** OPEN — diagnosed, not fixed.
- **Identified:** 2026-05-19 (live query "generate a simple archimate
  diagram with 2 actors…").
- **Area:** `src/aion/generation.py:350`.

**Symptom:** ArchiMate generation returns *"Generated model with
validation issues: No XML found in output"* followed by the YAML
intermediate; the artifact is saved as raw YAML, not OXC XML.

**Root cause (verified, single line):** `generation.py:350` gates the
entire YAML→XML conversion path on
`if skill_entry.name == "archimate-generator":` — the **deleted
ainstein-core skill name**. The live skill is enterpower's
**`archimate-oxc-generator`**, so the branch is always False →
`_extract_yaml` + `yaml_to_archimate_xml` are skipped → raw YAML flows
into `_validate_with_retry` → `_extract_xml` finds no `<?xml`/`<model>`
→ `"No XML found in output"`. The LLM and SKILL.md behaved correctly
(the skill mandates YAML → deterministic converter; the model produced
valid YAML).

**Why it slipped through:** the pre-flagged, **waived Phase-6
consumer-migration debt** (`archimate-generator` →
`archimate-oxc-generator` was called out as different name AND output
format → requires explicit consumer migration; that per-skill audit was
the waived gate). Also a gap in the post-supersession staleness sweeps:
tests + README were de-referenced but `src/` was never `git grep`'d for
hardcoded behavioral dependencies on the dead name. Relates to
`plugin-migration-retrospective.md` §10 (Phase-6 waiver), memory
`project-phase6-waived-gate`, and the Completion Double-Check gate
(exactly the "stale implementation / one-of-N call sites" class it must
catch).

---

## ISS-003 — Repo-analysis clone failures are UI-only (no server log); private repos fail unauthenticated

- **Severity:** HIGH — two coupled defects: (a) an **observability
  gap** (a failed operation produces *no* server-side log line, only a
  UI/SSE event — undiagnosable from logs/terminal); (b) repo analysis
  of **private repos always fails** with a misleading "not found",
  which for an Alliander-internal tool is the primary use case.
- **Status:** OPEN — diagnosed, not fixed.
- **Identified:** 2026-05-19 (live query "Analyze the architecture of
  https://github.com/Alliander/esa-ainstein-artifacts").
- **Area:** `src/aion/tools/repo_analysis.py` (`clone_repo`,
  lines ~362–444), `src/aion/agents/repo_analysis_agent.py`
  (`clone_repo` tool, lines ~56–82).

**Symptom:** Analyzing a private Alliander repo →
`Clone failed: Git clone failed: … fatal: repository '…/esa-ainstein-artifacts.git/'
not found` in the UI, then *"Repository analysis did not produce
architecture notes…"* with a **truncated/garbled** agent message
("…The repository is priva"). User confirmed: **nothing in the
terminal — the error appears only in the UI.**

**Root cause (verified):**
- **No auth on the clone.** `clone_repo` builds
  `cmd = ["git","clone","--depth","1", … clone_url_git, target]`
  (repo_analysis.py:433–436) — a plain **unauthenticated** HTTPS clone.
  No `GITHUB_TOKEN` / credential injection anywhere in the clone path
  (`git grep` of repo_analysis.py: zero `GITHUB_TOKEN`/`github_token`).
  GitHub deliberately returns *"Repository not found"* for private
  repos to unauthenticated callers (it does not reveal existence), so
  every private/Alliander repo clone fails with a cause-obscuring
  message.
- **No server-side logging on failure.** The clone-failure exits —
  repo_analysis.py:440 (`return {"error": "Git clone failed: …"}`),
  :442 (timeout), :444 (git-not-found) — **none call
  `logger.error/warning/exception`**. The only `logger.warning` in the
  function (:426) is for the unrelated stale-clone-remote-mismatch case.
  In the agent, `repo_analysis_agent.py` (~70–77) handles
  `"error" in result` by `ctx_.deps.emit_event({"type":"status",
  "content": f"Clone failed: …"})` — it **emits an SSE/UI status event
  but never logs server-side**. Net: the failure is visible only in the
  UI; the terminal/server log has no record (exactly as observed).
- **Cosmetic compounder:** stderr is truncated to `[:200]`
  (repo_analysis.py:440) and re-wrapped by the higher-level
  "did not produce architecture notes / Agent response: …" layer, so
  the UI shows a mid-word-truncated message.
