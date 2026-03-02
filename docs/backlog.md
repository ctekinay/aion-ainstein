# AInstein Backlog

Queued technical work items with context and rationale.

## High Priority

n/a

## Medium Priority

### Diff-Based Refinement
Replace full-model regeneration with a structured delta approach. The
LLM sees the full model for context but returns only a YAML diff. A
deterministic merge engine applies the diff mechanically.

**Format:** Pure YAML envelope (no XML-inside-YAML mixing):
```yaml
refinement:
  add:
    elements:
      - id: t1
        type: Node
        name: "API Gateway Runtime"
    relationships:
      - type: Serving
        source: t1
        target: a8
  modify:
    a1:
      name: "Authorization Server (OAuth2) + OpenID Provider"
  remove:
    elements: [a99]
```

**Merge engine policy:**
- `add` — append elements/relationships to existing YAML
- `modify` — find element by ID, patch specified fields
- `remove` — cascade-with-warning: remove element, remove all
  dangling relationships (where element is source or target),
  include cleanup note in response to user

**Files to modify:** `generation.py` (refinement prompt + merge
function), possibly `tools/archimate.py` (merge engine).

**Validation:** existing pipeline (YAML→XML, schema check, view
repair) runs on the merged result. Fallback: if diff parsing fails,
fall back to full-regeneration (current behavior).

**Before implementing:** run one refinement both ways on the same
model and measure actual token reduction. The YAML pivot already cut
full-regeneration from ~34K to ~9K tokens — measure the real delta
before claiming a percentage.

### Dynamic Model Catalog
Populate the settings dropdown by querying the provider's model list
at runtime (OpenAI `/v1/models`, Ollama `/api/tags`). Prevents invalid model name errors that currently cause silent degradation.

## Low Priority
n/a

## No Priority Assigned (requires a technical discovery session)

### Cross-Conversation Memory and User Preferences
The system currently has no memory beyond a single conversation.
Each conversation is isolated — prior queries, generated artifacts,
and user preferences are not carried forward. Potential capabilities:
cross-conversation context (recall previous generations and refinements),
user preference learning (preferred detail levels, recurring topics,
default generation parameters), and session-to-session knowledge
accumulation. Requires discovery to determine scope, storage mechanism
(extend SQLite store vs. dedicated memory collection in Weaviate),
privacy boundaries, and interaction with the Persona's intent
classification.

---

### Policy/Regulation Compliance Skill
The current system lacks a skill to check the development to-dos for
newly identified features during the technical discovery process or to
verify (at scheduled regular times; cyclic) existing solution
implementations still comply with the updated policies and regulations
(captured in the solution knowledge base).

---

### Chat navigation interrupts active generation

When a user switches to a new chat or opens Settings while AInstein is processing a query, the generation pipeline either halts entirely or the thinking indicator disappears while the backend continues running. Both outcomes cause confusion — the user assumes the process has stopped and may re-submit the query, triggering duplicate work.

**To investigate:**
- Does navigating away cancel the backend task (WebSocket disconnect → task abort), or does it only unmount the frontend thinking indicator?
- If the backend continues, the response is generated but never delivered to the UI — wasted tokens.
- If the backend aborts, the abort should be clean (no partial artifacts saved, no orphaned status messages).

**Expected behavior:** Either persist the generation and surface the result when the user returns to the chat, or cancel cleanly with a visible status ("Generation cancelled — you navigated away").

---

### Thinking traces not persisted across chat sessions

When the user starts a new chat, the thinking traces (retrieval steps, intent classification, source citations) from previous chats are cleared from the UI. Toggling "Show AInstein's thinking" on/off does not restore them — the trace data is only held in frontend state and is not persisted to the conversation history.

**To investigate:**
- Are thinking traces stored in the messages table or only in ephemeral frontend state?
- If ephemeral: add a `thinking_trace` field to the message model and persist it alongside the response.
- If stored but not loaded: the chat hydration query may be filtering them out.

**Expected behavior:** Thinking traces are part of the conversation record. Returning to an old chat and enabling "Show thinking" should display the original traces for each response.

## Completed

### Progressive Skill Loading
Implemented via `inject_mode: on_demand` with `tags` in the skill
registry. The Persona emits `skill_tags` on every classification;
`get_skill_content(active_tags=...)` only includes on-demand skills
when their tags match. ArchiMate and SKOSMOS skills load only when
relevant. Always-inject skills (identity, QA, ontology, formatter)
remain on every query as they apply universally.

### Alliander GitHub MCP Integration
Implemented MCP client framework (`src/aion/mcp/`) with GitHub file
fetching via the GitHub Copilot MCP server. The inspect pipeline
fetches ArchiMate models from GitHub URLs, converts to YAML, and
streams LLM analysis. Supports both `github.com` blob URLs and
`raw.githubusercontent.com` URLs.

### Sanitize XML on Every Validation Retry
`_sanitize_xml()` now runs before each validation retry attempt,
catching mechanical XML issues (bare `&`, encoding problems) before
falling back to an LLM retry call.

### Generation Pipeline Summary Log Line
The COMPLETE log line now includes actual prompt and completion token
counts (accumulated across main call, view repair, and retries) and
artifact filename. Token counts are sourced from provider responses
(OpenAI usage object, Ollama eval counts).