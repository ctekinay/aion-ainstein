# AInstein Development Instructions

**For: Coding agents and developers working on the AInstein codebase**
**Version:** 1.1 — February 20, 2026
**Authority:** These instructions are derived from architectural decisions made during the main branch's 297-commit development cycle and the artifacts branch rebuild. They represent hard-won lessons — not theoretical preferences. Audited against the codebase by the lead dev on February 20, 2026.

---

## 1. Core Principles

### The LLM is the router
All intent classification, scope gating, query reformulation, and routing decisions are made by the LLM via prompts. Never use keyword matching, regex patterns, or hardcoded trigger lists. The main branch built 10 keyword-triggered deterministic routes and deleted all of them (commit 265: -600 lines). If you're writing an `if "list" in query.lower():` branch, you're on the wrong path.

### Skills are declarative prompt content
The Skills Framework injects rules into the LLM context via atlas injection. Behavioral changes (formatting rules, scope gating, identity) should be achieved by editing SKILL.md files, not by writing Python code. If a behavior can be changed by editing a prompt, it must not be hardcoded in code.

### Thin layers, not frameworks
Every **new** component should be a single file, 150–300 lines, with one class and one primary method. If a new implementation exceeds 500 lines or requires more than 2 new files, it is over-engineered. AInstein is a thin orchestration layer on top of Elysia, not a framework.

**Known exceptions:** `elysia_agents.py` (~1,400 lines) contains all Elysia tools, fallback handlers, and direct query logic in one file because splitting it would break Elysia's closure-based tool registration. `chat_ui.py` (~1,400 lines) contains the full FastAPI server, SSE streaming, conversation store, and test mode. These are legacy monoliths — do not add to them without good reason, and do not use their size as justification for new large files.

### The Elysia Tree is the RAG engine
The Persona classifies intent and routes. The Tree selects tools and executes search. These responsibilities must not overlap. The Persona decides WHETHER to use the Tree, not HOW the Tree executes. Never duplicate tool selection logic outside the Tree.

---

## 2. What NOT To Do

These are absolute prohibitions. Every one of them was tried in the main branch, caused problems, and was deleted.

### No keyword-based routing
```python
# ❌ NEVER DO THIS
if "list" in query.lower() or "what exists" in query.lower():
    return handle_list_query(query)
if "compare" in query.lower():
    return handle_compare_query(query)
```
Use the LLM for all routing decisions. Tool docstrings guide the Tree's tool selection.

**Known exception:** `_direct_query()` (the uvloop fallback path, lines ~961-1074) uses 6 keyword-matching blocks to route queries when the Elysia Tree is unavailable. This is a degraded-mode fallback that only activates when the Tree fails entirely. It violates this rule but is documented and accepted as a last-resort path. Do not extend it or use it as a pattern for new code.

### No regex soup
```python
# ❌ NEVER DO THIS
match = re.match(r'^(what|which|how many)\s+(adrs?|principles?|pcps?)', query, re.I)
if match:
    doc_type = match.group(2)
```
If you're writing a regex to detect intent, parse LLM output, or classify queries, stop. Use structured LLM output with simple string operations (`.split()`, `.strip()`, `.startswith()`).

**Known violation — pragmatic exception:** `search_principles` and `search_architecture_decisions` use `re.findall` to extract PCP/ADR numbers from queries and apply Weaviate filters. This is *data extraction* (parsing structured identifiers like "PCP.10" from a query string), not *intent detection* or *routing* — it's closer to parsing than classification. The `findall` approach handles both range expressions ("PCP.10 through PCP.18") and Tree-expanded lists ("PCP.10 PCP.11 PCP.12 ...") by deriving a min/max range from all found numbers.

**Caveat:** min/max range means "Compare PCP.10 and PCP.35" fetches all 26 PCPs in between, not just the two. The LLM focuses on the mentioned documents; extra data is noise but not harmful.

**Still pending:** natural language references ("the first few principles") are not handled by regex. These should be resolved by the Persona rewriting the query with explicit identifiers, or by letting the Tree select the list tool and the LLM handle filtering in summarization.

### No response gateways or JSON contracts
```python
# ❌ NEVER DO THIS
schema = {"intent": str, "confidence": float, "entities": list}
response = llm.generate(f"Respond in this JSON schema: {schema}")
parsed = json.loads(response)  # Brittle — will break
```
The LLM responds in natural language or simple structured text (e.g., "Line 1 = intent, Lines 2+ = content"). Formatting is guided by Skills, not enforced by code schemas.

### No client abstraction layers
```python
# ❌ NEVER DO THIS
class ResilientLLMClient:
    class DirectLLMClient:
        class ElysiaClient:
```
Use the LLM provider directly — Ollama HTTP API or OpenAI SDK. No wrapper hierarchies.

### No hardcoded return properties
```python
# ❌ NEVER DO THIS
return_properties=["title", "status", "content"]  # What about owner_team? file_path?
```
Use dynamic property discovery from the collection schema. Hardcoded property lists cause retry loops when the Tree asks for data that isn't in the response. Exclude only known large/internal fields (`full_text`, `content_hash`), return everything else.

### No formatting logic in the agent layer
```python
# ❌ NEVER DO THIS (in elysia_agents.py)
def _apply_bold_formatting(text):
    return re.sub(r'(ADR\.\d+)', r'**\1**', text)
```
The agent layer (`elysia_agents.py`) handles retrieval and routing. The presentation layer (`index.html`) handles formatting. If the model doesn't produce `**bold**` markers, that's a model capability issue — don't add regex post-processing to compensate.

### No stdout parsing
```python
# ❌ NEVER DO THIS
captured = capture_stdout(tree.run(query))
parsed = parse_ansi_output(captured)  # Fragile
```
Use `tree.async_run()` to iterate typed result dicts directly. The `OutputCapture` class was deleted for this reason (commit `e21c576`, -321 lines).

---

## 3. Architecture Rules

### Layer separation
```
User → Persona (intent classification, query rewriting) → Elysia Tree (tool selection, KB search) → Weaviate
```
Each layer has a single responsibility. Do not leak responsibilities across layers.

### Configuration over code
- **Retrieval limits** → `thresholds.yaml` (read via `_get_retrieval_limits()`)
- **Content truncation** → `thresholds.yaml` (read via `_get_truncation()`)
- **Distance thresholds** → `thresholds.yaml` (read via `_get_distance_threshold()`)
- **Persona system prompt** → `skills/persona-orchestrator/SKILL.md`
- **Response formatting** → `skills/response-formatter/SKILL.md`
- **Scope gating** → `skills/rag-quality-assurance/SKILL.md`
- **Recursion limit** → code (`tree_data.recursion_limit = 4`), documented with justification

If a value can change based on tuning, it belongs in config, not in code.

### Read config at call time, not registration time
```python
# ✅ CORRECT — reads config on every query, changes take effect without restart
async def search_principles(query: str, limit: int = 10):
    limit = _get_retrieval_limits().get("principle", limit)

# ❌ WRONG — reads config once at startup, changes require restart
DEFAULT_LIMIT = _get_retrieval_limits().get("principle", 6)
async def search_principles(query: str, limit: int = DEFAULT_LIMIT):
```

### Dynamic property discovery
Search tools should return all available metadata, not a hardcoded subset. Hardcoded property lists cause retry loops when the Tree asks for data that isn't in the response (e.g., the 5× `search_principles` loop when `status` was missing).

The principle: Weaviate's hybrid search returns all properties by default. For `fetch_objects` calls (listing tools), specify all properties except known large/internal fields. Apply `content_max_chars` truncation only to the `content` field — everything else is small metadata.

```python
# ✅ CORRECT — exclude only large/internal fields, return everything else
excluded = {"full_text", "content_hash"}
return_props = [p.name for p in collection.config.get().properties if p.name not in excluded]

# ❌ WRONG — hardcoded list that misses properties and causes retry loops
return_properties=["title", "content", "status"]
```
Cache the schema lookup per collection to avoid repeated Weaviate API calls.

### Deduplication for chunked data
Documents are stored as multiple chunks (Statement, Rationale, Implications, Approval Records). Listing tools must deduplicate by document ID (`principle_number`, `file_path`) and return one entry per document.

```python
# ✅ CORRECT — deduplicate and filter
seen = {}
for obj in results.objects:
    doc_id = obj.properties.get("principle_number", "")
    title = obj.properties.get("title", "")
    if not doc_id or doc_id in seen:
        continue
    if title.startswith("Principle Approval Record"):
        continue
    seen[doc_id] = {...}
```

### DAR/template filtering
Decision Approval Records (DARs), templates, and index pages must be filtered from listing and generic search results. Filter by `doc_type` where reliable (`adr_approval`, `template`, `index`). Use title-based filtering as fallback where `doc_type` is unreliable (Principle collection tags DARs as `doc_type: 'principle'`).

---

## 4. Elysia Tree Integration

### Recursion limit
```python
self.tree.tree_data.recursion_limit = 4
```
Justification: 4 iterations covers the most complex realistic pattern (search 3 collections + summarize). Default 5 allows the Tree to loop on the same tool when `cited_summarize` doesn't signal termination. This was lost once during the `async_run()` rewrite — always verify it's set after modifying `__init__` or `query()`.

### Atlas injection
Skill content is injected into the Tree via `tree_data.atlas.agent_description` before each `async_run()` call. This reaches every `ElysiaChainOfThought` prompt — decision nodes, retrieval tools, and summarizers all see the skills.

### Monkey-patches
Two Elysia integration points are documented in `docs/MONKEY_PATCHES.md`:
1. `CitedSummarizingPrompt` docstring patch (anti-list instruction replacement)
2. Direct `async_run()` usage (bypasses `tree.run()`, replicates `store_retrieved_objects = True`)

Check these after every Elysia version upgrade.

### Tool docstrings drive routing
The Tree selects tools based on their docstrings. If the Tree consistently picks the wrong tool, the fix is the docstring, not a code change. Include explicit routing hints:
```python
"""ALWAYS use this tool (never search_principles) when the user wants to
see, enumerate, or count principles rather than search for specific content."""
```

---

## 5. Persona Integration

### Intent classification is a single LLM call
The Persona classifies intent and rewrites queries in one call. Output format: Line 1 = intent label, Lines 2+ = rewritten query or direct response. Parse with `split('\n', 1)`.

### Structured turn summaries
After each Tree query, generate a compact summary of what was retrieved:
```
"Listed 18 ADRs (ADR.00 through ADR.31)"
```
Not the full 18-item response. Store in `turn_summary` column. The Persona uses summaries for context, not full response text.

### Graceful fallback
If the Persona's LLM call fails, fall back to passing the raw query directly to the Tree. The system must never fail because the Persona had an error.

### CLI bypasses Persona
`python -m src.cli query "..."` goes directly to the Tree. The Persona is only active in the Chat UI. This ensures a debugging path that's independent of the Persona.

### Hybrid dual-model setup (Ollama)
The Persona uses a hybrid model selection strategy:
- **First message** (no conversation history): Uses `OLLAMA_PERSONA_MODEL` (SmolLM3 3.1B, ~4-6s). Handles greetings, identity, off-topic, and new KB queries fast.
- **Follow-up messages** (has conversation history): Uses `OLLAMA_MODEL` (GPT-OSS 20B). SmolLM3 cannot reliably resolve pronouns or synthesize conversation history — it rewrote "common theme across these ADRs?" as "consequences of ADR.21". The 20B model handles context-dependent query rewriting correctly.

If `OLLAMA_PERSONA_MODEL` is not set, the Persona falls back to `OLLAMA_MODEL` for all calls.

**Context window constraint:** SmolLM3 has a 4,096-token context window. The Persona prompt (SKILL.md + message, no history for SmolLM3) totals ~1,200 tokens. If persona-orchestrator SKILL.md grows beyond ~2,000 tokens, switch to a model with a larger context window.

**SmolLM3 output format quirks:** SmolLM3 outputs intent labels with markdown formatting (`**intent:** identity`) instead of bare labels. The `_parse_response()` parser strips formatting artifacts (`*`, `:`, `intent_` prefix) and searches for valid intent names. Direct responses may also contain format echoes and self-commentary, which are cleaned by regex patterns in `_parse_response()`.

**UI model selector isolation:** The `/api/settings/llm` endpoint only updates `settings.ollama_model` (the Tree model). The Persona model is set exclusively via `.env`.

---

## 6. Frontend Rules

### SSE event types
- `status` — progress updates ("Running search_principles...")
- `decision` — Tree decisions ("Decision: list_all_adrs Reasoning: ...")
- `persona_intent` — Persona classification ("Follow-up from conversation → ...")
- `complete` — final response with content
- `error` — error message

### No text events in thinking container
Status and decision events provide progress. Text events from the Tree contain both intermediate narration and final responses with the same `payload_type`, making them impossible to distinguish. Suppress all text events from the thinking queue.

### User-facing labels
```javascript
// ✅ CORRECT
const intentLabels = {
    'retrieval': 'Searching knowledge base',
    'follow_up': 'Follow-up from conversation',
};

// ❌ WRONG — developer-facing labels shown to users
addThinkingStep('follow_up', 'status');
```

### Use marked.js for markdown rendering
Don't write custom markdown parsers. Use `marked.js` via CDN. For copy-to-clipboard, use a DOM walker (`htmlToPlainText()`) since CSS-generated counters don't appear in `innerText`.

---

## 7. Data Integrity

### Principle collection has unreliable doc_type
DAR chunks in the Principle collection are tagged as `doc_type: 'principle'` instead of `'principle_approval'`. The ADR collection is correctly tagged. Use title-based filtering (`startswith("Principle Approval Record")`) as a workaround for principles. This is an ingestion bug — fix it there eventually.

### Template files must be filtered
`adr-template.md` and similar template files are ingested into collections. Filter them by `doc_type: 'template'` or by filename pattern during ingestion and in search/listing tools.

### Weaviate bug: range + not_equal filter combination
Combining range operators (`greater_or_equal` / `less_or_equal`) with `not_equal` on a *different* property silently drops results. Observed in both Principle and ArchitecturalDecision collections: a range filter on `principle_number` (0010–0018) returns 80 chunks correctly, but adding `title.not_equal("Principle Approval Record List")` to the same filter reduces results to 6 chunks (1 principle instead of 9). The `not_equal` clause appears to interfere with the range evaluation.

**Workaround:** Apply range filters in Weaviate, then do exclusion filtering (DAR/template removal) in the Python loop after fetching results. Never combine range operators with `not_equal` on a different property in the same Weaviate filter expression.

This affects `search_principles` and `search_architecture_decisions` range query paths. Single-value `equal` + `not_equal` combinations (e.g., `adr_number.equal("0029") & title.not_equal(...)`) work correctly — only range operators trigger the bug.

### Collection has `_OpenAI` suffix
When `LLM_PROVIDER=openai`, collections have an `_OpenAI` suffix. All filters, tools, and lookups must work with both collection name variants.

---

## 8. Testing

### Regression queries (must always pass)
```bash
python -m src.cli query "What ADRs exist in the system?"          # → 18 ADRs
python -m src.cli query "What PCPs exist in the system?"          # → 31 principles
python -m src.cli query "What are the consequences of ADR.29?"    # → trade-offs
python -m src.cli query "What is document 22?"                    # → disambiguates ADR.22 vs PCP.22
python -m src.cli query "What is ADR 12?"                         # → CIM/IEC standards
```

### Run regressions before every commit
Every code change must be verified against these 5 queries before committing. If any query regresses, the commit must not proceed.

### Chat UI tests (Persona)
These require the Chat UI and must be run in the browser:
1. "Who are you?" → identity response, no KB search
2. "What's the weather?" → polite decline, no KB search
3. Multi-turn: "What ADRs exist?" → "Is there a common theme across these?" → thematic synthesis
4. Pronoun resolution: "What PCPs exist?" → "Show me the first three" → PCP.10, PCP.11, PCP.12

---

## 9. Commit Discipline

### Test before committing
Run the 5 regression queries. If they pass, commit. If they fail, fix first.

### Document monkey-patches
Any integration point that depends on Elysia's internal structure (prompt text, method signatures, data structures) must be documented in `docs/MONKEY_PATCHES.md` with the exact text being patched and what to check after an Elysia upgrade.

### Document why, not what
```python
# ❌ WRONG — describes what the code does (obvious from reading it)
# Set recursion limit to 4
self.tree.tree_data.recursion_limit = 4

# ✅ CORRECT — explains why this value was chosen
# Limit: 4 iterations covers the most complex realistic pattern
# (search 3 collections + summarize). Default 5 allows the Tree
# to loop on the same tool when cited_summarize doesn't signal
# termination. See: search_principles 7× loop incident.
self.tree.tree_data.recursion_limit = 4
```

### Track regressions from rewrites
When rewriting a function (e.g., the `async_run()` migration), verify that all behavioral settings from the original code are preserved in the new code. The `recursion_limit = 2` setting was lost during the `async_run()` rewrite because the new code didn't replicate all setup from the old `__init__`.

---

## 10. Performance Expectations

### Local model (GPT-OSS:20B on M3 MacBook Pro)
- Single LLM inference: 3–8 seconds
- Persona classification: 2–3 seconds (SmolLM3) / 5–12 seconds (GPT-OSS:20B if no persona model set)
- Full Tree query (search + summarize): 15–30 seconds
- Total with Persona + SmolLM3: 17–33 seconds
- Direct response (identity/off-topic): 1–3 seconds (SmolLM3) / 3–8 seconds (GPT-OSS:20B)

### Cloud model (GPT-5.2 / OpenAI)
- Persona classification: < 1 second
- Full Tree query: 5–15 seconds
- Direct response: < 1 second

### Every long operation needs a progress indicator
If the user will wait more than 2 seconds, show a thinking step. The Persona emits "Thinking..." before its LLM call. The Tree emits status/decision events during execution. Never let the UI freeze without feedback.

---

## 11. File Locations

| File | Purpose |
|------|---------|
| `src/elysia_agents.py` | Elysia Tree integration, tool registration, query execution |
| `src/persona.py` | AInstein Persona — intent classification, query rewriting |
| `src/chat_ui.py` | FastAPI Chat UI, SSE streaming, conversation store |
| `src/cli.py` | CLI interface (bypasses Persona) |
| `src/static/index.html` | Chat UI frontend |
| `src/static/skills.html` | Skills Management UI |
| `src/skills/registry.py` | Skill registry with `inject_into_tree` support |
| `src/skills/loader.py` | SKILL.md parsing, thresholds loading |
| `src/skills/api.py` | Skills API endpoints |
| `skills/registry.yaml` | Skill registry configuration |
| `skills/*/SKILL.md` | Individual skill definitions (including `response-contract`) |
| `docs/MONKEY_PATCHES.md` | Elysia integration points for upgrade checking |
| `thresholds.yaml` path | `skills/rag-quality-assurance/references/thresholds.yaml` |

---

## 12. Repository & Identity Rules

These rules are **non-negotiable** and apply to all commits, comments, pull requests, issues, and any interaction with git repositories.

### No AI tool attribution in repositories
Never use the names "Claude", "Claude Code", "Anthropic", or any other AI tool name in commit messages, code comments, pull request descriptions, issue comments, branch names, or any other content that is pushed to a repository. This applies to all repositories without exception.

```bash
# ❌ NEVER DO THIS
git commit -m "Fix implemented by Claude"
git commit -m "Generated with Anthropic Claude Code"
# Code comment: "// Claude suggested this approach"

# ✅ CORRECT
git commit -m "Fix search_principles retry loop by adding status to return props"
git commit -m "Add dynamic property discovery to all search tools"
```

### Repository-specific git accounts
- **Alliander repositories** (`github.com/alliander`): Use **CagriTekinay** account only. Never use `ctekinay` account.
- **Personal repositories** (`github.com/ctekinay`): Use **ctekinay** account only. Never use `CagriTekinay` account.
- Never commit to an Alliander repository unless explicitly instructed to do so.

### Verify before every push
Before pushing to any repository:
1. Confirm the correct git account is configured for the target remote
2. Confirm no AI tool names appear in any commit message in the push
3. Confirm the target repository is correct (Alliander vs. personal)
4. Confirm you have explicit authorization to push to Alliander repositories
