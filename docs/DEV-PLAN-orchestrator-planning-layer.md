# Implementation Plan: Fix Repo Review Misroute

**Status:** Proposal (revision 2 — replaces keyword-matching approach)
**Author:** Architecture review
**Date:** 2026-03-20

---

## 1. The Problem — Why We're Doing This

### 1.1 The Concrete Bug

A user asked AInstein: **"Review this repo"** with a GitHub URL.

They got the **inspect path** — a shallow fetch (README + directory listing via `stream_inspect_response()`) — instead of the **deep clone → AST extraction → architecture analysis** they needed.

The repo-analysis pipeline is gated behind `intent == "generation"` in `routing.py:41`:

```python
if skill_tags and "repo-analysis" in skill_tags and intent == "generation":
    return ExecutionModel.REPO_ANALYSIS
```

The Persona classified "Review this repo" as `intent=inspect` — because that's exactly what the SKILL.md told it to do.

### 1.2 Root Cause: Contradictory SKILL.md Rules

The Persona SKILL.md contains two rules that contradict each other:

**Rule A** — Repository Analysis Routing (line 180):
> When the user provides a GitHub URL and asks to **analyze, model, map, or understand the repository's architecture**, add `"repo-analysis"` to skill_tags.

**Rule B** — Inspect vs Generation table (lines 254-256):
> "Review this repo: https://github.com/..." → `inspect`, `github_refs: []`
> "What does https://github.com/org/repo do?" → `inspect`, `github_refs: []`
> "Check this repo: https://github.com/org/project" → `inspect`, `github_refs: []`

"Review this repo" IS asking to understand the repository's architecture. Rule A says: add `"repo-analysis"` + classify as `generation`. Rule B says: classify as `inspect` with no tags. The Persona follows Rule B because explicit examples override general rules — and it routes to the shallow path.

### 1.3 Why the Previous Plan Was Wrong

The v1 plan proposed adding `_implies_repo_understanding()` — a keyword matcher in the Orchestrator that would override the routing after Persona classification. This approach:

1. **Violates the project's routing philosophy.** The skills-registry.yaml says *"no keyword triggers needed"* — the LLM decides routing. Adding a keyword second-guesser after the LLM spoke is working against the architecture, not with it.
2. **Adds complexity in the wrong place.** A post-classification keyword heuristic is a code smell: it means the classification is wrong, not that we need a new layer to patch it.
3. **Is brittle.** Any keyword list becomes a maintenance burden that drifts from the Persona's actual classification rules. You'd need to keep two routing authorities in sync.

The correct fix is to resolve the contradiction where it lives: in the SKILL.md.

### 1.4 The Deeper Architecture Issue (Unchanged From v1)

There IS a legitimate need for an Orchestrator planning layer — for multi-pipeline decomposition, proactive gap detection, and dynamic step planning. But those are future capabilities. Using an Orchestrator to paper over a classification prompt bug is solving the right problem at the wrong layer.

---

## 2. The Fix — Resolve the SKILL.md Contradiction

### Design Principle

The Persona is the sole routing authority. The routing table (`get_execution_model()`) is a mechanical mapper — it trusts the Persona's output. If the Persona classifies wrong, fix the Persona's instructions, don't add a second classifier.

### What Changes

| Layer | Change |
|-------|--------|
| **Persona SKILL.md** | Reclassify "repo review/analysis" queries with GitHub URLs from `inspect` to `generation` + `repo-analysis` tag |
| **`routing.py`** | No changes. The `intent == "generation"` gate stays. |
| **`chat_ui.py`** | No changes. |
| **`orchestrator.py`** | No changes. |
| **E2E tests** | Update the misroute protection test to reflect new classification boundary |

### The Key Distinction (Revised)

The original SKILL.md drew the inspect/generation boundary at the **verb**: "review" → inspect, "generate" → generation. This is wrong for repositories, because reviewing a repo's architecture requires the deep extraction pipeline regardless of whether the user says "review," "analyze," or "generate."

The correct boundary for repositories is the **goal**:

| Goal | Intent | Tags | Pipeline |
|------|--------|------|----------|
| **Understand repo architecture** ("review this repo," "analyze this codebase," "what does this repo do?") | `generation` | `["repo-analysis"]` | Deep clone → AST → architecture notes → ArchiMate |
| **Browse a specific file** ("review this file: .../blob/main/model.xml") | `inspect` | `[]` | Shallow fetch + LLM analysis |
| **Review a generated model** ("describe the model you just generated") | `inspect` | `[]` | Load artifact from conversation |
| **Bare URL, no request** ("https://github.com/org/repo") | `inspect` | `[]` | Shallow fetch + LLM analysis |

The distinguishing signal: **is the user pointing at a whole repository and asking to understand it?** If yes → `generation` + `repo-analysis`. If they're pointing at a specific file, a previously generated model, or dropping a bare URL with no ask → `inspect`.

---

## 3. Implementation Steps

> **NON-NEGOTIABLE:** Before touching ANY existing file, read it in full. Understand what it does. Trace callers. Run existing tests. If you're going to modify an existing function, make sure you understand all its callers and that your change doesn't break them.

### Step 1: Update the Persona SKILL.md

**File:** `skills/persona-orchestrator/SKILL.md`

#### 1a. Update the `inspect` intent description (line 18)

The current `inspect` description includes repo-level examples that should now be `generation`:

**Current** (line 18, inspect examples):
```
"https://github.com/OpenSTEF/openstef", "What does https://github.com/org/repo do?", "Check this repo: https://github.com/org/project"
```

**Change to:** Remove the whole-repo examples from inspect. Keep file-level and model-level examples:

```
"Describe the model you just generated", "What elements are in this ArchiMate file?", "Analyze this architecture model", "How many relationships does the model have?", "https://github.com/org/repo/blob/main/model.xml", "Review https://github.com/org/repo/blob/main/file.archimate.xml"
```

Also update the inspect description text. Change:
> A message containing a GitHub URL is inspect when the user wants to **browse, review, or understand** the content — not when they want to generate a structured artifact from it. A bare URL with no other text is also inspect.

To:
> A message containing a GitHub URL pointing to a **specific file** (`.../blob/...`) is inspect. A **bare repository URL** with no other text is also inspect (shallow preview). But when the user asks to **review, analyze, or understand a whole repository's architecture**, that's `generation` with `repo-analysis` — see Repository Analysis Routing below.

#### 1b. Update the `generation` intent description (line 17)

Add repo-review examples to the generation examples list:

**Current examples:**
```
"Create an ArchiMate model for ADR.29", "Generate ArchiMate from the OAuth2 decision", "Build an architecture model for demand response", "Build an ArchiMate model from https://github.com/OpenSTEF/openstef", "Based on what you found in OpenSTEF, create an ArchiMate model"
```

**Add:**
```
"Review this repo: https://github.com/org/repo", "What does https://github.com/org/repo do?", "Analyze the architecture of https://github.com/org/repo", "Check this repo: https://github.com/org/project"
```

Also update the generation description text. Change:
> When the message contains GitHub URLs or references AND requests artifact generation, classify as generation (not inspect) and populate `github_refs`.

To:
> When the message contains GitHub URLs or references AND the user wants to **understand, review, or analyze the repository** (not just browse a specific file), classify as generation with `repo-analysis` tag and populate `github_refs`. This includes "review this repo" and "what does this repo do?" — these require deep analysis, not a shallow fetch.

#### 1c. Update the Repository Analysis Routing section (line 180)

**Add** "review" and "understand" to the explicit verb list:

**Current:**
> asks to **analyze, model, map, or understand the repository's architecture**

**Change to:**
> asks to **review, analyze, model, map, check, or understand the repository's architecture**

**Add examples:**
```
- "Review this repo: https://github.com/org/repo" → `skill_tags: ["repo-analysis"]`, `github_refs: ["org/repo"]`, intent: `generation`
- "What does https://github.com/org/repo do?" → `skill_tags: ["repo-analysis"]`, `github_refs: ["org/repo"]`, intent: `generation`
- "Check this repo: https://github.com/org/project" → `skill_tags: ["repo-analysis"]`, `github_refs: ["org/project"]`, intent: `generation`
```

#### 1d. Update the Inspect vs Generation table (line 243-256)

**Current table rows to change:**

| Message | Current | New |
|---------|---------|-----|
| `"https://github.com/OpenSTEF/openstef"` | inspect, [] | inspect, [] | *(no change — bare URL stays inspect)* |
| `"Review this repo: https://github.com/OpenSTEF/openstef"` | inspect, [] | **generation, ["OpenSTEF/openstef"]** |
| `"What does https://github.com/org/repo do?"` | inspect, [] | **generation, ["org/repo"]** |
| `"Check this repo: https://github.com/org/project"` | inspect, [] | **generation, ["org/project"]** |

**Add a new row for the file-level inspect case:**

| Message | Intent | github_refs | Why |
|---------|--------|-------------|-----|
| `"Review this file: https://github.com/org/repo/blob/main/model.xml"` | inspect | [] | Points at a specific file, not the whole repo |

#### 1e. Update the GitHub Reference Extraction section (line 233-241)

**Current:**
> Only populate for `generation` intent — never for `inspect`.

This rule stays correct. Since "review this repo" is now `generation`, `github_refs` will be populated automatically.

#### 1f. Add a disambiguation note

Add a new subsection after the Inspect vs Generation table:

```markdown
### Bare URL vs Repo Review

A bare GitHub URL with no accompanying text is `inspect` — it's a "show me what's there" gesture:
- `"https://github.com/org/repo"` → inspect (no explicit ask)

But once the user adds ANY verb that implies understanding the repo as a whole, it becomes `generation` + `repo-analysis`:
- `"Review https://github.com/org/repo"` → generation + repo-analysis
- `"https://github.com/org/repo — what does this do?"` → generation + repo-analysis

The only exception is verbs that target a specific file within the repo:
- `"Review https://github.com/org/repo/blob/main/README.md"` → inspect (single file)
```

### Step 2: Update E2E Test — Misroute Protection

**File:** `tests/test_e2e_chat_pipeline.py`

The existing test `test_repo_analysis_not_triggered_for_inspect_intent` (line 436) tests that `intent=inspect` + `skill_tags=["repo-analysis"]` routes to inspect, not repo_analysis.

This test is **still valid** as a routing-layer safety net — if the Persona somehow emits `inspect` + `repo-analysis`, the routing table should still send it to inspect (the `intent == "generation"` gate in `routing.py:41` protects against this). **Do not delete this test.**

However, the test docstring and scenario name need updating to reflect that this is now a defensive safety net rather than the expected happy path:

**Current docstring:**
```python
"""inspect + repo-analysis tag must NOT route to REPO_ANALYSIS.
This was the misrouting bug — 'Review this repo' classified as inspect
should take the inspect path, not the repo analysis pipeline."""
```

**Change to:**
```python
"""inspect + repo-analysis tag must NOT route to REPO_ANALYSIS.
Safety net: if the Persona misclassifies a repo query as inspect
(it should classify whole-repo queries as generation), the routing
table must still protect against triggering the extraction pipeline.
See: original misroute incident where 'Is this compliant with our
principles?' was classified as inspect+repo-analysis."""
```

### Step 3: Add a New E2E Test — Repo Review Happy Path

**File:** `tests/test_e2e_chat_pipeline.py`

Add a new test to `TestRepoAnalysisRouting` that verifies the **fixed** classification routes correctly:

```python
@pytest.mark.asyncio
async def test_repo_review_classified_as_generation_routes_to_repo_analysis(
    self, client, _mock_lifespan
):
    """'Review this repo' should be classified as generation+repo-analysis
    by the Persona, which routes to the repo analysis pipeline.
    This is the fixed behavior — previously it was classified as inspect."""
    persona_result = _make_persona_result(
        intent="generation",
        rewritten_query="Review and analyze the architecture of org/repo",
        skill_tags=["repo-analysis"],
    )
    _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

    call_log = []

    async def mock_repo_archimate(*args, **kwargs):
        call_log.append(True)
        yield f"data: {json.dumps({'type': 'complete', 'response': 'analysis', 'sources': [], 'timing': {}})}\n\n"

    with patch("aion.chat_ui.stream_repo_archimate_response", side_effect=mock_repo_archimate):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "Review this repo: https://github.com/org/repo"},
        )

    assert len(call_log) == 1  # Repo analysis pipeline was invoked
```

### Step 4: Update the Routing Comment

**File:** `src/aion/routing.py`

Update the comment at lines 36-40 to reflect the fix:

**Current:**
```python
# inspect is excluded: it's for reviewing existing models, not running the
# extraction pipeline. See: misroute incident where Persona classified
# "Is this compliant with our principles?" as inspect+repo-analysis.
```

**Change to:**
```python
# inspect is excluded: it's for reviewing existing models or browsing
# specific files — not for running the extraction pipeline. Whole-repo
# queries ("review this repo", "analyze this codebase") should be
# classified as generation+repo-analysis by the Persona (see SKILL.md
# Repository Analysis Routing section). This gate is a safety net.
# See: misroute incident where "Is this compliant with our principles?"
# was classified as inspect+repo-analysis.
```

### Step 5: Run Tests

1. Run the full test suite before making any changes. Confirm baseline.
2. Make the SKILL.md changes (Step 1).
3. Make the test changes (Steps 2-3).
4. Make the comment change (Step 4).
5. Run the full test suite again. Confirm nothing regresses.

---

## 4. What NOT to Change

These are explicit boundaries:

1. **`get_execution_model()` in `routing.py`**. The function stays as-is. The `intent == "generation"` gate is correct — it's the Persona's job to classify correctly, and the routing table maps mechanically.

2. **`orchestrator.py`**. No new `plan()` method. No keyword matching. The Orchestrator stays focused on multi-step RAG execution.

3. **`chat_ui.py` routing dispatch**. The `execution_model = get_execution_model(...)` call at line 2038 stays unchanged. No new layer between Persona and routing.

4. **`persona.py` code**. The Persona's Python logic is correct — it parses the LLM's JSON output faithfully. The fix is in the LLM's instructions (SKILL.md), not in the parsing code.

5. **Agent internals** (`rag_agent.py`, `archimate_agent.py`, `repo_analysis_agent.py`). These work. Don't touch them.

6. **`capability_gaps.py` and `capability_store.py`**. Future Orchestrator work, not this change.

---

## 5. Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Persona over-classifies file-level inspect queries as generation | Low | The SKILL.md explicitly distinguishes `/blob/` file URLs from repo URLs. The bare-URL → inspect rule provides a safe fallback. |
| Persona under-classifies — still emits inspect for "review this repo" | Medium | LLMs can be stubborn about learned patterns. **Mitigation:** The E2E test from Step 3 verifies the happy path. If the Persona still misclassifies in production, the routing safety net (inspect ≠ repo_analysis) prevents the extraction pipeline from running unexpectedly — it degrades to shallow inspect, same as today. |
| Existing inspect use cases break ("describe the model you generated") | Very Low | These queries have no GitHub URL and no repo-analysis tag. The SKILL.md changes only affect repo-level GitHub URL queries. |
| Follow-up routing changes ("Is this compliant with our principles?" after repo analysis) | None | The Follow-ups After Repository Analysis section (lines 192-204) is unchanged. Follow-ups don't get `repo-analysis` tags. |

---

## 6. Why This Is Better Than the v1 Plan

| Dimension | v1 (Orchestrator + keyword matching) | v2 (SKILL.md fix) |
|-----------|---------------------------------------|---------------------|
| **Files changed** | 4 (orchestrator.py, chat_ui.py, routing.py, tests) | 3 (SKILL.md, routing.py comment, tests) |
| **New code** | ~80 lines (Plan dataclass, plan() method, helpers, wiring) | 0 lines of Python |
| **New abstractions** | Plan dataclass, _implies_repo_understanding(), _contains_github_url() | None |
| **Runtime cost** | Sub-millisecond (pure Python), but a new code path to maintain | Zero — the Persona LLM call already happens |
| **Routing authorities** | Two (Persona + Orchestrator keyword matcher) | One (Persona) |
| **Maintenance burden** | Keyword list must stay in sync with SKILL.md rules | Single source of truth in SKILL.md |
| **Consistency with project philosophy** | Violates "no keyword triggers" | Follows existing pattern |

---

## 7. Future Work — Orchestrator Planning Layer

The v1 plan's vision of an Orchestrator planning layer is valid for **future** capabilities that genuinely exceed the Persona's classification:

1. **Multi-pipeline decomposition:** "Review this repo and compare it to our principles" → repo_analysis + RAG retrieval + synthesis. The Persona can't express this today (it returns a single intent).

2. **Proactive gap detection:** Before execution, check the capability registry. If a step needs a tool that doesn't exist, tell the user instead of silently degrading.

3. **Dynamic step planning with capability awareness:** The Orchestrator checks what agents/tools are available and builds a plan that uses them.

These are real problems that justify an Orchestrator — but they should be built when the need arises, not retrofitted as a workaround for a classification prompt bug.

---

## 8. Checklist Before Submitting

- [ ] Read `skills/persona-orchestrator/SKILL.md` in full
- [ ] Read `routing.py` in full — confirm the generation gate
- [ ] Read `tests/test_e2e_chat_pipeline.py` — understand existing misroute test
- [ ] Run full test suite — confirm baseline passes
- [ ] Update SKILL.md inspect intent description (Step 1a)
- [ ] Update SKILL.md generation intent description (Step 1b)
- [ ] Update SKILL.md Repository Analysis Routing section (Step 1c)
- [ ] Update SKILL.md Inspect vs Generation table (Step 1d)
- [ ] Add SKILL.md bare URL disambiguation note (Step 1f)
- [ ] Update E2E test docstring (Step 2)
- [ ] Add new E2E test for repo review happy path (Step 3)
- [ ] Update routing.py comment (Step 4)
- [ ] Run full test suite — confirm nothing regresses
- [ ] Manual test: "Review this repo" + GitHub URL → verify Persona classifies as generation+repo-analysis
- [ ] Manual test: "Describe the model you generated" → verify inspect still works
- [ ] Manual test: "https://github.com/org/repo" (bare URL) → verify inspect still works
- [ ] Manual test: "Generate ArchiMate from https://github.com/..." → verify generation+repo still works
