# AInstein [![Alliander](https://img.shields.io/badge/maintained%20by-Alliander-orange.svg)](https://www.alliander.com)

Agentic RAG and multi-skill AI system developed by Alliander's Energy System Architecture Group to support various
architecture workstreams. Built on Weaviate (Vector DB) + Pydantic AI agents with an AInstein Persona layer for
intent classification and a Skills Framework for prompt engineering.

## What It Does

AInstein lets architects and engineers query Alliander's architecture knowledge base using natural language:

- **18 Architecture Decision Records (ADRs)** — design decisions with context, options, and consequences
- **41 Architecture Principles (PCPs)** — guiding statements for design choices
- **59 Decision Approval Records (DARs)** — governance and approval history (18 ADR + 41 PCP approval records)
- **5,200+ SKOS Vocabulary Concepts** — IEC 61970/61968/62325 standards, CIM models, domain ontologies via SKOSMOS REST
  API
- **Policy Documents** — data governance, privacy, security policies
- **ArchiMate 3.2 Model Generation** — validated Open Exchange XML from architecture descriptions, with optional Dublin
  Core (`dct:*`) metadata properties on elements and relationships
- **ArchiMate Model Inspection** — analyze, describe, and compare ArchiMate models from conversation artifacts, file
  uploads, or URLs
- **Architecture Principle Generation** — generate new TOGAF-aligned principles (Statement/Rationale/Implications)
  grounded in the KB with structure validation, quality gate checks, and artifact persistence for download and refinement
- **Architecture Principle Quality Assessment** — assess existing principles against TOGAF quality criteria: Decision
  Gate (is it a principle?) and five dimensions (understandability, robustness, completeness, consistency, stability)
- **Repository Architecture Analysis** — analyze GitHub repos or local clones to extract architecture (tech stack,
  modules, dependency graph, deployment topology) and generate ArchiMate models automatically. Zero LLM tokens for
  extraction — deterministic parsers handle AST, manifests, docker-compose, OpenAPI, Terraform, and SQL migrations
- **GitHub Repository Browsing** — inspect GitHub repos (metadata, README, directory structure), org/user profiles (top
  repositories), and individual files via MCP and REST API
- **SKOSMOS Vocabulary Lookups** — term definitions, abbreviations, concept hierarchies via structured API

Queries are handled by the AInstein Persona, which classifies intent, emits skill tags for domain-specific capabilities,
and rewrites queries. The Persona routes to the appropriate execution path:

- **Retrieval queries** ("What ADRs exist?", "What is document [N]?") go to the **RAG Agent**
  (Pydantic AI), which selects tools, searches collections, and formats responses with citations.
- **Generation queries** ("Create an ArchiMate model for an ADR") go to the **Generation Pipeline**, which fetches
  source content, builds a prompt from the matching skill, makes a single LLM call, validates, and saves the artifact
  for download. Token usage is tracked across all LLM calls (generation, view repair, validation retries) and reported
  in a single summary log line at completion.
- **Refinement queries** ("Add a Technology layer to the model") go to the *
  *Generation Pipeline** with the previous artifact loaded as context. The LLM returns a structured YAML diff
  envelope (~200 tokens) instead of regenerating the full model (~4,600 tokens). A deterministic merge engine applies
  the diff — supporting element/relationship addition, removal, property modification (additive merge), and relationship
  modification via derived IDs; if parsing fails, the pipeline falls back transparently to full regeneration.
- **Inspection queries** ("Describe the model you just generated", "What elements are in this ArchiMate
  file?") go to the **Inspection path**. ArchiMate files are converted to compact YAML (~
  90% token reduction) for LLM analysis. GitHub repo URLs fetch metadata + README + directory listing via MCP for
  repo-level analysis. GitHub org/user URLs fetch profile and top repositories via REST API. Non-ArchiMate files (e.g.,
  `.py`, `.toml`) get generic file analysis. Models can come from conversation artifacts, file uploads, or URLs.
- **Principle generation queries** ("Generate a principle on data sovereignty") go to the **Principle Agent** (Pydantic AI), which searches the KB for related principles to ensure
  consistency, generates a TOGAF-aligned principle, validates its structure, and saves it as a markdown artifact.
- **Principle quality assessment queries** ("Assess a principle against TOGAF criteria") go to the **Principle Agent**,
  which retrieves principles and applies the TOGAF Decision Gate and five quality dimensions. For compliance evaluation
  (document uploaded + evaluated against principles), the agent uses batched evaluation: principles are split into
  groups, each batch evaluated independently against the document, and results merged into a single unified table. This
  ensures complete coverage of all principles regardless of model context window size. Batching is automatic for local
  models and opt-in for cloud models via configuration.
- **Repository analysis queries** ("Analyze https://github.com/org/repo and generate an ArchiMate model") go through a
  three-phase pipeline chained by `stream_repo_archimate_response()` in a single user turn:
  - **Phase 1:** The **RepoAnalysisAgent** clones the repo and runs deterministic extraction tools (profile, manifests,
    AST, dependency graph) — zero LLM tokens. Architecture notes saved as a YAML artifact.
  - **Phase 2:** The **Generation Pipeline** converts the architecture notes into an ArchiMate 3.2 Open Exchange XML
    model. If YAML-to-XML conversion fails, an explicit error is surfaced and Phase 3 is skipped.
  - **Phase 3:** A deterministic Python function (`generate_explorer_html()`) templates an interactive HTML architecture
    browser from the YAML — tier classification, module cards, class drill-down, dependency edge pills, JSON export.
    Sub-second execution, zero LLM tokens.
- **Multi-step queries** ("Compare two architecture documents") go to the **Multi-Step Orchestrator**, which decomposes
  the query into per-document RAG calls, executes each sequentially, and synthesizes a combined response. The Persona
  classifies these as `multi-step` with explicit step plans. Search result caching prevents retry spirals — if the RAG
  agent searches the same document twice within a step, the second call returns the cached result without hitting
  Weaviate or burning a tool call slot.
- **Vocabulary queries** ("What is an asset?", "Define interoperability") go to the **Vocabulary Agent** (Pydantic AI),
  which searches SKOSMOS for term definitions. When a term exists in multiple vocabularies (e.g., terms appearing in
  multiple standards), the agent surfaces all options and asks the user to select a context before presenting a
  definition — a programmatic disambiguation gate prevents silently picking one vocabulary.
- **Direct response queries** (identity, off-topic, and conversational queries) are answered by the Persona without any
  backend call. Meta-questions about the agent's reasoning are answered directly; domain-specific follow-ups route to
  the RAG Agent.

**Quality Gate:** After RAG Agent responses, a closed-loop quality gate evaluates response shape against query complexity.
For simple queries classified by the Persona, the gate checks proportionality (is a "what is X?" answer a concise summary
or an exhaustive dump?) and cleans up verbose abstentions. An enumeration guard (code-level, zero latency) detects
responses with 5+ structured list items and skips condensation regardless of complexity classification — preventing
destructive reformatting of listing and follow-up responses. Gate actions are visible in the UI thinking panel as `[QA]`
steps and logged for operator diagnosis. All gate parameters (prompts, thresholds, enable/disable) are configurable in
`src/aion/config/runtime.yaml` under `quality_gate`.

**Disclaimer:** Currently, the above-mentioned data sources are integrated stand-alone via the data/ folder. The
short-term goal for AInstein is full integration with ESA repositories, tools, and other internal data sources directly.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Web UI / CLI                                 │
│              localhost:8081  |  uv run aion chat                     │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│            AInstein Persona / Orchestration Layer                    │
│  Intent classification: retrieval, listing, follow_up, generation,   │
│    refinement, inspect, identity, off_topic, clarification,          │
│    conversational                                                     │
│  Query rewriting with conversation context (pronoun resolution)      │
│  Skill tag emission for on-demand capabilities                       │
│  Direct response for identity/off-topic/clarification                │
└──────────┬─────────────────────┬──────────────────────┬──────────────┘
           │ retrieval / listing │ generation /         │ inspect
           │ / follow_up         │ refinement           │
┌──────────▼─────────────────┐ ┌─▼───────────────┐ ┌────▼────────────────────┐
│  RAG Agent (Pydantic AI)   │ │ Generation      │ │ Inspection              │
│  KB search + summarize     │ │ Pipeline        │ │ XML → YAML → LLM        │
├────────────────────────────┤ │ Direct LLM call │ │ Sources: artifact,      │
│  search_arch_decisions     │ ├─────────────────┤ │ upload, URL (MCP/httpx) │
│  search_principles         │ │ 1. Fetch source │ └─────────────────────────┘
│  search_policies           │ │ 2. Load skill   │
│  list_adrs                 │ │ 3. LLM call     │ ┌─────────────────────────┐
│  list_principles           │ │ 4. Sanitize XML │ │   Artifacts             │
│  list_policies / list_dars │ │ 5. View repair  │ │  SQLite store           │
│  search_by_team            │ │ 6. Validate     │ │  SSE download card      │
│  request_data              │ │ 7. Save artifact│ │  File upload + API      │
└──────────────┬─────────────┘ │ 8. Download card│ └─────────────────────────┘
               │               ├─────────────────┤
               │               │ Refinement:     │
               │               │ YAML diff merge │
               │               │ + fallback      │
               │               └─────────────────┘
┌──────────────┴─────────────┐ ┌─────────────────────────────────────────────┐
│ Vocabulary Agent           │ │ ArchiMate Agent                             │
│ (Pydantic AI)              │ │ (Pydantic AI)                               │
├────────────────────────────┤ ├─────────────────────────────────────────────┤
│ skosmos_search             │ │ validate_archimate   save_artifact          │
│ skosmos_concept_details    │ │ inspect_archimate    get_artifact           │
│ skosmos_list_vocabularies  │ │ merge_archimate_view request_data           │
│ search_knowledge_base      │ └─────────────────────────────────────────────┘
│ request_data               │ ┌─────────────────────────────────────────────┐
└────────────────────────────┘ │ Principle Agent (Pydantic AI)               │
               │               ├─────────────────────────────────────────────┤
               │               │ search_related_principles  save_principle   │
               │               │ validate_principle_structure get_principle  │
               │               │ request_data                                │
               │               └─────────────────────────────────────────────┘
               │               ┌─────────────────────────────────────────────┐
               │               │ Repo Analysis Agent (Pydantic AI)           │
               │               ├─────────────────────────────────────────────┤
               │               │ clone_repo          extract_code_structure  │
               │               │ profile_repo        build_dep_graph         │
               │               │ extract_manifests   merge_and_save_notes    │
               │               └─────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│                     Skills Framework                                 │
│  Always-on skills injected into every prompt via atlas               │
│  ┌─────────────────┐ ┌──────────────────┐ ┌──────────────────────┐   │
│  │ persona-        │ │ rag-quality-     │ │ esa-document-        │   │
│  │ orchestrator    │ │ assurance        │ │ ontology             │   │
│  │ Intent classif. │ │ Anti-hallucin.   │ │ ADR/PCP/DAR          │   │
│  │ + skill tags    │ │ Citation rules   │ │ disambiguation       │   │
│  └─────────────────┘ └──────────────────┘ └──────────────────────┘   │
│  ┌─────────────────┐ ┌──────────────────┐                            │
│  │ response-       │ │ ainstein-        │                            │
│  │ formatter       │ │ identity         │                            │
│  │ Numbered lists, │ │ Tone, behavior,  │                            │
│  │ follow-ups      │ │ scope, identity  │                            │
│  └─────────────────┘ └──────────────────┘                            │
│                                                                      │
│  On-demand skills (injected when Persona emits matching tags)        │
│  ┌─────────────────┐ ┌──────────────────┐ ┌──────────────────────┐   │
│  │ archimate-      │ │ archimate-view-  │ │ skosmos-             │   │
│  │ generator       │ │ generator        │ │ vocabulary           │   │
│  │ ArchiMate 3.2   │ │ View layout +    │ │ SKOSMOS REST API     │   │
│  │ XML + properties│ │ merge            │ │ term definitions     │   │
│  │ tag: archimate  │ │ tag: archimate   │ │ tag: vocabulary      │   │
│  └─────────────────┘ └──────────────────┘ └──────────────────────┘   │
│  ┌─────────────────────┐ ┌─────────────────────────┐                 │
│  │ principle-quality-  │ │ principle-generator     │                 │
│  │ assessor            │ │ Principle template +    │                 │
│  │ TOGAF quality rubric│ │ quality gate            │                 │
│  │ tag:principle-qual. │ │ tag: generate-principle │                 │
│  └─────────────────────┘ └─────────────────────────┘                 │
│  ┌─────────────────────┐ ┌─────────────────────────┐                 │
│  │ repo-to-archimate   │ │ repo-architecture-      │                 │
│  │ Repo analysis tools │ │ explorer                │                 │
│  │ + classification    │ │ HTML explorer from YAML │                 │
│  │ tag: repo-analysis  │ │ tag: repo-arch.-explr.  │                 │
│  └─────────────────────┘ └─────────────────────────┘                 │
└──────────────────────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│                        Weaviate 1.35.7                               │
│  ┌──────────────────┐ ┌───────────┐ ┌──────────────┐                 │
│  │ Architectural    │ │ Principle │ │ Policy       │                 │
│  │ Decision  18+49  │ │ 41+41     │ │ Document     │                 │
│  │ ADRs + DARs      │ │ PCPs+DARs │ │ 76 chunks    │                 │
│  └──────────────────┘ └───────────┘ └──────────────┘                 │
│  Hybrid search: BM25 keyword + vector similarity                     │
│  Client-side embeddings via Ollama (all providers)                   │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│                        SKOSMOS REST API                              │
│  5,200+ SKOS concepts · IEC/CIM/EU vocabularies · ESAV terminology   │
│  skosmos_search → skosmos_concept_details → skosmos_list_vocabs      │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│                      LLM Providers                                   │
│  ┌────────────────┐ ┌────────────────────┐ ┌──────────────────────┐  │
│  │ Ollama         │ │ GitHub CoPilot     │ │ OpenAI               │  │
│  │ (default)      │ │ Models (Alliander  │ │ (pay-per-token, not  │  │
│  │ gpt-oss:20b    │ │ Enterprise, might  │ │ for company data)    │  │
│  │ Local, free    │ │ have token limit)  │ │ gpt-5.2              │  │
│  └────────────────┘ └────────────────────┘ └──────────────────────┘  │
│  Per-component overrides: PERSONA_PROVIDER / RAG_PROVIDER            │
└──────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- **Docker** (or **Podman**) — for Weaviate vector database and SKOSMOS vocabulary service
- **Python 3.11-3.13** (3.10 and 3.14+ not supported). Python 3.13 support added March 2026 — existing 3.12 environments continue to work without changes.
- **Ollama** (default, local, free) — [ollama.ai/download](https://ollama.ai/download)
- **SKOSMOS** — vocabulary lookup service (runs separately via Docker, see [SKOSMOS Setup](#skosmos-setup))
- Or **GitHub CoPilot Models** (Alliander Enterprise Account, 8K token limit) — set `LLM_PROVIDER=github_models` and
  `GITHUB_MODELS_API_KEY` in `.env`
- Or **OpenAI API key** (cloud, paid — do not use with company data) — set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` in
  `.env`

## Quick Start

```bash
# 1. Clone and enter
git clone <your-fork-url>
cd esa-ainstein-artifacts

# 2. Start Weaviate (use podman-compose on Linux if not using Docker)
docker compose up -d

# 3. Start Ollama and pull models
ollama serve &
ollama pull nomic-embed-text-v2-moe
ollama pull gpt-oss:20b

# 4. Python environment (requires uv — https://docs.astral.sh/uv/)
uv sync

# 5. Configure
cp .env.example .env
# Default uses Ollama — no changes needed

# 6. Initialize and run
uv run aion init
uv run aion chat --port 8081
# Open http://localhost:8081
```

## Commands

The CLI uses Typer for structured terminal output.

```bash
# Web UI
uv run aion chat --port 8081       # Start web UI (default: localhost:8081)

# Data management
uv run aion init                  # Initialize collections and ingest data
uv run aion init --chunked        # Ingest with section-based chunking
uv run aion init --recreate       # Recreate collections from scratch

# Querying
uv run aion query "question"              # Direct RAG query (bypasses Persona — see note below)
uv run aion query "question" --persona    # Full pipeline: Persona → routing → agent/orchestrator
uv run aion search "query"               # Direct hybrid search against Weaviate (no agent)
uv run aion interactive                   # Interactive query session (multi-turn, bypasses Persona)
uv run aion rag "query"                   # RAG Agent interactive session
uv run aion vocabulary "term"             # Search SKOSMOS vocabulary
uv run aion archimate "query"             # Query ArchiMate agent

# System
uv run aion config                # Show current configuration
uv run aion status                # Show Weaviate collection status
uv run aion agents                # List available knowledge domains
uv run aion capability-report     # Show logged capability gaps
uv run aion evaluate              # Run RAG evaluation (Ollama vs OpenAI)

# Element Registry
uv run aion registry list          # List all registered elements
uv run aion registry list --near-dupes  # Show near-duplicate element pairs
uv run aion registry stats         # Registry statistics (total, by-type, near-duplicates)
uv run aion registry merge ID1 ID2 # Merge element ID2 into ID1 (union refs, delete ID2)
uv run aion registry backfill      # Backfill dct_identifier from Weaviate metadata
```

> **Important: `query` without `--persona` bypasses the AInstein Persona entirely.** This means no intent classification,
> no multi-step orchestration, no routing to specialized agents (vocabulary, ArchiMate, principles), and no query
> rewriting. The query goes directly to the RAG Agent. Use `--persona` (or `-p`) to test the full pipeline including
> orchestration, or use `aion chat` for the web UI which always routes through the Persona.

## Web UI

The chat interface at `http://localhost:8081` provides:

- **Chat** — conversational RAG with AInstein Persona intent classification and citations
- **Settings** — model selection, temperature, comparison mode. Provider and model preferences persist across server
  restarts via `~/.ainstein/settings.json`
- **Plugin Management** (`/plugins`) — per-plugin view: enable/disable skills, edit each plugin's
  `thresholds.yaml` in the plugin-scoped Plugin Settings panel, reload a plugin. (`/skills`
  308-redirects here for back-compat.)

## Pixel Agents (VSCode Extension)

AInstein integrates with [Pixel Agents](https://github.com/pablodelucca/pixel-agents), a VSCode extension that
visualizes agent activity as animated pixel-art characters in a virtual office. The bundled extension is a customized
fork with an AInstein adapter layer (`ainsteinAdapter.ts`) that translates AInstein's manifest format and JSONL event
protocol into the extension's internal agent/transcript system. This includes custom manifest detection, multi-agent
registration from a single server, and support for AInstein-specific event types (speech bubbles, tool labels).

Each AInstein agent (Persona, Orchestrator, RAG Agent, Vocabulary, ArchiMate, Principles, Repository Analysis) appears
as a character that reacts in real time:

- **Tool calls** — the character shows what tool is being used (e.g., "Searching ADRs...", "Validating model...")
- **Speech bubbles** — the Persona greets users ("Hi!", "I'm AInstein!") on identity queries, and shows contextual
  messages ("Let me think...") on conversational responses
- **Idle/active states** — characters animate when their agent is working and return to idle when done

### Setup

A pre-built `.vsix` is bundled in the repository:

```bash
code --install-extension extensions/pixel-agents-1.0.2.vsix
```

No additional configuration is needed — the extension auto-detects AInstein's agent manifest when the server starts.
The manifest and per-agent JSONL transcript files are written to the extension's project data directory, which it
watches via its file watcher.

### How it works

1. On server startup, `pixel_agents.py` writes a `manifest.json` with agent metadata (name, role, JSONL file path)
2. The extension's AInstein adapter detects the manifest, registers all 6 agents, and assigns each a pixel-art
   character with a unique palette
3. During query processing, the server writes structured events (tool_call, tool_result, speech, idle) to per-agent
   JSONL files
4. The extension's file watcher picks up new events and the transcript parser updates character animations in real time

### Without the extension

If the extension is not installed, AInstein works normally — pixel agent events are silently discarded. The extension is
purely a visualization layer with no effect on query processing or results.

## Plugins

AInstein loads skills, MCP servers, and hooks from plugins — self-describing directory trees
containing a `.ainstein-plugin/plugin.json` manifest. Plugins are deployed under the
top-level `plugins/` directory. Three plugins are committed and bundled:
`ainstein-kernel` (`role: kernel` — the always-on host behavior:
identity, persona, formatter, RAG quality, document ontology;
non-removable), `esa-workflow` (`role: domain` — the ESA workflow
capability, SKOSMOS vocabulary), and `enterpower-architecture`
(`role: domain` — the authoritative architecture provider: ArchiMate
generation/tooling, principles, repo analysis). Any *other* plugin you
deploy into `plugins/` is gitignored — only these three are tracked. The
repository root is the host, not a plugin.

### Plugin discovery (at startup)

In order:

1. **`AINSTEIN_PLUGINS` env var** — colon-separated absolute paths. Use for development and CI.
   ```bash
   AINSTEIN_PLUGINS=/path/to/my-plugin uv run aion serve
   ```
2. **`~/.ainstein/plugins/*/`** — auto-discovery. Drop a plugin's root directory into
   `~/.ainstein/plugins/` and AInstein loads it on next start.
3. **In-tree `<repo>/plugins/*/`** — every child directory containing `.ainstein-plugin/`.
   This is where the bundled `ainstein-kernel`, `esa-workflow`, and
   `enterpower-architecture` load from. The repo root itself is never scanned.

In-tree is checked **last**, so a plugin supplied via the env var or `~/.ainstein/plugins/`
wins the `conflicts_with` tie-breaker over a same-named in-tree skill. Discovery dedupes by
resolved absolute path. Malformed manifests are logged at WARNING and skipped — a single
broken third-party plugin can't crash the host. If discovery finds **no** plugins, AInstein
fails fast: at minimum the `ainstein-kernel` plugin must be present at
`plugins/ainstein-kernel/` (it carries the always-on host behavior).

### Trust model

**Loading a plugin grants it AInstein-process privileges.** Plugin-supplied hook scripts run
with the AInstein process's user, env, and filesystem access. Plugin-supplied MCP server
processes are spawned and signaled by the AInstein lifespan. There is no sandboxing in this
release.

Only load plugins from sources you trust. The trust decision is one-shot at install time —
plugins from `AINSTEIN_PLUGINS` or `~/.ainstein/plugins/` are loaded unconditionally on
every server start.

### Skill-name collisions

When two plugins declare a skill with the same name, AInstein resolves the conflict in one
of two ways:

* **`conflicts_with` declaration** — the declaring side auto-disables on load when its
  target peer is enabled (in-memory only; YAML on disk unchanged). Logged at INFO; UI surfaces
  the shadowed skill under its owning plugin's accordion with a "disabled by conflicts_with"
  badge.
* **No `conflicts_with`** — startup fails with `DuplicateSkillError`, naming both plugins.
  Operator resolves manually by disabling one plugin's copy via the skills UI.

The skills UI's per-plugin toggle endpoint runs a **duplicate-check preflight**: re-enabling
a shadowed skill returns HTTP 409 with the conflicting pair, so operators see the conflict
before it bites at next server start.

### First-invocation latency

Plugin MCP servers are spawned **eagerly at AInstein startup**, not lazily on first slash-
command invocation. This is a deliberate trade-off: `ClientSession.list_tools()` requires an
initialized session, which requires the server process to be running. The cold-start cost
(5–15 s for Vite-based servers like the peer plugin's interactive viewer) is paid once at
`lifespan` startup and parallelized across all servers via `asyncio.gather`. After lifespan,
slash commands return sub-second on every invocation.

For AInstein-standalone (no plugin MCP servers declared), this is a no-op and startup is
unaffected.

### Plugin-scoped API endpoints

For programmatic plugin management:

* `GET /api/plugins` — manifest metadata + per-plugin skill counts.
* `PUT /api/plugins/{plugin}/skills/{skill}/enabled` — plugin-scoped toggle with the
  duplicate-check preflight. Returns HTTP 409 on conflict with a structured `detail` body
  naming the conflict.

The legacy `PUT /api/skills/{skill}/enabled` endpoint (no plugin scope) routes to the
**first plugin in load order** that defines the named skill. Under collision, this may not
target the plugin you intended. **Programmatic API consumers managing multi-plugin installs
should use the plugin-scoped endpoint instead** — it routes explicitly and runs the
preflight.

### Writing a plugin

See `proposals/plugin-author-guide.md` for the full schema reference, MCP/hook patterns,
file_path semantics caveat, and worked examples. The smallest end-to-end example —
exercising every locked-decision path (collision, conflicts_with, slash routing, per-skill
MCP routing, hook firing, shared references) — is in `tests/fixtures/fake_plugin/`.

## Skills Framework

Skills are markdown instruction files injected into every LLM prompt. They control how AInstein behaves — identity,
formatting, citation rules, domain knowledge. Skills are managed via the `/plugins` (Plugin Management) UI or by editing files directly.

Skills live under each plugin's `skills/` directory; the per-plugin manifest at
`.ainstein-plugin/skills-registry.yaml` controls which are enabled and how they route.
Below is the bundled three-plugin layout — third-party plugins follow the same
shape under their own roots. Each plugin owns its `.ainstein-plugin/`
manifest, `skills-registry.yaml`, and `thresholds.yaml`:

```
plugins/
├── ainstein-kernel/                     # role: kernel — always-on host behavior (committed, non-removable). 4 skills.
│   ├── .ainstein-plugin/{plugin.json, skills-registry.yaml, thresholds.yaml}
│   └── skills/
│       ├── persona-orchestrator/SKILL.md     # Intent classification, query rewriting, skill tags
│       ├── ainstein-identity/SKILL.md        # Conversational behavior, tone, identity, scope
│       ├── rag-quality-assurance/SKILL.md    # Citation format, abstention rules (owns RAG thresholds)
│       └── response-formatter/SKILL.md       # Numbered lists, statistics, follow-up options
├── esa-workflow/                  # role: domain — ESA-specific capability + document ontology (committed)
│   ├── .ainstein-plugin/{plugin.json, skills-registry.yaml, thresholds.yaml}
│   └── skills/
│       ├── skosmos-vocabulary/SKILL.md       # On-demand (tag: vocabulary) — SKOSMOS REST API
│       └── esa-document-ontology/            # inject_mode: always — ADR/PCP/DAR naming, numbering, disambiguation
│           └── references/registry-index.md  # Condensed document registry
│                                             # (moved here from ainstein-kernel: ESA ontology is ESA-specific,
│                                             #  not generic host behavior — reverses Phase-4 Decision 2)
└── enterpower-architecture/             # role: domain — authoritative architecture provider (committed)
    ├── .ainstein-plugin/{plugin.json, skills-registry.yaml, thresholds.yaml}
    ├── .mcp.json                            # preview MCP server (currently unwired)
    ├── shared-references/archimate-shared/  # Cross-skill ArchiMate reference docs (group-merged)
    └── skills/
        ├── archimate-oxc-generator/         # On-demand — ArchiMate 3.2 OXC (Open Exchange) generation
        ├── archimate-oxc-view-generator/    # On-demand — view/diagram generation
        ├── archimate-visual-composer/       # On-demand — interactive browser visualization
        ├── archimate-viewer/                # /archimate-viewer — start/stop/screenshot the viewer
        ├── archimate-tools/                 # On-demand (tag: archimate-model) — validate/inspect/merge
        ├── principle-generator/             # On-demand (tag: generate-principle) — TOGAF-aligned
        ├── principle-quality-assessor/      # On-demand (tag: principle-quality) — TOGAF Decision Gate
        ├── repo-to-archimate/               # On-demand (tag: repo-analysis)
        └── repo-architecture-explorer/      # On-demand — self-contained interactive HTML explorer
```


**Progressive Skill Loading:** Skills use two injection modes to minimize token usage:

- **Always-on** — core skills (identity, quality assurance, document ontology, response formatting) are injected into
  every prompt via the RAG Agent's system prompt. These apply to all query types.
- **On-demand** — domain-specific skills (ArchiMate generation, ArchiMate views, SKOSMOS vocabulary, principle
  generation, principle quality assessment, repository analysis, architecture explorer) are injected only when the
  Persona emits matching `skill_tags` (e.g., `["archimate"]`, `["vocabulary"]`, `["generate-principle"]`,
  `["principle-quality"]`, `["repo-analysis"]`, or `["repo-architecture-explorer"]`). A standard KB query like "What ADRs exist?" never loads the ArchiMate generation skill (~10K
  chars), SKOSMOS vocabulary rules, repo analysis tools, or principle instructions.

This reduces prompt size by 40-80% for standard queries compared to loading all skills on every call. The Generation
Pipeline loads only the matching generation skill (e.g., enterpower's `archimate-oxc-generator`) — not the always-on skills — since it
operates outside the RAG Agent's retrieval context.

**Configuration split (commit 4 of the plugin migration):**

Two distinct config layers, each owned by the appropriate authority. All values are read at
call time (not startup), so changes take effect without restarting the server.

- **`src/aion/config/runtime.yaml`** (system-runtime, AInstein-controlled, NOT plugin-overridable):
  - `kb_collections` — Weaviate collection names + display labels
  - `llm_token_limits` — max tokens per LLM call site (`persona_reasoning: 2048`,
    `persona_standard: 500`, `summarize_reasoning: 512`, `rag_reasoning: 1000`,
    `chat_review_reasoning: 4096`, etc.). Reasoning model limits must be higher because
    GPT-5 spends reasoning tokens within `max_completion_tokens`
  - `agents.max_tool_calls` — max tool iterations per agent (`default: 15`,
    `rag_agent: 15`, `repo_analysis_agent: 12`). Keys match `AGENT_LABELS` in
    `agents/__init__.py`
  - `document_agent.{timeout_ollama, timeout_cloud, max_retries_*}` — document-agent
    timeouts and retry policy
  - `persona.skip_classification_models` — models too slow for LLM classification
  - `quality_gate` — response quality evaluation (`evaluation_max_tokens: 10`,
    `condensation_max_tokens: 1024`, proportionality prompts, abstention cleanup signals)
  - `upload.*` — file size and history-truncation limits
  - `element_registry.prompt_limit`

- **`<plugin>/.ainstein-plugin/thresholds.yaml`** (per-plugin content tuning, plugin-author-controlled):
  - `abstention.distance_threshold` — maximum vector distance before abstaining
  - `retrieval_limits` — max documents per collection (`adr: 8`, `principle: 6`,
    `policy: 4`, `vocabulary: 4`, `team_search: 10`)
  - `truncation` — content length limits (`content_max_chars: 800`, `list_content_max_chars: 4000`,
    `max_context_results: 50`, `source_display_limit: 35`, etc.)

The split exists because a third-party plugin should be able to tune retrieval and truncation
**for its own skills** but should NOT be able to rebind AInstein's Weaviate collections,
agent tool-call budgets, or LLM token limits. The system-runtime keys live outside any
plugin's reach.

## Project Structure

```
esa-ainstein-artifacts/
├── src/aion/
│   ├── cli.py                    # Typer CLI (init, query — data management and debugging)
│   ├── config.py                 # Pydantic settings from .env (3-provider config)
│   ├── persona.py                # AInstein Persona — intent classification, query rewriting
│   ├── generation.py             # Direct LLM generation pipeline (ArchiMate XML, etc.)
│   ├── chat_ui.py                # FastAPI web server + API endpoints + SQLite conversation store
│   │                             #   Execution router: generation → pipeline, retrieval → RAG Agent
│   ├── orchestrator.py            # Multi-step orchestrator — sequential RAG + synthesis
│   ├── routing.py                # ExecutionModel enum + intent → pipeline routing
│   ├── pixel_agents.py           # Pixel Agents integration for VSCode extension visualization
│   ├── text_utils.py             # Shared text utilities (think-tag stripping)
│   ├── agents/
│   │   ├── __init__.py           # SessionContext — per-query state for agent tool calls
│   │   ├── rag_agent.py          # RAG Agent (Pydantic AI) — tool selection, KB search, abstention
│   │   ├── quality_gate.py       # Post-generation quality gate — response proportionality + abstention cleanup
│   │   ├── vocabulary_agent.py   # Vocabulary Agent — SKOSMOS term lookups and concept details
│   │   ├── archimate_agent.py    # ArchiMate Agent — validation, inspection, view merge
│   │   ├── principle_agent.py    # Principle Agent — TOGAF-aligned principle generation and refinement
│   │   └── repo_analysis_agent.py # Repo Analysis Agent — repository architecture extraction
│   ├── mcp/
│   │   ├── config.yaml           # MCP server registry (URLs, auth, transport)
│   │   ├── registry.py           # MCPServerConfig + load_registry() + get_server()
│   │   ├── client.py             # Generic MCP client (streamable HTTP transport)
│   │   └── github.py             # GitHub file/repo/org fetching + URL parsing
│   ├── tools/
│   │   ├── rag_search.py         # RAGToolkit — Weaviate search, abstention, result building
│   │   ├── artifacts.py          # Artifact save/get for conversation context
│   │   ├── archimate.py          # ArchiMate 3.2 validation, inspection, merge
│   │   ├── yaml_to_xml.py        # ArchiMate YAML ↔ XML converter (generation + inspection)
│   │   ├── skosmos.py            # SKOSMOS REST API wrappers (search, concept details)
│   │   ├── repo_analysis.py      # Repo clone, profile, merge (zero LLM tokens)
│   │   ├── repo_extractors.py    # Manifest, AST, dependency graph extraction
│   │   ├── capability_gaps.py    # Capability gap logging tools
│   │   └── reconciliation.py     # Element registry reconciliation
│   ├── ingestion/                 # Weaviate client and data ingestion
│   │   ├── client.py             # Weaviate connection factory
│   │   ├── collections.py        # Collection schema definitions
│   │   ├── embeddings.py         # Ollama embedding functions
│   │   └── ingestion.py          # Data ingestion pipeline
│   ├── loaders/
│   │   ├── markdown_loader.py    # ADR/PCP markdown parser with frontmatter
│   │   ├── document_loader.py    # DOCX/PDF parser for policies
│   │   ├── registry_parser.py    # ESA registry table parser
│   │   └── index_metadata_loader.py # ESA index metadata parser
│   ├── chunking/                  # Section-based document chunking
│   │   ├── models.py             # Chunk data models
│   │   └── strategies.py         # Chunking strategy implementations
│   ├── registry/
│   │   ├── element_registry.py   # Element identity registry (SQLite, dedup, near-miss detection)
│   │   └── cli.py                # Registry management CLI (list, stats, duplicates)
│   ├── memory/
│   │   ├── session_store.py      # SQLite session management, user profiles
│   │   ├── summarizer.py         # Rolling conversation summaries
│   │   └── cli.py                # Memory management CLI (show, reset, export)
│   ├── storage/
│   │   └── capability_store.py   # Capability gap SQLite CRUD
│   ├── diagnostics/
│   │   ├── rag_diagnostics.py    # RAG pipeline diagnostic tools
│   │   └── retrieval_inspector.py # Retrieval quality inspection
│   ├── skills/
│   │   ├── __init__.py           # Package init, get_skill_registry()
│   │   ├── loader.py             # SkillLoader: parses SKILL.md, loads thresholds
│   │   ├── registry.py           # SkillRegistry: enabled/disabled state, content injection
│   │   ├── api.py                # Skills CRUD API (list, get, toggle, update)
│   │   └── filters.py            # Query-based skill filtering (unused, kept for reference)
│   ├── evaluation/                # RAG quality evaluation framework
│   │   ├── evaluator.py          # Evaluation runner and metrics
│   │   └── test_runner.py        # Test case execution
│   └── static/
│       ├── index.html            # Main chat UI
│       └── plugins.html          # Plugin Management UI (served at /plugins)
├── plugins/                      # Plugin deployment dir
│   ├── ainstein-kernel/          # Bundled (committed): role=kernel — always-on host behavior
│   ├── esa-workflow/       # Bundled (committed): role=domain — ESA workflow (SKOSMOS)
│   └── enterpower-architecture/  # Bundled (committed): role=domain — authoritative architecture
├── extensions/
│   └── pixel-agents-1.0.2.vsix  # Bundled Pixel Agents VSCode extension
├── docker-compose.yml            # Weaviate 1.35.7 container
├── pyproject.toml                # Python project configuration
└── .env.example
```

## Configuration

### Environment Variables

| Variable                 | Default                             | Description                                                                                   |
|--------------------------|-------------------------------------|-----------------------------------------------------------------------------------------------|
| `LLM_PROVIDER`           | `ollama`                            | `ollama`, `github_models`, or `openai` — controls the chat/reasoning model                    |
| `EMBEDDING_PROVIDER`     | `ollama`                            | `ollama` or `openai` — controls query embedding for vector search. Independent of `LLM_PROVIDER`; Ollama must be running even when LLM is OpenAI if embeddings use Ollama |
| `WEAVIATE_PORT`          | `8090`                              | Default port Weaviate HTTP endpoint                                                           |
| `WEAVIATE_URL`           | `http://localhost:${WEAVIATE_PORT}` | Weaviate HTTP endpoint                                                                        |
| `WEAVIATE_GRPC_PORT`     | `50061`                             | Default port Weaviate gRPC endpoint                                                           |
| `WEAVIATE_GRPC_URL`      | `localhost:${WEAVIATE_GRPC_PORT}`   | Weaviate gRPC endpoint                                                                        |
| `OLLAMA_URL`             | `http://localhost:11434`            | Ollama API                                                                                    |
| `OLLAMA_MODEL`           | `gpt-oss:20b`                       | Ollama chat model                                                                             |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text-v2-moe`           | Embedding model (all providers)                                                               |
| `GITHUB_MODELS_API_KEY`  | —                                   | Required when using `github_models` provider                                                  |
| `GITHUB_MODELS_MODEL`    | `openai/gpt-4.1`                    | GitHub CoPilot Models chat model                                                              |
| `OPENAI_API_KEY`         | —                                   | Required when using `openai` provider (not for company data)                                  |
| `OPENAI_CHAT_MODEL`      | `gpt-5.2`                           | OpenAI chat model                                                                             |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large`            | OpenAI embedding model                                                                        |
| `SKOSMOS_URL`            | `http://localhost:8080`             | SKOSMOS REST API endpoint for vocabulary lookups                                              |
| `GITHUB_TOKEN`           | —                                   | GitHub PAT for MCP file fetching (requires `repo` scope; authorize for org SSO if applicable) |
| `PERSONA_PROVIDER`       | —                                   | Override LLM provider for AInstein Persona only                                               |
| `RAG_PROVIDER`           | —                                   | Override LLM provider for RAG Agent only                                                      |
| `PIXEL_AGENTS_DIR`       | —                                   | Base directory for Pixel Agents extension (disabled if not set)                                |

Additional environment variables for timeout, retry, and operational limits are available in `src/aion/config.py`.

### Docker / Podman

Weaviate runs locally via Docker (or Podman). The `docker-compose.yml` configures:

- Weaviate 1.35.7 with text2vec-ollama and generative-ollama modules
- HTTP on port 8090, gRPC on port 50061
- Persistent storage via Docker volume

```bash
docker compose up -d         # Start
docker compose down          # Stop
docker compose down -v       # Stop and delete all data
```

> [!NOTE]
> the docker-compose.yml creates a local volume for Weaviate data 'esa-ainstein-artifacts_weaviate_data'.
> Be aware this can be a large volume and may require additional disk space, and that the volume needs to be deleted
> when the container is stopped.

**Podman users (Linux):** Use `podman-compose` instead of `docker compose`. If Ollama runs on the host, replace
`host.docker.internal` with the host's actual IP in `.env` — Podman doesn't support `host.docker.internal` by default.

## SKOSMOS Setup

SKOSMOS provides the vocabulary lookup service for ESA Architecture principles (ESAV vocabulary) and IEC/CIM/SKOS
concepts. It currently runs as a local Docker/Podman stack, until MCP integration with the production Fuseki instance at
`https://vocabs.alliander.com/` is implemented.

The SKOSMOS instance and its vocabulary data are maintained in a separate Alliander repository:

```bash
git clone git@github.com:Alliander/esa-odei-skosmos.git
cd esa-odei-skosmos
docker compose up -d
```

Then configure the endpoint in your AInstein `.env`:

```bash
SKOSMOS_URL=http://localhost:8080
```

> **Note:** Access to `Alliander/esa-odei-skosmos` requires an Alliander GitHub account (same as this repository).

AInstein will work without SKOSMOS, but vocabulary lookups (`skosmos_search`, `skosmos_concept_details`) will return
errors. All other features (ADR/PCP/policy search, ArchiMate generation) function independently.

## Conversation Memory

AInstein stores conversation history and session data in a local SQLite database (`chat_history.db`), created
automatically on first run. This enables:

- Persistent conversation history across restarts
- Rolling conversation summaries for multi-turn context (older turns summarized, recent turns verbatim)
- In-session recall — the Persona can retrieve content it wrote earlier in the conversation
- **RAG agent multi-turn reasoning** — the agent receives its own prior responses via Pydantic AI's
  `message_history`, enabling follow-up questions like "how many of these are X?" without contradicting itself.
  A registered `history_processor` caps history to the last 4 turn pairs and prepends a rolling summary for
  longer conversations.
- **Prior sources injection** — on follow-up queries, the previous turn's search results (stripped to lightweight
  identifiers) are injected into the RAG agent's context so it can answer counting/filtering questions without
  re-querying Weaviate
- Session management and user profiles

The Persona's conversation history window is configurable via `persona-orchestrator/references/thresholds.yaml` (
verbatim window size, message truncation). No additional setup is required — SQLite is part of the Python standard
library.

## Artifacts

When AInstein generates structured output (e.g., ArchiMate XML), it saves the content as an artifact in the same SQLite
database. The chat UI shows a download card with the filename, a summary (element/relationship counts), and download
buttons. ArchiMate artifacts show dual download buttons (XML + YAML); other artifacts show a single button. Artifacts
are accessible via:

- **Download card** in the chat UI (appears automatically after generation)
- **API endpoint** `GET /api/artifact/{id}/download` — returns the artifact content with the appropriate MIME type
- **File upload** — click the paperclip button to upload ArchiMate files (.xml, .yaml, .yml) for inspection and analysis
- **URL fetch** — paste a GitHub URL in the chat: file URLs (blob/raw) fetch via MCP, repo root URLs fetch metadata +
  README + directory listing, org/user URLs fetch profile + top repos via REST API. Non-GitHub URLs are fetched via
  httpx. Supports private repos when `GITHUB_TOKEN` is set.

Artifacts persist across sessions and can be loaded for refinement ("Add security constraints to the model") or
inspection ("Describe the model you just generated").

## Testing

### Unit tests

```bash
uv run pytest tests/ -v
```

### Regression queries

These queries should always produce correct results. Run via CLI before committing changes to agent or retrieval code:

```bash
uv run aion query "What ADRs exist in the system?"
uv run aion query "What PCPs exist in the system?"
uv run aion query "What are the consequences of [any ADR]?"
uv run aion query "What is document [N]?"              # tests disambiguation
```

### Chat UI tests (requires running server)

These test the Persona + agent pipeline end-to-end:

1. Identity: "Who are you?" → identity response, no KB search
2. Simple retrieval: "What is [any PCP]?" → concise summary with citations
3. Multi-step: "Compare [a PCP] with [an ADR]" → orchestrated retrieval + synthesis
4. Follow-up: after generation, "Why did you choose those elements?" → direct response from Persona
5. Abstention: "What's the budget for [any ADR]?" → clean two-sentence response

## Upgrading / Migration

### Mandatory re-indexing after upgrade

If you are upgrading from a previous version, you **must** recreate all Weaviate collections:

```bash
uv run aion init --recreate --chunked
# or for a fresh install:
uv run aion init --chunked
```

This is required because:

1. **SKOSMOS vocabulary moved out of Weaviate** — vocabulary concepts are now served via the SKOSMOS REST API instead of
   being embedded in Weaviate collections. The old vocabulary collection is no longer used.
2. **Data structure changes** — document metadata, chunking strategy, and collection schemas have changed. Notably,
   `dct_identifier` and `dct_issued` properties (Dublin Core metadata from frontmatter) require a schema update.
3. **Principle ownership corrected at ingestion time** — `owner_team_abbr` is now written correctly per-PCP at index
   time using `registry-index.md`. Without re-indexing, all 41 principles show `ESA` as owner regardless of their actual
   owning group (BA, DO, NB-EA, EA).
4. **Embedding model alignment** — all collections must use the same embedding model. If you switched embedding models,
   existing vectors are incompatible.

**Important:** The `--recreate` flag drops and recreates all collections, then re-ingests all data from `data/`. Without
it, `init` skips collections that already exist and **will not update the schema**. If you added new collection
properties (e.g., `dct_identifier`), you **must** use `--recreate` — otherwise the old schema is preserved and new
fields will be `None`.

## Known Limitations

**ArchiMate XML generation requires a cloud model.** Local models (GPT-OSS:20B via Ollama) handle KB retrieval,
vocabulary lookups, and text summarization well, but may refuse to generate structured ArchiMate XML. Switch to a cloud
model (e.g., GPT-5.2 via OpenAI) in the Chat UI settings before requesting ArchiMate generation. The generation pipeline
validates output, sanitizes common LLM XML errors (e.g., unescaped `&`), repairs missing view references (
elements/relationships without corresponding diagram nodes/connections), and retries on validation failure.

**Invalid model names produce clear errors.** If you configure a model name that doesn't exist on the provider (e.g., a
typo in the settings), the system surfaces a clear error message instead of silently degrading. Transient errors (
timeouts, rate limits) still fall back gracefully.

## Troubleshooting

**Weaviate won't start:**

```bash
docker ps                          # Check if running
docker logs weaviate-ainstein-dev  # Check logs
```

**Ollama models not found:**

```bash
ollama list                  # Check installed models
ollama pull nomic-embed-text-v2-moe
ollama pull gpt-oss:20b
```

**Skills not taking effect** — verify skills are enabled:

```bash
curl http://localhost:8081/api/skills | python -m json.tool
```

## Contact

**Maintained by the Energy System Architecture (ESA) Team at Alliander**

- Organization: [Alliander](https://www.alliander.com)
- Repository: [esa-ainstein-artifacts](https://github.com/Alliander/esa-ainstein-artifacts)

For questions or support, please [open an issue](https://github.com/Alliander/esa-ainstein-artifacts/issues) or contact
the ESA team.

