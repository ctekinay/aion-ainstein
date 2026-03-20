# Implementation Plan: Separate Planning from Classification

**Status:** Proposal
**Author:** Architecture review
**Date:** 2025-03-20

---

## 1. The Problem — Why We're Doing This

### 1.1 The Concrete Bug That Exposed the Problem

A user asked AInstein: **"Review this repo"** with a GitHub `/tree/branch` URL.

Three things broke:
1. **Branch URL parsing:** The `/tree/branch` suffix wasn't stripped correctly for `git clone`.
2. **Module grouping:** All code files collapsed into one module due to 2-level path grouping.
3. **ArchiMate generation:** Crashed because the architecture notes were too thin (too few components).

The dev fixed all three. But they were symptoms, not the root cause.

### 1.2 The Structural Problem Those Bugs Revealed

The Persona classified "Review this repo" as `intent=inspect` — correct per the SKILL.md rules (the user said "review," not "generate"). But the **repo-analysis pipeline is gated behind `intent == "generation"`** in `routing.py:41`:

```python
# routing.py:41
if skill_tags and "repo-analysis" in skill_tags and intent == "generation":
    return ExecutionModel.REPO_ANALYSIS
```

So the user got the **inspect path** — a shallow MCP fetch (README + directory listing via `stream_inspect_response()` at `chat_ui.py:1088`) — instead of the **deep clone → AST extraction → architecture analysis** they actually needed.

The comment on line 39-40 even explains why this gate exists:
```python
# inspect is excluded: it's for reviewing existing models, not running the
# extraction pipeline. See: misroute incident where Persona classified
# "Is this compliant with our principles?" as inspect+repo-analysis.
```

This was a correct fix for one misroute, but it created a new one. **The routing is rigid** — it maps intent labels to fixed execution paths. When a query falls between paths (like "review this repo" which needs deep analysis but isn't "generation"), it silently degrades.

### 1.3 The Deeper Architecture Issue

The Persona can only route to paths that already exist. Its classification is a **label** — a single word from `VALID_INTENTS`. The routing engine (`get_execution_model()`) then maps that label to a fixed pipeline. There is no middle layer that:

1. Decomposes the user's **goal** into **steps**
2. Checks which steps the system **can actually execute**
3. Identifies **gaps** and either degrades gracefully or asks the user
4. Executes the plan step-by-step

The system already has infrastructure for capability gap detection (`capability_gaps.py`, `capability_store.py`, `request_data` tool on every agent) — but it's passive and lives on the agents, not on the planning layer.

### 1.4 The `magic_fetch` Insight

The `request_data` tool (at `src/aion/tools/capability_gaps.py:12`) is a no-op tool registered on every agent. It does nothing — logs the call to SQLite via `capability_store.py`, returns `"Data retrieved successfully. Continue your reasoning."` The agent, reasoning through the problem, calls it with precise descriptions of what's missing. This becomes a prioritized roadmap of what to build next.

But it only fires **after** the wrong path has already been chosen. If the Orchestrator could do the same gap-check **before** execution, it could prevent the degradation entirely.

---

## 2. The Proposal — Separate Planning from Classification

### Current Flow
```
User Message → [Persona: classify intent] → [Router: intent→pipeline] → [Agent: execute]
```

### Proposed Flow
```
User Message → [Persona: classify intent+skills+complexity]
             → [Orchestrator: decompose goal → check capabilities → build plan]
             → [Router: execute plan steps]
```

### What Each Layer Does

| Layer | Responsibility | What Changes |
|-------|---------------|-------------|
| **Persona** | Fast classification: intent, skill_tags, complexity, query rewrite. Stays lean. | **No changes.** |
| **Orchestrator** | Receives classification. Decomposes the goal into steps. Checks each step against the capability registry. Identifies gaps. Decides execution strategy. | **New logic added here.** |
| **Router** | Executes the plan step by step. | **Minor changes** — accepts a plan instead of just intent+skills. |

### What This Fixes

1. **The repo review bug vanishes.** The Orchestrator sees the goal is "deep repo review," checks that clone + extract + summarize are all available capabilities, and routes to `REPO_ANALYSIS` regardless of whether the intent label is "inspect" or "generation."

2. **Gap detection lives in the right place.** The Orchestrator knows the full capability registry. It doesn't need the Persona to guess what's possible.

3. **Cost scales with complexity.** Simple queries get a pass-through (no overhead). Complex queries get full decomposition.

---

## 3. Implementation Steps

> **NON-NEGOTIABLE:** Before touching ANY existing file, read it in full. Understand what it does. Trace callers. Run existing tests. If you're going to modify an existing function, make sure you understand all its callers and that your change doesn't break them.

### Step 1: Add Goal Decomposition to the Orchestrator

**File:** `src/aion/orchestrator.py`

**What exists now:** `MultiStepOrchestrator.run()` (line 34) takes a `PersonaResult` and executes its `steps` sequentially. Each step is a RAG call. It only handles the "multi-step retrieval" case — it doesn't reason about which pipeline to use.

**What to add:** A new method `plan()` that sits between Persona output and execution. This method:

1. Receives `PersonaResult` (intent, skill_tags, rewritten_query, github_refs, steps, etc.)
2. Analyzes the **goal** — not just the intent label — to determine what the user actually needs
3. Checks if the selected execution path actually serves that goal
4. Returns a `Plan` object that the execution path uses

**Concrete logic for the repo review case:**

```python
# PSEUDOCODE — do NOT copy-paste. Read the actual code first.
def plan(self, persona_result: PersonaResult) -> Plan:
    """Decompose the user's goal into an execution plan.

    This is where intent-label-to-pipeline mismatches get caught.
    """
    intent = persona_result.intent
    skills = set(persona_result.skill_tags)
    has_github_url = bool(persona_result.github_refs) or _contains_github_url(persona_result.original_message)
    has_repo_path = _contains_local_path(persona_result.original_message)

    # --- Repo analysis override ---
    # The Persona correctly classifies "review this repo" as inspect.
    # But inspect routes to shallow MCP fetch, not deep analysis.
    # If the user provided a repo URL/path AND the query implies
    # understanding the repo's architecture, upgrade to repo_analysis.
    if (has_github_url or has_repo_path) and intent in ("inspect", "retrieval"):
        if _implies_repo_understanding(persona_result.rewritten_query):
            return Plan(
                execution_model=ExecutionModel.REPO_ANALYSIS,
                skill_tags=list(skills | {"repo-analysis"}),
                reason="User wants to understand a repository — upgrading from inspect to repo_analysis",
            )

    # --- Default: use the existing routing logic ---
    execution_model = get_execution_model(intent, persona_result.skill_tags)
    return Plan(execution_model=execution_model, skill_tags=persona_result.skill_tags)
```

**Key helper — `_implies_repo_understanding()`:**

This is a simple keyword/pattern check, NOT an LLM call. Examples of queries that imply deep repo understanding:
- "Review this repo"
- "Analyze the architecture"
- "What does this repo do?"
- "Map the components"
- "Understand the codebase"

Examples that do NOT (and should stay on inspect):
- "Check this ArchiMate XML file" (single file review)
- "Is this model valid?" (model validation)

**Important:** `_contains_github_url()` must handle the same URL formats that `clone_repo()` in `repo_analysis.py:363` handles (https, git@, /tree/branch suffixes). Do NOT reinvent URL parsing — look at what `clone_repo()` already does and extract/reuse that logic.

### Step 2: Create the Plan Data Structure

**File:** `src/aion/orchestrator.py` (add to existing file)

```python
@dataclass
class Plan:
    """Execution plan produced by the Orchestrator."""
    execution_model: ExecutionModel
    skill_tags: list[str]
    reason: str = ""  # Why this plan was chosen (for logging/debugging)
    upgraded_from: str | None = None  # Original execution model if overridden
```

This is deliberately minimal. It's a data class, not a framework. Expand it later if needed.

### Step 3: Wire the Orchestrator into chat_ui.py

**File:** `src/aion/chat_ui.py`

**What exists now:** At line 2038, after Persona classification, the code calls `_get_execution_model()` directly:

```python
execution_model = _get_execution_model(
    persona_result.intent, persona_result.skill_tags,
)
```

**What to change:** Insert the Orchestrator's `plan()` call between Persona and routing:

```python
# After persona classification, let the Orchestrator plan
from aion.orchestrator import MultiStepOrchestrator
orchestrator = MultiStepOrchestrator()
plan = orchestrator.plan(persona_result)
execution_model = plan.execution_model

# Log if the Orchestrator overrode the default route
if plan.upgraded_from:
    logger.info(
        "orchestrator_override",
        original=plan.upgraded_from,
        final=plan.execution_model.value,
        reason=plan.reason,
    )
```

**CRITICAL — check all downstream uses of `execution_model`:** After this point, `execution_model` is used in many places (pixel agents, event capture, artifact saving, turn summary). The Plan's `execution_model` must be a valid `ExecutionModel` enum value. The existing `if/elif` chain starting at line 2231 must continue to work unchanged.

**Also wire into `stream_rag_response`:** There's a second routing call at `chat_ui.py:2518` inside `stream_rag_response()`. Check whether this path also needs the Orchestrator. (It likely does — this is the non-streaming path used by the orchestrator's own steps.)

### Step 4: Update the Routing Comment

**File:** `src/aion/routing.py`

The comment at lines 36-40 explains why `inspect` is excluded from repo analysis:

```python
# inspect is excluded: it's for reviewing existing models, not running the
# extraction pipeline. See: misroute incident where Persona classified
# "Is this compliant with our principles?" as inspect+repo-analysis.
```

This gate stays. The `get_execution_model()` function is **not** changing. The Orchestrator overrides the routing **after** `get_execution_model()` returns, not inside it. Update the comment to reflect this:

```python
# inspect is excluded here: it's for reviewing existing models, not running the
# extraction pipeline. The Orchestrator (orchestrator.py) may upgrade
# inspect→repo_analysis when the query implies deep repo understanding
# (e.g., "review this repo" with a GitHub URL). This separation keeps
# routing pure and puts goal-reasoning in the Orchestrator.
```

### Step 5: Add Logging for Plan Decisions

**File:** `src/aion/orchestrator.py`

Every plan decision should be logged with structlog so we can debug misroutes:

```python
logger.info(
    "orchestrator_plan",
    intent=persona_result.intent,
    default_route=default_execution_model.value,
    planned_route=plan.execution_model.value,
    upgraded=plan.upgraded_from is not None,
    reason=plan.reason,
    has_github_url=has_github_url,
    has_repo_path=has_repo_path,
)
```

This is essential for debugging. When a misroute happens in production, the logs should show exactly what the Orchestrator decided and why.

### Step 6: Tests

**Required tests (non-negotiable):**

1. **Existing tests must pass.** Run the full test suite before making any changes. Run it again after. If anything breaks, fix it before proceeding.

2. **New unit tests for `plan()`:**
   - `intent=inspect` + GitHub URL + "review this repo" → `REPO_ANALYSIS`
   - `intent=inspect` + GitHub URL + "check this ArchiMate file" → stays `INSPECT`
   - `intent=generation` + `skill_tags=["repo-analysis"]` → `REPO_ANALYSIS` (existing behavior preserved)
   - `intent=inspect` + no URL → stays `INSPECT` (existing behavior preserved)
   - `intent=retrieval` + GitHub URL + "what does this repo do?" → `REPO_ANALYSIS`
   - `intent=retrieval` + no URL → stays `TREE` (existing behavior preserved)
   - `intent=generation` + no repo-analysis tag → stays `GENERATION` (existing behavior preserved)

3. **Integration test:**
   - Mock PersonaResult with `intent=inspect`, `github_refs=["org/repo"]`, `original_message="Review this repo https://github.com/org/repo"`
   - Verify the Orchestrator returns `Plan(execution_model=REPO_ANALYSIS)`
   - Verify downstream execution reaches `stream_repo_archimate_response` (not `stream_inspect_response`)

---

## 4. What NOT to Change

These are explicit boundaries. Do NOT touch these unless a test proves they're broken:

1. **Persona classification logic** (`persona.py`). The Persona's job is to classify intent. It's doing that correctly. The problem is downstream.

2. **`get_execution_model()` in `routing.py`**. This function stays as-is. It's the "default" route. The Orchestrator overrides it when needed, but doesn't replace it.

3. **The SKILL.md prompt** (`skills/persona-orchestrator/SKILL.md`). This is the LLM classification prompt. It correctly classifies "review this repo" as inspect. Don't change the classification rules to hack around the routing problem.

4. **`capability_gaps.py` and `capability_store.py`**. These are fine. They're the passive gap detection system. In a future phase, the Orchestrator could use them proactively, but not in this change.

5. **Agent internals** (`rag_agent.py`, `archimate_agent.py`, `repo_analysis_agent.py`). These agents work. Don't modify their tool registrations, system prompts, or query methods.

6. **The `stream_repo_archimate_response()` chain** (`chat_ui.py:1479`). This two-phase chain (repo analysis → ArchiMate generation) works correctly. The only change is that it gets called for more queries (when the Orchestrator upgrades inspect→repo_analysis).

---

## 5. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Orchestrator upgrades queries that shouldn't be upgraded (false positive) | `_implies_repo_understanding()` must be conservative. When in doubt, don't upgrade. Log every upgrade decision for monitoring. |
| Existing inspect path breaks (e.g., "describe the model you generated") | Orchestrator only upgrades when a repo URL/path is present AND the query implies repo understanding. No URL = no upgrade. |
| The `stream_rag_response` second routing path at line 2518 diverges | Check this path carefully. If it's used by the MultiStepOrchestrator's inner steps, it shouldn't need the planning layer (those steps are already planned). |
| Performance — added latency from Orchestrator | The `plan()` method is pure Python pattern matching. No LLM calls. No I/O. Sub-millisecond. |

---

## 6. Future Phases (Not in This Change)

For context only — don't implement these now:

1. **Proactive gap detection:** Before executing a plan, check the capability registry for each step. If a step requires a capability that doesn't exist, log it as a gap AND tell the user transparently.

2. **Magic fetch on the Orchestrator:** Move `request_data` from agent-level to Orchestrator-level. When the Orchestrator can't find a suitable pipeline for a goal, it calls `request_data` with what's needed. This surfaces integration priorities at the planning layer.

3. **Dynamic step planning:** Instead of just overriding the execution model, the Orchestrator decomposes complex goals into multiple pipeline calls (e.g., "review this repo and compare it to our principles" → repo_analysis + RAG retrieval + synthesis).

---

## 7. Checklist Before Submitting

- [ ] Read `orchestrator.py` in full — understand `MultiStepOrchestrator.run()`
- [ ] Read `routing.py` in full — understand `get_execution_model()`
- [ ] Read `chat_ui.py` lines 2030-2400 — understand the execution dispatch
- [ ] Read `chat_ui.py` lines 1088-1170 — understand `stream_inspect_response()`
- [ ] Read `chat_ui.py` lines 1479-1548 — understand `stream_repo_archimate_response()`
- [ ] Read `repo_analysis_agent.py` in full — understand the agent's tools and flow
- [ ] Read `repo_analysis.py:363-469` — understand `clone_repo()` URL parsing
- [ ] Run full test suite — confirm baseline passes
- [ ] Implement `Plan` dataclass
- [ ] Implement `plan()` method
- [ ] Implement `_implies_repo_understanding()` and `_contains_github_url()`
- [ ] Wire into `chat_ui.py` at line 2038
- [ ] Update routing.py comment
- [ ] Add structured logging
- [ ] Write unit tests for `plan()`
- [ ] Write integration test for the full flow
- [ ] Run full test suite — confirm nothing regresses
- [ ] Manual test: "Review this repo" + GitHub URL → verify deep analysis runs
- [ ] Manual test: "Describe the model you generated" → verify inspect still works
- [ ] Manual test: "Generate ArchiMate from https://github.com/..." → verify generation+repo still works
