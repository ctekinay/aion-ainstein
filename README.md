# AInstein [![Alliander](https://img.shields.io/badge/maintained%20by-Alliander-orange.svg)](https://www.alliander.com)

Agentic RAG and multi-skill AI system developed by Alliander's Energy System Architecture Group to support various architecture workstreams. Built on Weaviate (Vector DB) + Elysia decision trees with an AInstein Persona layer for intent classification and a Skills Framework for prompt engineering.

## What It Does

AInstein lets architects and engineers query Alliander's architecture knowledge base using natural language:

- **18 Architecture Decision Records (ADRs)** — design decisions with context, options, and consequences
- **31 Architecture Principles (PCPs)** — guiding statements for design choices
- **49 Decision Approval Records (DARs)** — governance and approval history
- **5,200+ SKOS Vocabulary Concepts** — IEC 61970/61968/62325 standards, CIM models, domain ontologies via SKOSMOS REST API
- **Policy Documents** — data governance, privacy, security policies
- **ArchiMate 3.2 Model Generation** — validated Open Exchange XML from architecture descriptions
- **ArchiMate Model Inspection** — analyze, describe, and compare ArchiMate models from conversation artifacts, file uploads, or URLs
- **SKOSMOS Vocabulary Lookups** — term definitions, abbreviations, concept hierarchies via structured API

Queries are handled by the AInstein Persona, which classifies intent, emits skill tags for domain-specific capabilities, and rewrites queries. The Persona routes to the appropriate execution path:

- **Retrieval queries** ("What ADRs exist?", "What is document 22?", "Define active power") go to the **Elysia Decision Tree**, which selects tools, searches collections, and formats responses with citations.
- **Generation queries** ("Create an ArchiMate model for ADR.29") go to the **Generation Pipeline**, which fetches source content, builds a prompt from the matching skill, makes a single LLM call, validates, and saves the artifact for download. Token usage is tracked across all LLM calls (generation, view repair, validation retries) and reported in a single summary log line at completion.
- **Refinement queries** ("Add a Technology layer to the model") go to the **Generation Pipeline** with the previous artifact loaded as context. The LLM returns a structured YAML diff envelope (~200 tokens) instead of regenerating the full model (~4,600 tokens). A deterministic merge engine applies the diff; if parsing fails, the pipeline falls back transparently to full regeneration.
- **Inspection queries** ("Describe the model you just generated", "What elements are in this ArchiMate file?") go to the **Inspection path**, which converts XML to compact YAML (~90% token reduction), sends it to the LLM for analysis, and streams the response. Models can come from conversation artifacts, file uploads (.xml/.yaml), or URLs. GitHub URLs are fetched via MCP (Model Context Protocol) using the remote GitHub MCP server, with httpx fallback for non-GitHub URLs.
- **Direct response queries** ("Who are you?", "What's the weather?") are answered by the Persona without any backend call.

**Disclaimer:** Currently, the above-mentioned data sources are integrated stand-alone via the data/ folder. The short-term goal for AInstein is full integration with ESA repositories, tools, and other internal data sources directly. 

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Web UI / CLI                                 │
│              localhost:8081  |  python -m src.aion.cli               │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│                    AInstein Persona Layer                            │
│  Intent classification: retrieval, listing, follow_up, generation,   │
│    refinement, inspect, identity, off_topic, clarification           │
│  Query rewriting with conversation context (pronoun resolution)      │
│  Skill tag emission for on-demand capabilities                       │
│  Direct response for identity/off-topic/clarification                │
└──────────┬─────────────────────┬──────────────────────┬──────────────┘
           │ retrieval / listing │ generation /         │ inspect
           │ / follow_up         │ refinement           │
┌──────────▼─────────────────────▼────┐  ┌──────────────▼────────────────┐
│       Elysia Decision Tree          │  │      Generation Pipeline      │
│  Tool selection via LLM planner     │  │  Direct LLM call (no planner) │
│  Atlas = injected skill content     │  │  Skill-driven prompt building │
├─────────────────────────────────────┤  ├───────────────────────────────┤
│  Tools:                             │  │  1. Fetch source content      │
│  search_architecture_decisions      │  │  2. Load generation skill     │
│  search_principles                  │  │  3. Single LLM call           │
│  search_policies                    │  │  4. XML sanitization          │
│  list_all_adrs                      │  │  5. View repair (detect+fix)  │
│  list_all_principles                │  │  6. Validation (+ retry)      │
│  search_by_team                     │  │  7. Save artifact to SQLite   │
│  get_collection_stats               │  │  8. Emit download card (SSE)  │
│  skosmos_search                     │  ├───────────────────────────────┤
│  skosmos_concept_details            │  │  Refinement: YAML diff merge  │
│  skosmos_list_vocabularies          │  │  with full-regen fallback     │
│  validate_archimate                 │  └───────────────┬───────────────┘
│  inspect_archimate_model            │                  │
│  merge_archimate_view               │           ┌──────▼──────────┐
│  save_artifact  get_artifact        │           │   Artifacts     │
├─────────────────────────────────────┤  ▼────────┤  SQLite store   │
│  Summarizers: cited_summarize       │  │        │  SSE download   │
└──────────────┬──────────────────────┘  │        │  card + API     │
               │                         │        │  File upload    │
               │                         │        └─────────────────┘
               │                         │
               │              ┌──────────┴──────────┐
               │              │     Inspection      │
               │              │  XML → YAML → LLM   │
               │              │  Sources: artifact, │
               │              │  upload, URL (MCP/  │
               │              │  httpx)             │
               │              └─────────────────────┘
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
│  │ Numbered lists, │ │ Scope, persona   │                            │
│  │ follow-ups      │ │ rules            │                            │
│  └─────────────────┘ └──────────────────┘                            │
│                                                                      │
│  On-demand skills (injected when Persona emits matching tags)        │
│  ┌─────────────────┐ ┌──────────────────┐ ┌──────────────────────┐   │
│  │ archimate-      │ │ archimate-view-  │ │ skosmos-             │   │
│  │ generator       │ │ generator        │ │ vocabulary           │   │
│  │ ArchiMate 3.2   │ │ View layout +    │ │ SKOSMOS REST API     │   │
│  │ XML generation  │ │ merge            │ │ term definitions     │   │
│  │ tag: archimate  │ │ tag: archimate   │ │ tag: vocabulary      │   │
│  └─────────────────┘ └──────────────────┘ └──────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│                        Weaviate 1.35.7                               │
│  ┌──────────────────┐ ┌───────────┐ ┌──────────────┐                 │
│  │ Architectural    │ │ Principle │ │ Policy       │                 │
│  │ Decision  18+49  │ │ 31+31     │ │ Document     │                 │
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
│  Per-component overrides: PERSONA_PROVIDER / TREE_PROVIDER           │
└──────────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Clone and enter
git clone <your-fork-url>
cd esa-ainstein-artifacts

# 2. Start Weaviate
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
python -m src.aion.cli init
python -m src.aion.cli chat --port 8081
# Open http://localhost:8081
```

## Prerequisites

- **Docker** — for Weaviate vector database and SKOSMOS vocabulary service
- **Python 3.11-3.12** (3.10 and 3.13+ not supported)
- **Ollama** (default, local, free) — [ollama.ai/download](https://ollama.ai/download)
- **SKOSMOS** — vocabulary lookup service (runs separately via Docker, see [SKOSMOS Setup](#skosmos-setup))
- Or **GitHub CoPilot Models** (Alliander Enterprise Account, 8K token limit) — set `LLM_PROVIDER=github_models` and `GITHUB_MODELS_API_KEY` in `.env`
- Or **OpenAI API key** (cloud, paid — do not use with company data) — set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` in `.env`

## CLI Commands

```bash
python -m src.aion.cli init                  # Initialize collections and ingest data
python -m src.aion.cli init --chunked        # Ingest with section-based chunking
python -m src.aion.cli init --recreate       # Recreate collections from scratch
python -m src.aion.cli chat --port 8081      # Start web UI
python -m src.aion.cli query "question"      # Single query from terminal (bypasses AInstein Persona)
```

## Web UI

The chat interface at `http://localhost:8081` provides:

- **Chat** — conversational RAG with AInstein Persona intent classification and citations
- **Settings** — model selection, temperature, comparison mode
- **Skills** (`/skills`) — enable/disable skills, tune abstention threshold, edit SKILL.md content

## Skills Framework

Skills are markdown instruction files injected into every LLM prompt. They control how AInstein behaves — identity, formatting, citation rules, domain knowledge. Skills are managed via the `/skills` UI or by editing files directly.

```
skills/
├── skills-registry.yaml             # Which skills are enabled + on-demand tags
├── persona-orchestrator/
│   └── SKILL.md                     # AInstein Persona system prompt, intent classification, skill tags
├── ainstein-identity/
│   └── SKILL.md                     # Identity, scope, persona rules
├── rag-quality-assurance/
│   ├── SKILL.md                     # Citation format, abstention rules
│   └── references/thresholds.yaml   # Distance threshold, retrieval limits
├── esa-document-ontology/
│   └── SKILL.md                     # ADR/PCP/DAR naming, numbering, disambiguation
├── response-formatter/
│   └── SKILL.md                     # Numbered lists, statistics, follow-up options
├── archimate-generator/             # On-demand (tag: archimate)
│   ├── SKILL.md                     # ArchiMate 3.2 XML generation workflow
│   └── references/                  # Element types, allowed relations
├── archimate-view-generator/        # On-demand (tag: archimate)
│   ├── SKILL.md                     # View layout and merge workflow
│   └── references/                  # View layout rules
└── skosmos-vocabulary/              # On-demand (tag: vocabulary)
    └── SKILL.md                     # SKOSMOS REST API search and concept lookup
```

**Progressive Skill Loading:** Skills use two injection modes to minimize token usage:

- **Always-on** — core skills (identity, quality assurance, document ontology, response formatting) are injected into every prompt via the Elysia Tree's `atlas.agent_description`. These apply to all query types.
- **On-demand** — domain-specific skills (ArchiMate generation, ArchiMate views, SKOSMOS vocabulary) are injected only when the Persona emits matching `skill_tags` (e.g., `["archimate"]` or `["vocabulary"]`). A standard KB query like "What ADRs exist?" never loads the ArchiMate generation skill (~10K chars) or SKOSMOS vocabulary rules.

This reduces prompt size by 40-80% for standard queries compared to loading all skills on every call. The Generation Pipeline loads only the matching generation skill (e.g., `archimate-generator`) — not the always-on skills — since it operates outside the Tree's retrieval context.

**Thresholds:** The `rag-quality-assurance` skill has a `thresholds.yaml` that controls:
- `abstention.distance_threshold` (0.5) — maximum vector distance before abstaining
- `retrieval_limits` — max documents per collection (per-tool override at call time)
- `truncation` — content length limits (per-tool override at call time)

## Project Structure

```
esa-ainstein-artifacts/
├── src/aion/
│   ├── cli.py                    # Typer CLI (init, chat, query, evaluate)
│   ├── config.py                 # Pydantic settings from .env (3-provider config)
│   ├── persona.py                # AInstein Persona — intent classification, query rewriting
│   ├── generation.py             # Direct LLM generation pipeline (ArchiMate XML, etc.)
│   ├── chat_ui.py                # FastAPI web server + API endpoints + SQLite conversation store
│   │                             #   Execution router: generation → pipeline, retrieval → Tree
│   ├── elysia_agents.py          # Elysia Tree integration, tool registration,
│   │                             #   skill injection, abstention
│   ├── mcp/
│   │   ├── config.yaml           # MCP server registry (URLs, auth, transport)
│   │   ├── registry.py           # MCPServerConfig + load_registry() + get_server()
│   │   ├── client.py             # Generic MCP client (streamable HTTP transport)
│   │   └── github.py             # GitHub file fetching + URL parsing
│   ├── tools/
│   │   ├── archimate.py          # ArchiMate 3.2 validation, inspection, merge
│   │   ├── yaml_to_xml.py        # ArchiMate YAML ↔ XML converter (generation + inspection)
│   │   └── skosmos.py            # SKOSMOS REST API wrappers (search, concept details)
│   ├── weaviate/
│   │   ├── client.py             # Weaviate connection factory
│   │   ├── collections.py        # Collection schema definitions
│   │   ├── embeddings.py         # Ollama embedding functions
│   │   └── ingestion.py          # Data ingestion pipeline
│   ├── loaders/
│   │   ├── markdown_loader.py    # ADR/PCP markdown parser with frontmatter
│   │   ├── document_loader.py    # DOCX/PDF parser for policies
│   │   └── registry_parser.py    # ESA registry table parser
│   ├── chunking/                 # Section-based document chunking
│   ├── memory/
│   │   ├── session_store.py      # SQLite session management, user profiles
│   │   ├── summarizer.py         # Rolling conversation summaries
│   │   └── cli.py                # Memory management CLI (show, reset, export)
│   ├── skills/
│   │   ├── __init__.py           # Package init, get_skill_registry()
│   │   ├── loader.py             # SkillLoader: parses SKILL.md, loads thresholds
│   │   ├── registry.py           # SkillRegistry: enabled/disabled state, content injection
│   │   ├── api.py                # Skills CRUD API (list, get, toggle, update)
│   │   └── filters.py            # Query-based skill filtering (unused, kept for reference)
│   ├── evaluation/               # RAG quality evaluation framework
│   └── static/
│       ├── index.html            # Main chat UI
│       └── skills.html           # Skills management UI
├── skills/                       # Skill definitions (SKILL.md + thresholds.yaml)
├── docker-compose.yml            # Weaviate 1.35.7 container
├── pyproject.toml                # Python project configuration
└── .env.example
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama`, `github_models`, or `openai` |
| `WEAVIATE_URL` | `http://localhost:8090` | Weaviate HTTP endpoint |
| `WEAVIATE_GRPC_URL` | `localhost:50061` | Weaviate gRPC endpoint |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API |
| `OLLAMA_MODEL` | `gpt-oss:20b` | Ollama chat model |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text-v2-moe` | Embedding model (all providers) |
| `GITHUB_MODELS_API_KEY` | — | Required when using `github_models` provider |
| `GITHUB_MODELS_MODEL` | `openai/gpt-4.1` | GitHub CoPilot Models chat model |
| `OPENAI_API_KEY` | — | Required when using `openai` provider (not for company data) |
| `OPENAI_CHAT_MODEL` | `gpt-5.2` | OpenAI chat model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large` | OpenAI embedding model |
| `SKOSMOS_URL` | `http://localhost:8080` | SKOSMOS REST API endpoint for vocabulary lookups |
| `GITHUB_TOKEN` | — | GitHub PAT for MCP file fetching (requires `repo` scope; authorize for org SSO if applicable) |
| `PERSONA_PROVIDER` | — | Override LLM provider for AInstein Persona only |
| `TREE_PROVIDER` | — | Override LLM provider for Elysia Tree only |

### Docker

Weaviate runs locally via Docker. The `docker-compose.yml` configures:
- Weaviate 1.35.7 with text2vec-ollama and generative-ollama modules
- HTTP on port 8090, gRPC on port 50061
- Persistent storage via Docker volume

```bash
docker compose up -d         # Start
docker compose down          # Stop
docker compose down -v       # Stop and delete all data
```

## SKOSMOS Setup

SKOSMOS provides the vocabulary lookup service (5,200+ IEC/CIM/SKOS concepts). It runs as a separate Docker container and is accessed via REST API.

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

AInstein will work without SKOSMOS, but vocabulary lookups (`skosmos_search`, `skosmos_concept_details`) will return errors. All other features (ADR/PCP/policy search, ArchiMate generation) function independently.

## Conversation Memory

AInstein stores conversation history and session data in a local SQLite database (`chat_history.db`), created automatically on first run. This enables:

- Persistent conversation history across restarts
- Rolling conversation summaries for multi-turn context
- Session management and user profiles

No additional setup is required — SQLite is part of the Python standard library.

## Artifacts

When AInstein generates structured output (e.g., ArchiMate XML), it saves the content as an artifact in the same SQLite database. The chat UI shows a download card with the filename, a summary (element/relationship counts), and download buttons. ArchiMate artifacts show dual download buttons (XML + YAML); other artifacts show a single button. Artifacts are accessible via:

- **Download card** in the chat UI (appears automatically after generation)
- **API endpoint** `GET /api/artifact/{id}/download` — returns the artifact content with the appropriate MIME type
- **File upload** — click the paperclip button to upload ArchiMate files (.xml, .yaml, .yml) for inspection and analysis
- **URL fetch** — paste a GitHub URL (blob or raw) or any file URL to an ArchiMate file in the chat; GitHub URLs are fetched via MCP (authenticated, supports private repos), others via httpx

Artifacts persist across sessions and can be loaded for refinement ("Add security constraints to the model") or inspection ("Describe the model you just generated").

## Upgrading / Migration

### Mandatory re-indexing after upgrade

If you are upgrading from a previous version, you **must** recreate all Weaviate collections:

```bash
python -m src.aion.cli init --recreate
```

This is required because:

1. **SKOSMOS vocabulary moved out of Weaviate** — vocabulary concepts are now served via the SKOSMOS REST API instead of being embedded in Weaviate collections. The old vocabulary collection is no longer used.
2. **Data structure changes** — document metadata, chunking strategy, and collection schemas have changed.
3. **Embedding model alignment** — all collections must use the same embedding model. If you switched embedding models, existing vectors are incompatible.

The `--recreate` flag drops and recreates all collections, then re-ingests all data from `data/`. Without it, `init` skips collections that already exist.

## Known Limitations

**ArchiMate XML generation requires a cloud model.** Local models (GPT-OSS:20B via Ollama) handle KB retrieval, vocabulary lookups, and text summarization well, but may refuse to generate structured ArchiMate XML. Switch to a cloud model (e.g., GPT-5.2 via OpenAI) in the Chat UI settings before requesting ArchiMate generation. The generation pipeline validates output, sanitizes common LLM XML errors (e.g., unescaped `&`), repairs missing view references (elements/relationships without corresponding diagram nodes/connections), and retries on validation failure.

**Invalid model names produce clear errors.** If you configure a model name that doesn't exist on the provider (e.g., a typo in the settings), the system surfaces a clear error message instead of silently degrading. Transient errors (timeouts, rate limits) still fall back gracefully.

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

**Elysia gRPC errors** — the system falls back to direct query mode automatically. To reset Elysia metadata:
```python
import weaviate
client = weaviate.connect_to_local()
if client.collections.exists("ELYSIA_METADATA__"):
    client.collections.delete("ELYSIA_METADATA__")
client.close()
```

**Skills not taking effect** — verify skills are enabled:
```bash
curl http://localhost:8081/api/skills | python -m json.tool
```
## Contact
**Maintained by the Energy System Architecture (ESA) Team at Alliander**

- Organization: [Alliander](https://www.alliander.com)
- Repository: [esa-ainstein-artifacts](https://github.com/Alliander/esa-ainstein-artifacts)

For questions or support, please [open an issue](https://github.com/Alliander/esa-ainstein-artifacts/issues) or contact the ESA team.

