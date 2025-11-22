# AION-AINSTEIN

Multi-Agent RAG (Retrieval-Augmented Generation) System for Energy System Architecture knowledge bases.

## Overview

AION-AINSTEIN is a local-first RAG system built on [Weaviate](https://weaviate.io/) that enables intelligent querying of energy sector knowledge bases including:

- **SKOS/RDF Vocabularies**: IEC 61970/61968/62325 standards, CIM models, and domain ontologies
- **Architectural Decision Records (ADRs)**: Design decisions and rationale
- **Data Governance Policies**: Compliance, data quality, and management policies
- **Architecture Principles**: System design and governance principles

The system uses a multi-agent architecture inspired by [Weaviate's Elysia](https://weaviate.io/blog/elysia-agentic-rag) framework, with specialized agents for different knowledge domains.

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
    │                    Weaviate (Local)                     │
    │                                                         │
    │  ┌──────────┐  ┌──────────────────┐  ┌───────────────┐ │
    │  │Vocabulary│  │ArchitecturalDec. │  │PolicyDocument │ │
    │  │Collection│  │  Collection      │  │  Collection   │ │
    │  └──────────┘  └──────────────────┘  └───────────────┘ │
    └─────────────────────────────────────────────────────────┘
                              │
    ┌─────────────────────────▼───────────────────────────────┐
    │                    Ollama (Local LLM)                   │
    │         Embeddings: nomic-embed-text                    │
    │         Generation: llama3.2                            │
    └─────────────────────────────────────────────────────────┘
```

## Prerequisites

- Docker and Docker Compose
- Python 3.10+ (3.12 recommended)
- NVIDIA GPU (optional, for faster local LLM inference)

## Quick Start

### 1. Start the Infrastructure

```bash
# Start Weaviate and Ollama
docker compose up -d

# Pull the required Ollama models
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull llama3.2
```

### 2. Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
```

### 3. Configure Environment

```bash
# Copy example configuration
cp .env.example .env

# Edit .env if needed (defaults work for local setup)
```

### 4. Initialize and Ingest Data

```bash
# Initialize collections and ingest all data
aion init

# Check status
aion status
```

### 5. Query the System

```bash
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

```bash
# Use specific agent
aion query "question" --agent vocabulary
aion query "question" --agent architecture
aion query "question" --agent policy

# Use all agents
aion query "question" --all

# Verbose output with sources
aion query "question" --verbose
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
├── docker-compose.yml         # Weaviate + Ollama
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## Configuration

Environment variables (`.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `WEAVIATE_URL` | `http://localhost:8080` | Weaviate HTTP endpoint |
| `WEAVIATE_IS_LOCAL` | `True` | Use local Weaviate instance |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model |
| `OLLAMA_CHAT_MODEL` | `llama3.2` | Generation model |

## Using with OpenAI (Optional)

To use OpenAI instead of local Ollama:

```bash
# In .env
OPENAI_API_KEY=your-api-key
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4o-mini
```

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

## Development

```bash
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
