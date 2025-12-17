# AION-AINSTEIN

Multi-Agent RAG (Retrieval-Augmented Generation) System for Energy System Architecture knowledge bases.

## Overview

AION-AINSTEIN is a local Weaviate-based RAG system with OpenAI embeddings that enables intelligent querying of energy sector knowledge bases including:

- **SKOS/RDF Vocabularies**: IEC 61970/61968/62325 standards, CIM models, and domain ontologies
- **Architectural Decision Records (ADRs)**: Design decisions and rationale
- **Data Governance Policies**: Compliance, data quality, security, privacy, and management policies
- **Architecture Principles**: System design and governance principles

The system integrates with [Weaviate's Elysia](https://weaviate.io/blog/elysia-agentic-rag) framework - a decision tree-based agentic RAG system that dynamically selects tools and processes queries.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    OrchestratorAgent                        │
│         (Routes queries to specialized agents)              │
└───────────────┬─────────────────┬─────────────────┬─────────┘
                │                 │                 │
    ┌───────────▼───┐   ┌────────▼────────┐   ┌────▼────────┐
    │ Vocabulary    │   │  Architecture   │   │   Policy    │
    │    Agent      │   │     Agent       │   │    Agent    │
    │               │   │                 │   │             │
    │ SKOS/OWL      │   │ ADRs &          │   │ Governance  │
    │ Concepts      │   │ Principles      │   │ Policies    │
    └───────────────┘   └─────────────────┘   └─────────────┘
                │                 │                 │
    ┌───────────▼─────────────────▼─────────────────▼─────────┐
    │                    Weaviate (Local Docker)              │
    │                      Version 1.28.2                     │
    │  ┌──────────┐  ┌──────────────────┐  ┌───────────────┐ │
    │  │Vocabulary│  │ArchitecturalDec. │  │PolicyDocument │ │
    │  │Collection│  │  Collection      │  │  Collection   │ │
    │  └──────────┘  └──────────────────┘  └───────────────┘ │
    └─────────────────────────────────────────────────────────┘
                              │
    ┌─────────────────────────▼───────────────────────────────┐
    │                    OpenAI API                           │
    │         Embeddings: text-embedding-3-small              │
    │         Generation: gpt-4o-mini                         │
    └─────────────────────────────────────────────────────────┘
```

## Prerequisites

- **Docker Desktop** (with WSL2 on Windows)
- **Python 3.10+** (3.12 recommended)
- **OpenAI API Key**

## Quick Start (Windows)

### 1. Start Weaviate

```powershell
docker compose up -d
```

### 2. Install Python Dependencies

```powershell
# Create virtual environment
python -m venv .venv312

# Activate it
.\.venv312\Scripts\Activate.ps1

# Install dependencies
pip install -e .
```

### 3. Configure Environment

```powershell
# Copy example configuration
Copy-Item .env.example .env

# Edit and add your OpenAI API key
notepad .env
```

Add your API key to `.env`:
```
OPENAI_API_KEY=sk-your-api-key-here
```

### 4. Initialize and Ingest Data

```powershell
# Initialize collections and ingest all data
python -m src.cli init

# Recreate collections and re-ingest (if needed)
python -m src.cli init --recreate

# Check status
python -m src.cli status
```

### 5. Query the System

```powershell
# Interactive mode (multi-agent)
python -m src.cli interactive

# Elysia mode (recommended - decision tree-based)
python -m src.cli elysia

# Single query
python -m src.cli query "What is the CIM model?"

# Query specific agent
python -m src.cli query "What decisions have been made about security?" --agent architecture

# Search directly
python -m src.cli search "data quality" --collection policy
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `python -m src.cli init` | Initialize Weaviate collections and ingest data |
| `python -m src.cli init --recreate` | Recreate collections and re-ingest all data |
| `python -m src.cli status` | Show collection status and document counts |
| `python -m src.cli query <question>` | Query the multi-agent system |
| `python -m src.cli search <text>` | Direct search across collections |
| `python -m src.cli agents` | List available agents |
| `python -m src.cli interactive` | Start interactive query session |
| `python -m src.cli elysia` | Start Elysia agentic RAG session (decision tree) |
| `python -m src.cli start-elysia-server` | Launch full Elysia web application |
| `python -m src.cli config` | Show current configuration |

### Query Options

```powershell
# Use specific agent
python -m src.cli query "question" --agent vocabulary
python -m src.cli query "question" --agent architecture
python -m src.cli query "question" --agent policy

# Use all agents
python -m src.cli query "question" --all

# Verbose output with sources
python -m src.cli query "question" --verbose
```

### Interactive Mode Commands

Once in interactive mode (`python -m src.cli interactive`):

```
@vocabulary <question>    Query only vocabulary agent
@architecture <question>  Query only architecture agent
@policy <question>        Query only policy agent
@all <question>           Query all agents
agents                    List available agents
status                    Show collection status
help                      Show help
quit                      Exit
```

### Elysia Mode (Recommended)

Elysia provides a decision tree-based agentic system that dynamically selects the right tools:

```powershell
# Start Elysia interactive mode
python -m src.cli elysia
```

Available tools in Elysia mode:
- `search_vocabulary` - Search SKOS concepts and IEC standards
- `search_architecture_decisions` - Search ADRs
- `search_principles` - Search architecture principles
- `search_policies` - Search governance policies (including privacy and security)
- `list_all_adrs` - List all ADRs
- `list_all_principles` - List all principles
- `get_collection_stats` - Get system statistics

For the full Elysia web experience with dynamic data display:
```powershell
# Using PowerShell script
.\start_elysia.ps1

# Stop the server
.\stop_elysia.ps1

# Or using CLI
python -m src.cli start-elysia-server
```

## Project Structure

```
aion-ainstein/
├── data/                           # Knowledge base data
│   ├── esa-skosmos/               # RDF/SKOS vocabularies (IEC standards)
│   ├── esa-main-artifacts/        # ADRs and architecture principles
│   │   └── doc/
│   │       ├── decisions/         # Architectural Decision Records
│   │       └── principles/        # Architecture principles
│   ├── do-artifacts/              # Domain-specific governance
│   │   ├── policy_docs/           # Data governance policies (DOCX/PDF)
│   │   └── principles/            # Governance principles
│   └── general-artifacts/         # General organizational policies
│       └── policies/              # Privacy and security policies (PDF)
├── knowledge/                      # Agent instruction templates
│   ├── compile-architecture-principles-EN.md
│   └── interact-with-open-archimate-file.md
├── other/                          # Reference documentation
│   ├── Elysia_Architecture.jpg
│   └── Elysia_Building an end-to-end agentic RAG app.docx
├── src/
│   ├── agents/                    # Multi-agent system
│   │   ├── base.py               # Base agent class
│   │   ├── vocabulary_agent.py   # SKOS/vocabulary queries
│   │   ├── architecture_agent.py # ADR and principle queries
│   │   ├── policy_agent.py       # Policy document queries
│   │   └── orchestrator.py       # Query routing
│   ├── loaders/                   # Data loaders
│   │   ├── rdf_loader.py         # SKOS/OWL/RDF parser
│   │   ├── markdown_loader.py    # ADR and principle parser
│   │   └── document_loader.py    # DOCX/PDF parser
│   ├── weaviate/                  # Weaviate integration
│   │   ├── client.py             # Connection management
│   │   ├── collections.py        # Schema definitions
│   │   └── ingestion.py          # Data ingestion pipeline
│   ├── config.py                  # Configuration management
│   ├── cli.py                     # CLI interface
│   └── elysia_agents.py           # Elysia integration with fallback
├── start_elysia.ps1               # Start Elysia web server (Windows)
├── stop_elysia.ps1                # Stop Elysia web server (Windows)
├── docker-compose.yml             # Weaviate container config
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## Configuration

Environment variables (`.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `WEAVIATE_URL` | `http://localhost:8080` | Weaviate HTTP endpoint |
| `WEAVIATE_GRPC_URL` | `localhost:50051` | Weaviate gRPC endpoint |
| `OPENAI_API_KEY` | (required) | Your OpenAI API key |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` | Chat model |

## Data Sources

### SKOS Vocabularies (5,200+ concepts)
- IEC 61970 (CIM for energy management)
- IEC 61968 (CIM for distribution management)
- IEC 62325 (CIM for energy markets)
- IEC 62746 (Distributed energy resources)
- ACER, ENTSOE-HEMRM, EUR-Lex regulatory terms
- PAS1879, FOCP2025, PPT2025 standards

### Architectural Decisions (17 ADRs)
- Documentation conventions
- Security and authentication (TLS, OAuth 2.0)
- Integration standards (CIM, demand response)
- Decision-making processes (DACI)

### Governance Principles (16 principles)
- Architecture principles (ESA)
- Data governance principles (data as asset, availability, etc.)

### Policy Documents (76 document chunks from 10 files)
- **Domain policies**: Data governance, classification, quality management
- **General policies**: Privacy policy, strategic security policy
- Capability documentation (metadata, master data, interoperability)

## Python API Usage

```python
import asyncio
from src.weaviate.client import weaviate_client
from src.agents import OrchestratorAgent

async def main():
    with weaviate_client() as client:
        orchestrator = OrchestratorAgent(client)

        # Query all agents
        response = await orchestrator.query(
            "What are the key data governance principles?"
        )
        print(response.answer)

        # Query specific agent
        response = await orchestrator.query(
            "What is IEC 61970?",
            agent_names=["vocabulary"]
        )
        print(response.answer)

asyncio.run(main())
```

### Using Elysia Directly

```python
from src.weaviate.client import get_weaviate_client
from src.elysia_agents import ElysiaRAGSystem

client = get_weaviate_client()
elysia = ElysiaRAGSystem(client)

# Query with automatic tool selection
import asyncio
response, objects = asyncio.run(elysia.query("What is the privacy policy?"))
print(response)

client.close()
```

## Troubleshooting

### Docker issues on Windows

```powershell
# Check if container is running
docker ps

# View logs
docker logs weaviate-aion

# Restart services
docker compose restart
```

### Weaviate connection issues

```powershell
# Test Weaviate is responding
Invoke-WebRequest -Uri "http://localhost:8080/v1/.well-known/ready"

# Check gRPC port
Test-NetConnection -ComputerName localhost -Port 50051
```

### Elysia gRPC errors

If you encounter gRPC errors like `proto: invalid type: <nil>`, the system will automatically fall back to direct tool execution. To reset Elysia's metadata:

```python
import weaviate
client = weaviate.connect_to_local()
if client.collections.exists("ELYSIA_METADATA__"):
    client.collections.delete("ELYSIA_METADATA__")
client.close()
```

### Reset everything

```powershell
# Stop and remove containers + volumes
docker compose down -v

# Start fresh
docker compose up -d
python -m src.cli init --recreate
```

## Development

```powershell
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/
ruff check src/ --fix
```

## Recent Changes

### Version Updates
- Weaviate upgraded to **1.28.2**
- Elysia integration with **automatic fallback** when gRPC errors occur

### New Features
- **Multiple policy path support**: Ingestion now scans both `do-artifacts/policy_docs` and `general-artifacts/policies`
- **Privacy and security policies**: Added support for general organizational policies
- **Elysia helper scripts**: `start_elysia.ps1` and `stop_elysia.ps1` for Windows

### New Documentation
- `knowledge/` folder with agent instruction templates for:
  - Compiling architecture principles
  - Interacting with ArchiMate files
- `other/` folder with Elysia reference documentation

## License

MIT License
