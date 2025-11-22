# AION-AINSTEIN

Multi-Agent RAG (Retrieval-Augmented Generation) System for Energy System Architecture knowledge bases.

## Overview

AION-AINSTEIN is a local Weaviate-based RAG system with OpenAI embeddings that enables intelligent querying of energy sector knowledge bases including:

- **SKOS/RDF Vocabularies**: IEC 61970/61968/62325 standards, CIM models, and domain ontologies
- **Architectural Decision Records (ADRs)**: Design decisions and rationale
- **Data Governance Policies**: Compliance, data quality, and management policies
- **Architecture Principles**: System design and governance principles

The system uses a multi-agent architecture inspired by [Weaviate's Elysia](https://weaviate.io/blog/elysia-agentic-rag) framework.

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
    │                                                         │
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
python -m venv .venv

# Activate it
.\.venv\Scripts\Activate.ps1

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
aion init

# Check status
aion status
```

### 5. Query the System

```powershell
# Interactive mode
aion interactive

# Single query
aion query "What is the CIM model?"

# Query specific agent
aion query "What decisions have been made about security?" --agent architecture

# Search directly
aion search "data quality" --collection policy
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `aion init` | Initialize Weaviate collections and ingest data |
| `aion status` | Show collection status and document counts |
| `aion query <question>` | Query the multi-agent system |
| `aion search <text>` | Direct search across collections |
| `aion agents` | List available agents |
| `aion interactive` | Start interactive query session |

### Query Options

```powershell
# Use specific agent
aion query "question" --agent vocabulary
aion query "question" --agent architecture
aion query "question" --agent policy

# Use all agents
aion query "question" --all

# Verbose output with sources
aion query "question" --verbose
```

### Interactive Mode Commands

Once in interactive mode (`aion interactive`):

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

## Project Structure

```
aion-ainstein/
├── data/                       # Knowledge base data
│   ├── esa-skosmos/           # RDF/SKOS vocabularies
│   ├── esa-main-artifacts/    # ADRs and principles
│   └── do-artifacts/          # Governance policies
├── src/
│   ├── agents/                # Multi-agent system
│   │   ├── base.py           # Base agent class
│   │   ├── vocabulary_agent.py
│   │   ├── architecture_agent.py
│   │   ├── policy_agent.py
│   │   └── orchestrator.py   # Query routing
│   ├── loaders/              # Data loaders
│   │   ├── rdf_loader.py     # SKOS/OWL parser
│   │   ├── markdown_loader.py
│   │   └── document_loader.py
│   ├── weaviate/             # Weaviate integration
│   │   ├── client.py
│   │   ├── collections.py
│   │   └── ingestion.py
│   ├── config.py             # Configuration
│   └── cli.py                # CLI interface
├── scripts/
│   ├── setup.ps1             # Windows setup script
│   └── setup.sh              # Linux/macOS setup script
├── docker-compose.yml         # Weaviate
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## Configuration

Environment variables (`.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `WEAVIATE_URL` | `http://localhost:8080` | Weaviate HTTP endpoint |
| `OPENAI_API_KEY` | (required) | Your OpenAI API key |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` | Chat model |

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

## Data Sources

### SKOS Vocabularies
- IEC 61970 (CIM for energy management)
- IEC 61968 (CIM for distribution management)
- IEC 62325 (CIM for energy markets)
- IEC 62746 (Distributed energy resources)
- ACER, ENTSOE-HEMRM, EUR-Lex regulatory terms

### Architectural Decisions
- 30 ADRs covering documentation, security, standards, and integration

### Governance Policies
- Data governance, quality, classification, and metadata management

## Troubleshooting

### Docker issues on Windows

```powershell
# Check if container is running
docker ps

# View logs
docker compose logs weaviate

# Restart services
docker compose restart
```

### Weaviate connection issues

```powershell
# Test Weaviate is responding
Invoke-WebRequest -Uri "http://localhost:8080/v1/.well-known/ready"
```

### Reset everything

```powershell
# Stop and remove containers + volumes
docker compose down -v

# Start fresh
docker compose up -d
aion init --recreate
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

## License

MIT License
