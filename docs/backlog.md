# AInstein Backlog

Queued technical work items with context and rationale.

## High Priority

### Progressive Skill Loading
Replace `inject_mode: always/on_demand` with `load_when: {intents, tags}`
in the skill registry. The Persona already classifies intent and
skill_tags — these signals should drive skill loading. Currently all
"always-inject" skills load on every query regardless of relevance,
adding ~25K chars of unnecessary context. Estimated 40-80% token
reduction per query across all execution paths.

## Medium Priority

### Diff-Based Refinement
Replace full-model regeneration with a structured delta approach. The
LLM returns a refinement envelope (`<add>`, `<modify>`, `<remove>`
sections) instead of the complete modified model. The pipeline applies
the delta mechanically. Benefits: ~80% token reduction on refinement,
elimination of element loss risk, faster execution.

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

### Policy/Regulation Compliance Skill
The current system lacks a skill to check the development to-dos for
newly identified features during the technical discovery process or to
verify (at scheduled regular times; cyclic) existing solution
implementations still comply with the updated policies and regulations
(captured in the solution knowledge base).

## Completed

### Sanitize XML on Every Validation Retry
`_sanitize_xml()` now runs before each validation retry attempt,
catching mechanical XML issues (bare `&`, encoding problems) before
falling back to an LLM retry call.

### Generation Pipeline Summary Log Line
The COMPLETE log line now includes actual prompt and completion token
counts (accumulated across main call, view repair, and retries) and
artifact filename. Token counts are sourced from provider responses
(OpenAI usage object, Ollama eval counts).