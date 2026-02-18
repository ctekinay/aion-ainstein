# AInstein

Agentic RAG system for querying Energy System Architecture knowledge bases. Built on Weaviate + Elysia decision trees with a Skills Framework for prompt engineering.

## What It Does

AInstein lets architects and engineers query Alliander's architecture knowledge base using natural language:

- **18 Architecture Decision Records (ADRs)** — design decisions with context, options, and consequences
- **31 Architecture Principles (PCPs)** — guiding statements for design choices
- **49 Decision Approval Records (DARs)** — governance and approval history
- **5,200+ SKOS/OWL Vocabulary Concepts** — IEC 61970/61968/62325 standards, CIM models, domain ontologies
- **Policy Documents** — data governance, privacy, security policies

Queries like "What ADRs exist?", "What is document 22?", "Who approved ADR.12?", and "Consequences of ADR.29?" are handled through an agentic decision tree that selects the right retrieval strategy, disambiguates overlapping document numbers, and formats responses with proper citations.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Web UI / CLI                                  │
│              localhost:8081  |  python -m src.cli                     │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│                      Elysia Decision Tree                            │
│  Routes queries to tools based on intent (list, lookup, summarize)   │
│  Atlas = injected skill content (identity, formatting, ontology)     │
├──────────────────────────────────────────────────────────────────────┤
│  Tools:                                                              │
│  search_vocabulary  search_architecture_decisions  search_principles  │
│  search_policies    list_all_adrs    list_all_principles             │
│  search_by_team     get_collection_stats                             │
├──────────────────────────────────────────────────────────────────────┤
│  Summarizers: cited_summarize  (monkey-patched to respect skills)    │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│                     Skills Framework                                  │
│  Enabled skills are injected into every LLM prompt via atlas          │
│  ┌─────────────────┐ ┌──────────────────┐ ┌──────────────────────┐   │
│  │ rag-quality-    │ │ esa-document-    │ │ response-formatter   │   │
│  │ assurance       │ │ ontology         │ │                      │   │
│  │ Anti-hallucin.  │ │ ADR/PCP/DAR      │ │ Numbered lists,      │   │
│  │ Citation rules  │ │ disambiguation   │ │ statistics, follow-  │   │
│  │ Identity rules  │ │ ID aliases       │ │ up suggestions       │   │
│  └─────────────────┘ └──────────────────┘ └──────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│                        Weaviate 1.35.7                                │
│  ┌────────────┐ ┌──────────────────┐ ┌───────────┐ ┌──────────────┐ │
│  │ Vocabulary │ │ Architectural    │ │ Principle │ │ Policy       │ │
│  │ 5,200+     │ │ Decision  18+49  │ │ 31+31     │ │ Document     │ │
│  │ concepts   │ │ ADRs + DARs      │ │ PCPs+DARs │ │ 76 chunks    │ │
│  └────────────┘ └──────────────────┘ └───────────┘ └──────────────┘ │
│  Hybrid search: BM25 keyword + vector similarity                     │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│                      LLM Provider                                     │
│  ┌──────────────────────┐    ┌────────────────────────────────────┐  │
│  │ Ollama (default)     │    │ OpenAI (alternative)               │  │
│  │ Embed: nomic-v2-moe  │    │ Embed: text-embedding-3-small     │  │
│  │ Chat: gpt-oss:20b    │    │ Chat: gpt-4o-mini                 │  │
│  │ Local, free           │    │ Cloud, paid                       │  │
│  └──────────────────────┘    └────────────────────────────────────┘  │
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

# 4. Python environment
python3 -m venv venv312
source venv312/bin/activate
pip install -r requirements.txt

# 5. Configure
cp .env.example .env
# Default uses Ollama — no changes needed

# 6. Initialize and run
python -m src.cli init
python -m src.cli chat --port 8081
# Open http://localhost:8081
```

## Prerequisites

- **Docker** — for Weaviate vector database
- **Python 3.10-3.12** (3.13+ not supported)
- **Ollama** (default, local, free) — [ollama.ai/download](https://ollama.ai/download)
- Or **OpenAI API key** (cloud, paid) — set `LLM_PROVIDER=openai` in `.env`

## CLI Commands

```bash
python -m src.cli init                  # Initialize collections and ingest data
python -m src.cli init --chunked        # Ingest with section-based chunking
python -m src.cli init --recreate       # Recreate collections from scratch
python -m src.cli chat --port 8081      # Start web UI
python -m src.cli query "question"      # Single query from terminal
python -m src.cli elysia                # Interactive Elysia session
python -m src.cli status                # Show collection statistics
python -m src.cli search "term"         # Direct hybrid search
python -m src.cli evaluate              # Compare Ollama vs OpenAI quality
```

## Web UI

The chat interface at `http://localhost:8081` provides:

- **Chat** — conversational RAG with citations and source cards
- **Settings** — model selection, temperature, comparison mode
- **Skills** (`/skills`) — enable/disable skills, tune abstention threshold, edit SKILL.md content
- **Test Mode** — side-by-side Ollama vs OpenAI comparison

## Skills Framework

Skills are markdown instruction files injected into every LLM prompt. They control how AInstein behaves — identity, formatting, citation rules, domain knowledge. Skills are managed via the `/skills` UI or by editing files directly.

```
skills/
├── registry.yaml                    # Which skills are enabled
├── rag-quality-assurance/
│   ├── SKILL.md                     # Identity rules, citation format, abstention
│   └── references/thresholds.yaml   # Distance threshold for abstention
├── esa-document-ontology/
│   └── SKILL.md                     # ADR/PCP/DAR naming, numbering, disambiguation
├── response-formatter/
│   └── SKILL.md                     # Numbered lists, statistics, follow-up options
└── response-contract/
    └── SKILL.md                     # Structured JSON output (disabled by default)
```

**How it works:** Enabled skills are concatenated and set on the Elysia Tree's `atlas.agent_description` field before each query. This means every `ElysiaChainOfThought` prompt — including decision nodes and summarizers — sees the skill content alongside the retrieved documents and user query.

**Thresholds:** The `rag-quality-assurance` skill has a `thresholds.yaml` that controls:
- `abstention.distance_threshold` (0.5) — maximum vector distance before abstaining
- `retrieval_limits` — max documents per collection (not yet wired)
- `truncation` — content length limits (not yet wired)

## Project Structure

```
esa-ainstein-artifacts/
├── src/
│   ├── cli.py                    # Typer CLI (init, chat, query, evaluate)
│   ├── config.py                 # Pydantic settings from .env
│   ├── chat_ui.py                # FastAPI web server + API endpoints
│   ├── elysia_agents.py          # Elysia Tree integration, tool registration,
│   │                             #   skill injection, prompt patching, abstention
│   ├── agents/                   # Legacy multi-agent system (orchestrator, vocab, etc.)
│   ├── weaviate/
│   │   ├── client.py             # Weaviate connection factory
│   │   ├── collections.py        # Collection schema definitions
│   │   ├── embeddings.py         # Ollama/OpenAI embedding functions
│   │   └── ingestion.py          # Data ingestion pipeline
│   ├── loaders/
│   │   ├── rdf_loader.py         # SKOS/OWL/RDF parser (70+ ontology files)
│   │   ├── markdown_loader.py    # ADR/PCP markdown parser with frontmatter
│   │   ├── document_loader.py    # DOCX/PDF parser for policies
│   │   └── registry_parser.py    # ESA registry table parser
│   ├── chunking/                 # Section-based document chunking
│   ├── skills/
│   │   ├── __init__.py           # Package init, get_skill_registry()
│   │   ├── loader.py             # SkillLoader: parses SKILL.md, loads thresholds
│   │   ├── registry.py           # SkillRegistry: enabled/disabled state, content injection
│   │   ├── api.py                # Skills CRUD API (list, get, toggle, update)
│   │   └── filters.py            # Query-based skill filtering (unused, kept for reference)
│   ├── evaluation/               # RAG quality evaluation framework
│   ├── diagnostics/              # Retrieval debugging tools
│   └── static/
│       ├── index.html            # Main chat UI
│       └── skills.html           # Skills management UI
├── skills/                       # Skill definitions (SKILL.md + thresholds.yaml)
├── data/
│   ├── esa-skosmos/              # RDF/SKOS vocabularies (IEC standards)
│   ├── esa-main-artifacts/doc/   # ADRs (decisions/) and PCPs (principles/)
│   ├── do-artifacts/             # Data Office policies and principles
│   └── general-artifacts/        # Privacy and security policies
├── docker-compose.yml            # Weaviate 1.35.7 container
├── requirements.txt
└── .env.example
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama` or `openai` |
| `WEAVIATE_URL` | `http://localhost:8080` | Weaviate HTTP endpoint |
| `WEAVIATE_GRPC_URL` | `localhost:50051` | Weaviate gRPC endpoint |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API |
| `OLLAMA_MODEL` | `gpt-oss:20b` | Chat model |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text-v2-moe` | Embedding model |
| `OPENAI_API_KEY` | — | Required when `LLM_PROVIDER=openai` |

### Docker

Weaviate runs locally via Docker. The `docker-compose.yml` configures:
- Weaviate 1.35.7 with text2vec-ollama and text2vec-openai vectorizers
- HTTP on port 8090, gRPC on port 50061
- Persistent storage via Docker volume

```bash
docker compose up -d        # Start
docker compose down          # Stop
docker compose down -v       # Stop and delete all data
```

## Key Design Decisions

**Elysia Tree as Router**: The decision tree picks tools (search, list, summarize) based on the query. Skills are prompt content, not routing logic — the LLM decides what's relevant.

**Atlas Injection**: Skill content is set on `tree_data.atlas.agent_description` before each `tree.run()`. This reaches all `ElysiaChainOfThought` prompts including summarizers.

**Prompt Patching**: Elysia's `CitedSummarizingPrompt` has a hardcoded "do not give an itemised list" instruction. We monkey-patch this at import time to say "format according to agent description guidelines" — letting our response-formatter skill control output format.

**Abstention in Code**: The system abstains from answering when vector distances exceed the threshold or when a specific ADR number isn't found in results. This is done in `elysia_agents.py:should_abstain()`, not in the LLM prompt.

**Dual Provider Support**: Collections exist with and without `_OpenAI` suffix. The system automatically appends the suffix when `LLM_PROVIDER=openai`.

## Troubleshooting

**Weaviate won't start:**
```bash
docker ps                    # Check if running
docker logs weaviate-aion-dev  # Check logs
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

## License

MIT License
