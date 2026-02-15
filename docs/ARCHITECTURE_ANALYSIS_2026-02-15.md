# AInstein RAG Pipeline: Architecture Analysis and Recommended Path Forward

**Date:** 2026-02-15
**Context:** Analysis of Gold Standard v3/v4 evaluation failures (34.5% accuracy with gpt-5.2 + text-embedding-3-large)
**Audience:** Development team

---

## 1. Executive Summary

The system's evaluation failures are not LLM comprehension failures. They are **system-induced behaviors** caused by a pipeline that bypasses LLM reasoning for a significant class of queries. The evidence shows deterministic list dumps where the LLM never gets the chance to synthesize an answer.

The fix is not more routing, regex, or short-circuits. The fix is architectural: **give the LLM the domain knowledge it needs to reason about ESA documents, then remove the legacy mechanisms that prevent it from doing so.**

---

## 2. The Problem: Evidence from Gold Standard v4

### 2.1 The "List Dump" Pattern

When a user asks `"Which ADR chose the authentication and authorization standard? Answer with the ADR id only"` (test R2), the expected response is `ADR.0029`. The actual response is a bullet list of all 18 ADR IDs (ADR.0000 through ADR.0031).

This is not an LLM misunderstanding. An LLM that doesn't understand "ID only" would produce:
- A sentence with one ID
- A wrong ID
- "I can't determine this"

What we see is a **deterministic dump of all retrieved results** in a fixed format. This is a system behavior, not an LLM behavior.

### 2.2 The "Clarification" Pattern

When a user asks `"What is a Business Actor in ArchiMate?"` (test V6), the system returns `"I'm not sure what you're looking for. Could you clarify?"` — even though "Business Actor" exists in the vocabulary collection with 5,608 terms.

The LLM never saw the vocabulary data. The intent classifier returned low confidence, and the system short-circuited to a clarification prompt before any retrieval occurred.

### 2.3 The "Wrong Collection" Pattern

When a user asks `"Why was CIM chosen as the default domain language?"` (test A3), the system searches vocabulary for "CIM" and finds term definitions — but the answer is in ADR.0012's `decision` field. The system doesn't know that "chosen as" implies an architecture decision, not a vocabulary definition.

---

## 3. Root Cause Analysis: Three System Artifacts

### 3.1 Artifact 1: `_direct_query` Keyword Routing Forces List Mode

**File:** `src/elysia_agents.py`, lines 2706-2755

When the Elysia Tree times out or fails, the system falls back to `_direct_query()`. This method contains hard-coded keyword matching:

```python
elif re.search(r"\badrs?\b", question_lower):
    list_tool = self._tool_registry.get("list_all_adrs")
    # ... calls list_all_adrs() and returns deterministic list
```

**ANY question containing the word "adr"** that hits this fallback path gets force-routed to `list_all_adrs()`. This includes:
- "Which ADR chose OAuth?" → lists all ADRs (should search ADR content)
- "Tell me about ADR.0025" → lists all ADRs (should fetch specific doc)
- "Why was CIM chosen as the default domain language?" → hits semantic path, but if "adr" appears in any follow-up context, it lists

The same pattern applies to "principle" → `list_all_principles()` and "policy" → `list_all_policies()`.

**This is the most likely source of the list dump behavior.** It was designed as a safety net for Tree failures but it intercepts semantic queries indiscriminately.

### 3.2 Artifact 2: `LIST_RESULT_MARKER` Bypasses LLM Synthesis

**File:** `src/list_response_builder.py`, lines 140-169

When any tool returns a dict with `{"__list_result__": True, ...}`, the response gateway intercepts it and produces a deterministic bullet list. The LLM never sees the data and never gets to synthesize an answer.

The flow:
1. Tool (e.g., `list_all_adrs()`) returns `build_list_result_marker(rows=...)`
2. `is_list_result()` detects the marker
3. `handle_list_result()` in `response_gateway.py` calls `finalize_list_result()`
4. A deterministic bullet list is produced and returned as the final response
5. **No LLM involved at any point in steps 2-4**

This is correct for explicit list requests ("List all ADRs"). It is incorrect when:
- The Tree accidentally picks a list tool for a semantic question
- The `_direct_query` keyword routing forces a list tool for a non-list query

### 3.3 Artifact 3: The Tree Has No Domain Knowledge for Tool Selection

**File:** `src/elysia_agents.py`, lines 1183-1196

The Elysia Tree's LLM receives this as its base description:

```
You are AInstein, the Energy System Architecture AI Assistant at Alliander.
Your role is to help architects, engineers, and stakeholders navigate...
IMPORTANT GUIDELINES:
- When referencing ADRs, use the format ADR.XX
- When referencing Principles, use the format PCP.XX
- Be transparent about the data
- Never hallucinate
```

Plus the registered tools with their docstrings:

```
search_architecture_decisions(query, limit=5)
    "Search ADRs for design decisions. Use when the user asks about
     architecture decisions and their rationale..."

list_all_adrs()
    "List all ADRs in the system. Use when the user asks:
     - What ADRs exist?
     - List all architecture decisions..."
```

The Tree's LLM must decide, based on these descriptions alone, whether to call `search_architecture_decisions("authentication standard")` or `list_all_adrs()` for the query "Which ADR chose the authentication standard?"

Without understanding what an ADR's `decision` field contains, or that "which X does Y" means "search for Y in X's content," the LLM defaults to the safest interpretation: show the user all ADRs and let them find it.

---

## 4. Why Current Fixes Don't Work

### 4.1 The "Add More Routes" Approach

Adding regex patterns to detect specific query types and short-circuit to the right tool is the approach taken historically. The routing policy now has:

- `_DOC_REF_RE` for document IDs
- `_APPROVAL_RE` for approval queries
- `_LIST_VERBS_RE` for list queries
- `_META_RE` for meta queries
- `_VOCAB_RE` for vocabulary queries
- `_COMPARE_RE` for comparison queries
- And many more...

**Problem:** This creates a parallel decision system that competes with the LLM. Every new regex pattern is a band-aid that:
1. Handles the specific phrasing tested, but not variations
2. Adds complexity that makes the system harder to debug
3. Masks the underlying issue: the LLM doesn't understand the domain

### 4.2 The "Add More Short-Circuits" Approach

The recent `_handle_lookup_doc()`, `_handle_lookup_approval()`, and `_handle_list()` methods bypass the Tree entirely for detected intents. This works for queries with explicit document IDs (e.g., "Tell me about ADR.0025") but fails for:
- "Which ADR chose the authentication standard?" (no ID in query)
- "What principle addresses data reliability?" (no ID in query)
- "How do the architecture decisions support governance?" (cross-domain, no ID)

These are the queries that actually need LLM reasoning, and the short-circuits don't apply to them.

---

## 5. The Structural Solution: Domain Comprehension Skills

### 5.1 The Human Analogy

When a human receives the query "Tell me about ADR.0025":

1. **Parse the action**: "tell me about" = provide information / summarize
2. **Parse the subject**: "ADR.0025" — but what IS an ADR? What is 0025?
3. **Learn the domain**: Consult the ESA documentation to understand ADRs have a title, status, context, decision, and consequences. Understand that ADR.0025 is identified by `adr_number="ADR.0025"` in the knowledge base.
4. **Execute the action**: Now that they know WHERE to look and WHAT to look for, fetch ADR.0025 and provide a summary of its content.

The system currently skips steps 2 and 3. It goes directly from "I see ADR.0025" to "call a Weaviate tool." This is why it makes wrong tool selections — it's guessing without understanding.

### 5.2 What Already Exists: `esa-document-ontology` Skill

The system already has an `esa-document-ontology` skill (`skills/esa-document-ontology/SKILL.md`) that contains excellent domain knowledge: document types, ID formats, numbering overlaps, disambiguation rules, owner groups, frontmatter schemas. This is 177 lines of structured domain knowledge.

**Current activation rules (from `skills/registry.yaml`):**
```yaml
- name: esa-document-ontology
  auto_activate: true
  triggers:
    - "adr"
    - "pcp"
    - "dar"
    - "principle"
    - "decision"
    - "approval"
    - "0010"
    - "0012"
    - "0022"
    - "0025"
```

**The issue:** `auto_activate: true` means it's always included, but the trigger list only covers specific document IDs. More importantly, this skill teaches the LLM what documents ARE, but not HOW TO REASON about queries.

The skill says "An ADR captures an important architecture decision along with its context, considered options, and consequences" — but it doesn't say "When someone asks 'Which ADR chose X?', search the `decision` field of ADRs for X and return the matching ADR ID."

### 5.3 What's Missing: Query Reasoning Skill

The system needs a second domain skill that teaches the LLM how to MAP user intent to system actions. This is the "training" step — the equivalent of showing the new employee what to do with each type of question.

This skill would contain:
- Action vocabulary: "tell me about" = summarize, "which X does Y" = search and identify, "who approved" = fetch DAR
- Subject identification: how to determine which collection to search
- Tool selection guidance: when to use `search_` vs `list_` tools
- Response guidance: "summarize" means synthesize content, not dump a list

### 5.4 What's Missing: Runtime Corpus Knowledge

The `esa-document-ontology` skill has a static inventory ("ADRs: ADR.00-ADR.02, ADR.10-ADR.12, ADR.20-ADR.31"). This is helpful but:
- It becomes stale when documents are added
- It doesn't include titles (needed for disambiguation)
- It can't validate whether a referenced doc exists

A runtime manifest (loaded from Weaviate at startup, cached in memory) would provide instant existence validation and enable the LLM to answer "Does ADR.0050 exist?" without any retrieval.

---

## 6. The Four Skills Model

### Skill 1: `esa-document-ontology` (EXISTS — needs minor expansion)

**Purpose:** What the documents ARE.
**Content:** Document types, ID formats, properties, relationships, numbering, disambiguation.
**Status:** Already implemented and comprehensive. Needs expansion for:
- Explicit field-level descriptions (ADR has `context`, `decision`, `consequences` fields)
- Vocabulary coverage scope (ArchiMate, CIM, IEC standards)
- Policy document categories (governance, capability)

### Skill 2: `esa-query-reasoning` (NEW)

**Purpose:** How to REASON about queries.
**Content:**
```markdown
## Action Mapping

| User Intent Pattern | Action | Tool Selection |
|---|---|---|
| "Tell me about [DOC_ID]" | Summarize document content | Fetch specific doc by ID, synthesize |
| "What does [DOC_ID] decide?" | Extract decision field | Fetch specific doc, focus on decision |
| "Who approved [DOC_ID]?" | Extract approval info | Fetch DAR for that doc ID |
| "Which [TYPE] does/chose [TOPIC]?" | Search and identify | Search TYPE collection for TOPIC, return match(es) |
| "What [TYPE] addresses [TOPIC]?" | Search and identify | Search TYPE collection for TOPIC |
| "List all [TYPE]" | Enumerate | List all docs of TYPE |
| "What is [TERM]?" | Define | Search vocabulary for TERM definition |
| "How do [TYPE_A] support [TYPE_B]?" | Cross-domain analysis | Search both collections, synthesize relationships |

## Tool Selection Rules

1. **search_* tools**: Use when the query asks about CONTENT (topics, decisions, rationale)
2. **list_* tools**: Use ONLY when the query explicitly asks "what exists" / "list" / "enumerate"
3. **Never** use list tools to answer content questions
4. **Never** dump all documents when the user asks about a specific topic

## Response Rules

1. "Summarize" = read the document fields and produce a synthesis
2. "Which X does Y" = find the specific match(es) and return their IDs with brief context
3. "Answer with ID only" = return only the document ID(s), no list of all documents
```

### Skill 3: `esa-corpus-manifest` (NEW — dynamic, cached at startup)

**Purpose:** What currently EXISTS in the knowledge base.
**Content:** Populated from Weaviate at startup:
```markdown
## Current Corpus

ADRs: 18 documents
  IDs: ADR.0000, ADR.0001, ADR.0002, ADR.0010, ADR.0011, ADR.0012,
       ADR.0020-ADR.0031

PCPs: 31 documents
  IDs: PCP.0010-PCP.0040

DARs: 49 records (18 ADR approvals + 31 PCP approvals)

Policies: 5 documents

Vocabulary: 5,608 terms (IEC/CIM/ArchiMate)

If a document ID is not in this list, it does not exist in the knowledge base.
```

### Skill 4: Existing skills (rag-quality-assurance, response-formatter, response-contract)

**Purpose:** Output quality and formatting.
**Status:** Already implemented. No changes needed, but their interaction with the domain skills needs verification (see Section 8).

---

## 7. What Must Be Removed (After Domain Skills Are Proven)

### 7.1 Remove Keyword Routing in `_direct_query`

**File:** `src/elysia_agents.py`, lines 2706-2755

The `elif re.search(r"\badrs?\b", question_lower): list_tool = ...` blocks must be replaced with a proper decision: if the intent is LIST, use the list tool; if the intent is SEMANTIC, proceed to semantic search. The intent should come from the LLM's understanding (informed by domain skills), not from keyword matching.

**Guard:** Before removal, verify with traceability (Section 8) that the domain-aware LLM makes correct tool selections.

### 7.2 Guard `LIST_RESULT_MARKER` Against Semantic Intent

**File:** `src/response_gateway.py`, `handle_list_result()`

Currently: if the output has the marker, produce a deterministic list regardless of the original query intent.

Should be: if the original query intent is SEMANTIC_ANSWER (not LIST), and the tool output has the marker, do NOT produce a deterministic list. Instead, feed the list data as context to the LLM and let it synthesize an answer.

This handles the case where the Tree accidentally picks a list tool for a semantic question — the LLM still gets a chance to reason about the data instead of dumping it.

### 7.3 Review `response-formatter` Skill Triggers

**Current triggers:** `"list"`, `"what"`, `"which"`, `"how many"`, `"show all"`, `"enumerate"`, `"summarize"`

The trigger `"what"` causes this skill to activate for virtually every question ("What is a Business Actor?", "What does ADR.0025 decide?", "What principle addresses data reliability?"). This skill instructs the LLM to use "Numbered lists for sequential items" and "Statistics section with counts" — which biases the LLM toward list-format responses even for non-list questions.

The trigger `"which"` similarly activates for "Which ADR chose OAuth?" — a question that should return a single ID, not a formatted list.

**Recommendation:** Narrow the triggers to only activate for actual list queries, or split the skill into list-formatting (narrow trigger) and general-formatting (broad trigger) variants.

---

## 8. Traceability: What to Instrument

Before removing artifacts, add traceability to verify where the list behavior originates for each test case.

### Required Fields in Test Output

```json
{
  "id": "R2",
  "question": "Which ADR chose the authentication standard? Answer with the ADR id only.",

  "pipeline_trace": {
    "intent_router": {
      "intent": "semantic_answer",
      "entity_scope": "adr",
      "confidence": 0.72,
      "mode": "llm",
      "heuristic_override": false
    },
    "route_taken": "tree",
    "tree_tools_called": [
      {"tool": "list_all_adrs", "marker": "LIST_RESULT_MARKER", "rows_returned": 18}
    ],
    "tree_timed_out": false,
    "direct_query_fallback": false,
    "direct_query_keyword_match": null,
    "skills_active": ["rag-quality-assurance", "response-formatter", "esa-document-ontology"],
    "skills_matched_triggers": {"response-formatter": ["which"], "esa-document-ontology": ["adr"]},
    "list_marker_triggered": true,
    "list_marker_source": "tree_tool_output",
    "raw_tree_output": "{\"__list_result__\": true, \"collection\": \"adr\", \"rows\": [...], ...}",
    "final_output": "- ADR.0000 - ADR.00: Use Markdown Architectural Decision Records (accepted)\n- ADR.0001 - ..."
  }
}
```

### What This Tells You

For each failing test case, the trace answers:
1. **Did the intent router classify correctly?** (intent + confidence)
2. **Which route was taken?** (tree / short-circuit / direct_query fallback)
3. **Which tools did the Tree call?** (the critical question)
4. **Was the LIST_RESULT_MARKER triggered?** (and by which tool)
5. **Which skills were active?** (and which triggers matched)
6. **What did the Tree's LLM output before any post-processing?** (raw_tree_output)
7. **What ended up in the final response?** (final_output)

If `raw_tree_output` is already a list marker but `final_output` is the bullet list → the Tree picked the wrong tool, the marker bypassed synthesis.
If `raw_tree_output` is a good answer but `final_output` is different → the formatter/post-processor changed it.
If `direct_query_fallback` is true → the Tree timed out and the keyword routing took over.

---

## 9. Implementation Plan

### Phase 1: Domain Skills (Highest Impact)

| Step | What | Files | Impact |
|------|------|-------|--------|
| 1a | Expand `esa-document-ontology` with field-level property descriptions | `skills/esa-document-ontology/SKILL.md` | Tree understands ADR fields |
| 1b | Create `esa-query-reasoning` skill with action→tool mapping | `skills/esa-query-reasoning/SKILL.md` + `skills/registry.yaml` | Tree selects correct tools |
| 1c | Verify both skills are injected into Tree agent description | Check `get_all_skill_content()` output | Skills reach the LLM |

### Phase 2: Traceability (Enables Verification)

| Step | What | Files | Impact |
|------|------|-------|--------|
| 2a | Add `pipeline_trace` dict to test runner output | `src/evaluation/test_runner.py` | See where behavior originates |
| 2b | Log `tools_called` from Tree execution | `src/elysia_agents.py` | See which tools Tree picks |
| 2c | Log `skills_active` and `matched_triggers` per query | `src/skills/registry.py` | See which skills influence the LLM |

### Phase 3: Artifact Removal (After Verification)

| Step | What | Files | Impact |
|------|------|-------|--------|
| 3a | Replace keyword routing in `_direct_query` with intent-aware routing | `src/elysia_agents.py:2706-2755` | No more force-list for semantic queries |
| 3b | Add intent guard on `LIST_RESULT_MARKER` | `src/response_gateway.py` | Accidental list tools don't kill synthesis |
| 3c | Narrow `response-formatter` triggers | `skills/registry.yaml` | Stop bias toward list format |

### Phase 4: Runtime Knowledge

| Step | What | Files | Impact |
|------|------|-------|--------|
| 4a | Create `esa-corpus-manifest` with startup population | New skill + `src/skills/manifest.py` | Instant existence validation |
| 4b | Add session memory for follow-up context | Extend `followup_binding` | Build understanding within session |

### Phase 5: Cleanup

| Step | What | Files | Impact |
|------|------|-------|--------|
| 5a | Remove regex-based intent classification if domain skills prove sufficient | `src/intent_router.py` | Simplify pipeline |
| 5b | Remove short-circuit handlers if Tree makes correct decisions | `src/elysia_agents.py` | Simplify pipeline |
| 5c | Consolidate duplicate base agent descriptions | `src/elysia_agents.py` + `src/llm_client.py` | Single source of truth |

---

## 10. Success Criteria

The changes are successful when:

1. **Gold Standard accuracy ≥ 75%** without any new regex patterns or short-circuits
2. **Route accuracy ≥ 90%** — the LLM, informed by domain skills, selects the correct tool
3. **Zero "list dump" failures** — no deterministic list output for semantic/lookup queries
4. **Zero "clarification" failures** — domain-relevant questions always proceed to retrieval
5. **Traceability shows** the LLM is making decisions, not being bypassed by system artifacts

---

## 11. Appendix: Current Skill Injection Flow

```
User Query
    ↓
[1] Skill Registry: get_active_skills(query)
    ├─ rag-quality-assurance (auto_activate=true) → ALWAYS ACTIVE
    ├─ response-formatter (auto_activate=true) → ALWAYS ACTIVE
    ├─ response-contract (auto_activate=false) → active if triggers match
    └─ esa-document-ontology (auto_activate=true) → ALWAYS ACTIVE

[2] get_all_skill_content(query)
    └─ Concatenates all active skills' SKILL.md content with "---" separator

[3] Agent Description = _base_agent_description + skill_content + scope_hints

[4] Tree = create_tree(agent_description)
    └─ Tree's LLM sees: base identity + skill content + scope hints + tool docstrings

[5] Tree calls tools and generates response
    ├─ If tool returns LIST_RESULT_MARKER → deterministic list (LLM bypassed)
    └─ If tool returns search results → LLM synthesizes answer

[6] Post-processing: postprocess_llm_output()
    ├─ If structured_mode → enforce JSON contract
    └─ If not → pass through
```

**The gap:** Skills 1-4 teach the LLM about output formatting and quality. Only `esa-document-ontology` teaches about the domain, and it doesn't teach query reasoning. The LLM gets instructions about HOW TO FORMAT but not HOW TO THINK ABOUT ESA QUERIES.

---

## 12. Appendix: `_direct_query` Keyword Routing (Full Code)

For reference, this is the exact code that forces list mode based on keywords. Lines 2706-2755 in `src/elysia_agents.py`:

```python
_DAR_RE_FALLBACK = re.compile(r"\bdars?\b|decision approval record", re.IGNORECASE)
if _DAR_RE_FALLBACK.search(question_lower):
    list_tool = self._tool_registry.get("list_approval_records")
    if list_tool:
        logger.info("_direct_query: re-routing DAR query to deterministic list tool")
        if "principle" in question_lower:
            list_result = await list_tool("principle")
        elif "adr" in question_lower:
            list_result = await list_tool("adr")
        else:
            list_result = await list_tool("all")
        if list_result and is_list_result(list_result):
            context = create_context_from_skills(question, _skill_registry)
            gateway_result = handle_list_result(list_result, context)
            if gateway_result:
                return gateway_result.response, objects

elif re.search(r"\badrs?\b", question_lower):
    list_tool = self._tool_registry.get("list_all_adrs")
    # ... forces list_all_adrs() for ANY query containing "adr"

elif re.search(r"\bprinciples?\b", question_lower):
    list_tool = self._tool_registry.get("list_all_principles")
    # ... forces list_all_principles() for ANY query containing "principle"

elif re.search(r"\bpolic(?:y|ies)\b", question_lower):
    list_tool = self._tool_registry.get("list_all_policies")
    # ... forces list_all_policies() for ANY query containing "policy"
```

Every semantic question about ADRs, principles, or policies that hits this path becomes a list dump.

---

## 13. Appendix: `response-formatter` Trigger Overlap

The `response-formatter` skill (auto_activate=true) has these triggers:
```yaml
triggers:
  - "list"
  - "what"      # ← matches virtually every question
  - "which"     # ← matches "Which ADR chose OAuth?"
  - "how many"
  - "show all"
  - "enumerate"
  - "summarize"
```

This skill instructs the LLM:
```
For ANY response that lists multiple items:
- Use numbered lists (1., 2., 3.) for sequential or ranked items
- Include a statistics summary at the END
- Include follow-up options
- Include visualization suggestions
```

Combined with the `"what"` and `"which"` triggers, this means nearly every query activates formatting instructions that bias toward list output. A question like "What principle addresses data reliability?" (test P3) activates `response-formatter` via the "what" trigger, which tells the LLM to produce numbered lists with statistics — exactly the behavior we observe in the failing tests.
