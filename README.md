# AION-AINSTEIN

Multi-Agent RAG (Retrieval-Augmented Generation) System for Energy System Architecture knowledge bases.

## Quick Deploy

Get up and running with local LLM (Ollama) - no API keys needed:

```bash
# 1. Clone and enter the project
git clone https://github.com/ctekinay/aion-ainstein.git
cd aion-ainstein

# 2. Start Weaviate (Docker required)
docker compose up -d

# 3. Install and start Ollama (see https://ollama.ai/download)
ollama serve &  # Skip if already running

# 4. Pull required models (IMPORTANT: do this BEFORE init)
ollama pull nomic-embed-text-v2-moe
ollama pull alibayram/smollm3:latest

# 5. Set up Python environment (Python 3.10-3.12 required)
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 6. Configure environment
cp .env.example .env
# Default uses Ollama - no changes needed for local LLM
# For OpenAI: edit .env, set LLM_PROVIDER=openai and add OPENAI_API_KEY

# 7. Initialize and start
python -m src.cli init
python -m src.cli elysia  # Start the Elysia CLI interface
```

## Overview

AION-AINSTEIN is a local Weaviate-based RAG system that enables intelligent querying of energy sector knowledge bases. It supports both **local LLM (Ollama)** and **cloud LLM (OpenAI)** for embeddings and generation.

**Knowledge bases include:**

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
    │              LLM Provider (choose one)                  │
    │  ┌─────────────────────┐  ┌───────────────────────────┐ │
    │  │ Ollama (default)    │  │ OpenAI (alternative)      │ │
    │  │ Embed: nomic-v2-moe │  │ Embed: text-embed-3-small │ │
    │  │ Chat: smollm3       │  │ Chat: gpt-4o-mini         │ │
    │  │ Local, Free         │  │ Cloud, Paid               │ │
    │  └─────────────────────┘  └───────────────────────────┘ │
    └─────────────────────────────────────────────────────────┘
```

## Prerequisites

- **Docker Desktop** (with WSL2 on Windows) or **Podman** (Linux) - [Install Docker](https://docs.docker.com/desktop/)
- **Python 3.10-3.12** (3.12 recommended) - [Download Python](https://www.python.org/downloads/)
- **Git** - [Install Git](https://git-scm.com/downloads)

**LLM Provider** (choose one):
- **Ollama** (default, local) - [Install Ollama](https://ollama.ai/download) - Free, runs locally, no API key needed
- **OpenAI** (cloud) - [Get API Key](https://platform.openai.com/api-keys) - Requires API key and usage fees

> **Note**: Python 3.13+ is not yet supported due to dependency compatibility.

## Installation

### Linux / macOS

```bash
# Clone the repository
git clone https://github.com/ctekinay/aion-ainstein.git
cd aion-ainstein

# Start Weaviate database
# Using Docker:
docker compose up -d
# Or using Podman (Linux):
podman-compose up -d
# Or start existing container:
podman start weaviate-aion  # if container already exists

# Install Ollama (if not already installed)
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama and pull models
ollama serve &  # Skip if already running (check: curl localhost:11434/api/version)
ollama pull nomic-embed-text-v2-moe
ollama pull alibayram/smollm3:latest

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Default uses Ollama - edit only if using OpenAI:
# nano .env  # Set LLM_PROVIDER=openai and add OPENAI_API_KEY

# Initialize the system (creates embeddings)
python -m src.cli init

# Start Elysia CLI (recommended)
python -m src.cli elysia
```

> **Linux Note**: On some Linux systems, the Elysia framework may have compatibility issues with `uvloop`. If you see errors like "Can't patch loop of type uvloop.Loop", the system automatically falls back to direct query mode.

### Windows (PowerShell)

```powershell
# Clone the repository
git clone https://github.com/ctekinay/aion-ainstein.git
cd aion-ainstein

# Start Weaviate database
docker compose up -d

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment
Copy-Item .env.example .env
notepad .env  # Add your OPENAI_API_KEY

# Initialize the system
python -m src.cli init

# Start Elysia CLI (recommended)
python -m src.cli elysia
```

## Docker Setup

The system uses Docker to run a local Weaviate vector database. The `docker-compose.yml` includes:

- **Weaviate 1.28.2** - Vector database with OpenAI integration
- **Ports**: 8080 (HTTP), 50051 (gRPC)
- **Persistent storage** via Docker volumes

### Docker Commands

```bash
# Start Weaviate in background
docker compose up -d

# Check if running
docker ps

# View logs
docker logs weaviate-aion

# Stop Weaviate
docker compose down

# Reset everything (deletes all data)
docker compose down -v
```

## Using the System

### Elysia CLI Mode (Recommended)

The Elysia CLI provides an intelligent, decision tree-based interface:

```bash
python -m src.cli elysia
```

This starts an interactive session where you can ask questions like:
- "What is the CIM model?"
- "What are the data governance principles?"
- "Show me all architectural decisions about security"

### Elysia Web UI

For a full web experience with dynamic data display:

```powershell
# Windows
.\start_elysia.ps1

# Or using CLI
python -m src.cli start-elysia-server
```

Access the UI at **http://localhost:8000**

To stop:
```powershell
.\stop_elysia.ps1
```

### Other Query Modes

```bash
# Interactive multi-agent mode
python -m src.cli interactive

# Single query
python -m src.cli query "What is the CIM model?"

# Query specific agent
python -m src.cli query "What decisions have been made about security?" --agent architecture

# Direct search
python -m src.cli search "data quality" --collection policy

# Check system status
python -m src.cli status
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

### Elysia Tools

Available tools in Elysia mode:
- `search_vocabulary` - Search SKOS concepts and IEC standards
- `search_architecture_decisions` - Search ADRs
- `search_principles` - Search architecture principles
- `search_policies` - Search governance policies (including privacy and security)
- `list_all_adrs` - List all ADRs
- `list_all_principles` - List all principles
- `get_collection_stats` - Get system statistics

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

### LLM Provider Selection

The system supports two LLM providers. Set `LLM_PROVIDER` in your `.env` file:

| Provider | Value | Description |
|----------|-------|-------------|
| **Ollama** | `ollama` | Local LLM, free, no API key required (default) |
| **OpenAI** | `openai` | Cloud LLM, requires API key and usage fees |

### Environment Variables

**Common Settings:**

| Variable | Default | Description |
|----------|---------|-------------|
| `WEAVIATE_URL` | `http://localhost:8080` | Weaviate HTTP endpoint |
| `WEAVIATE_GRPC_URL` | `localhost:50051` | Weaviate gRPC endpoint |
| `LLM_PROVIDER` | `ollama` | LLM provider: `ollama` or `openai` |

**Ollama Settings** (when `LLM_PROVIDER=ollama`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `alibayram/smollm3:latest` | Chat/completion model |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text-v2-moe` | Embedding model |

**OpenAI Settings** (when `LLM_PROVIDER=openai`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | Your OpenAI API key |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` | Chat model |

---

## Ollama Setup (Local LLM)

Ollama allows running LLMs locally without API keys or cloud costs.

### 1. Install Ollama

**Linux:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

**macOS:**
```bash
brew install ollama
```

**Windows:**
Download from [ollama.ai/download](https://ollama.ai/download)

### 2. Start Ollama Service

**Linux/macOS:**
```bash
# Start Ollama in the background
ollama serve &

# Or as a systemd service (Linux)
sudo systemctl start ollama
sudo systemctl enable ollama  # Auto-start on boot
```

**Windows:**
Ollama runs automatically after installation. Check the system tray.

### 3. Pull Required Models

**IMPORTANT:** Pull both models BEFORE running `python -m src.cli init`

```bash
# Embedding model (required for vector search)
ollama pull nomic-embed-text-v2-moe

# Chat model (required for responses)
ollama pull alibayram/smollm3:latest
```

### 4. Verify Models

```bash
# List installed models
ollama list

# Expected output:
# NAME                              SIZE
# nomic-embed-text-v2-moe          274 MB
# alibayram/smollm3:latest         2.0 GB

# Test embedding model
curl http://localhost:11434/api/embed -d '{
  "model": "nomic-embed-text-v2-moe",
  "input": "test"
}'

# Test chat model
curl http://localhost:11434/api/generate -d '{
  "model": "alibayram/smollm3:latest",
  "prompt": "Hello"
}'
```

### 5. Configure Environment

```bash
cp .env.example .env
```

Ensure your `.env` contains:
```env
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=alibayram/smollm3:latest
OLLAMA_EMBEDDING_MODEL=nomic-embed-text-v2-moe
```

### 6. Initialize and Run

```bash
# Initialize (creates embeddings using Ollama)
python -m src.cli init

# Start the system
python -m src.cli elysia
```

### Ollama Troubleshooting

**Connection refused (port 11434):**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/version

# If not running, start it
ollama serve

# On Linux, check systemd status
sudo systemctl status ollama
```

**404 on /api/embed:**
```bash
# This means the embedding model is not installed
ollama pull nomic-embed-text-v2-moe

# Verify it's installed
ollama list | grep nomic
```

**Model not found errors:**
```bash
# List available models
ollama list

# Pull missing models
ollama pull nomic-embed-text-v2-moe
ollama pull alibayram/smollm3:latest
```

**Port already in use:**
```bash
# Check what's using port 11434
# Linux/macOS:
lsof -i :11434
# Windows (PowerShell):
netstat -ano | findstr 11434

# Ollama might already be running - this is fine
```

**Slow performance:**
- Ollama uses CPU by default. For faster inference, use a GPU-enabled system.
- SmolLM3 is intentionally small (2GB) for broad compatibility. For better quality, try larger models like `llama3.2` or `mistral`.

### Alternative Ollama Models

| Model | Size | Use Case |
|-------|------|----------|
| `alibayram/smollm3:latest` | 2GB | Default, lightweight, fast |
| `llama3.2:3b` | 2GB | Better quality, similar size |
| `mistral:7b` | 4GB | Higher quality, needs more RAM |
| `llama3.2:latest` | 4GB | Best balance of quality/speed |

To use a different model:
```bash
ollama pull llama3.2:3b
# Then update .env:
# OLLAMA_MODEL=llama3.2:3b
```

---

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
