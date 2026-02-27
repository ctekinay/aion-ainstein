# AInstein

Agentic RAG and multi-skill AI system developed by Alliander's Energy System Architecture Group to support various architecture workstreams. Built on Weaviate (Vector DB) + Elysia decision trees with an AInstein Persona layer for intent classification and a Skills Framework for prompt engineering.

## What It Does

AInstein lets architects and engineers query Alliander's architecture knowledge base using natural language:

- **18 Architecture Decision Records (ADRs)** — design decisions with context, options, and consequences
- **31 Architecture Principles (PCPs)** — guiding statements for design choices
- **49 Decision Approval Records (DARs)** — governance and approval history
- **5,200+ SKOS Vocabulary Concepts** — IEC 61970/61968/62325 standards, CIM models, domain ontologies via SKOSMOS REST API
- **Policy Documents** — data governance, privacy, security policies
- **ArchiMate 3.2 Model Generation** — validated Open Exchange XML from architecture descriptions
- **SKOSMOS Vocabulary Lookups** — term definitions, abbreviations, concept hierarchies via structured API

Queries such as "What ADRs exist?", "What is document 22?", "Define active power", "Create an ArchiMate model for a web app", and "What are the consequences of ADR.29?" are handled by the AInstein Persona, which classifies intent, emits skill tags for domain-specific capabilities, and rewrites queries. The Elysia decision tree then selects the appropriate retrieval strategy — including SKOSMOS for vocabulary lookups and ArchiMate tools for model generation — disambiguates overlapping document numbers, and formats responses with proper citations.

**Disclaimer:** Currently, the above-mentioned data sources are integrated stand-alone via the data/ folder. The short-term goal for AInstein is full integration with ESA repositories, tools, and other internal data sources directly. 

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Web UI / CLI                                 │
│              localhost:8081  |  python -m src.aion.cli                    │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│                    AInstein Persona Layer                            │
│  Intent classification (retrieval, identity, off-topic, follow-up)   │
│  Query rewriting with conversation context (pronoun resolution)      │
│  Direct response for non-retrieval intents (no Tree needed)          │
└──────────────┬───────────────────────────────────────────────────────┘
               │ retrieval / follow-up
┌──────────────▼───────────────────────────────────────────────────────┐
│                      Elysia Decision Tree                            │
│  Routes queries to tools based on intent (list, lookup, summarize)   │
│  Atlas = injected skill content (identity, formatting, ontology)     │
├──────────────────────────────────────────────────────────────────────┤
│  Tools:                                                              │
│  search_architecture_decisions  search_principles  search_policies   │
│  list_all_adrs  list_all_principles  search_by_team                  │
│  get_collection_stats                                                │
│  skosmos_search  skosmos_concept_details  skosmos_list_vocabularies  │
│  validate_archimate  inspect_archimate_model  merge_archimate_view   │
├──────────────────────────────────────────────────────────────────────┤
│  Summarizers: cited_summarize                                        │
└──────────────┬───────────────────────────────────────────────────────┘
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
│  5,200+ SKOS concepts · IEC/CIM/EU vocabularies · ESAV terminology  │
│  skosmos_search → skosmos_concept_details → skosmos_list_vocabs     │
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
python -m src.aion.cli elysia                # Interactive Elysia session
python -m src.aion.cli status                # Show collection statistics
python -m src.aion.cli search "term"         # Direct hybrid search
python -m src.aion.cli evaluate              # Compare Ollama vs OpenAI quality
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

**How it works:** Always-on skills are concatenated and injected into the Elysia Tree's `atlas.agent_description` field before each query. On-demand skills are injected only when the Persona emits matching `skill_tags` (e.g., `["archimate"]` or `["vocabulary"]`). This keeps the prompt lean for standard KB queries while activating specialized knowledge when needed.

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
│   ├── chat_ui.py                # FastAPI web server + API endpoints + SQLite conversation store
│   ├── elysia_agents.py          # Elysia Tree integration, tool registration,
│   │                             #   skill injection, abstention
│   ├── tools/
│   │   ├── archimate.py          # ArchiMate 3.2 validation, inspection, merge
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

**ArchiMate XML generation requires a cloud model.** Local models (GPT-OSS:20B via Ollama) handle KB retrieval, vocabulary lookups, and text summarization well, but may refuse to generate structured ArchiMate XML. Switch to a cloud model (e.g., GPT-5.2 via OpenAI) in the Chat UI settings before requesting ArchiMate generation.

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