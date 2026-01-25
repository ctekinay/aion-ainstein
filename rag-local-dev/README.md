# RAG Local Development Environment

A production-grade RAG (Retrieval-Augmented Generation) system using PostgreSQL + pgvector for hybrid search over architectural documentation.

## Overview

This system indexes and searches:
- **ADRs** (Architectural Decision Records) - Markdown files with YAML frontmatter
- **Principles** - Architecture and governance principles
- **Policy Documents** - PDF and DOCX files
- **SKOS Terminology** - RDF/TTL vocabularies (IEC standards, CIM, etc.)

## Technology Stack

| Component | Technology |
|-----------|------------|
| Vector Database | PostgreSQL 16 + pgvector |
| Index Type | HNSW (Hierarchical Navigable Small World) |
| Embedding Provider | OpenAI `text-embedding-3-small` |
| API Framework | FastAPI |
| Containerization | Docker Compose |

## Quick Start

### 1. Prerequisites

- Python 3.10+
- Docker and Docker Compose
- OpenAI API key

### 2. Environment Setup

```bash
# Navigate to rag-local-dev directory
cd rag-local-dev

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export RAG_DB_PASSWORD=devpassword
export OPENAI_API_KEY=your-api-key-here
```

### 3. Start Database

```bash
docker-compose up -d
```

This starts PostgreSQL with pgvector. The schema is automatically initialized.

### 4. Run Indexing

```bash
# Index all documents
python scripts/index_documents.py

# Or index specific types
python scripts/index_documents.py --only adrs
python scripts/index_documents.py --only terminology

# Clear and re-index
python scripts/index_documents.py --clear
```

### 5. Start API Server

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Test Search

```bash
# Using curl
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the decision on CIM?"}'

# Or visit the interactive docs
open http://localhost:8000/docs
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/search` | POST | Hybrid search with auto query classification |
| `/document/{doc_id}` | GET | Retrieve document by ID (e.g., ADR-0001) |
| `/documents` | GET | List all indexed documents |
| `/stats` | GET | Collection statistics |
| `/health` | GET | Health check |

### Search Request Example

```json
{
  "query": "What is eventual consistency?",
  "doc_types": ["principle", "adr"],
  "max_results": 5,
  "include_terminology": true,
  "alpha": 0.7
}
```

### Search Response

```json
{
  "chunks": [...],
  "terminology_matches": [...],
  "confidence": 0.82,
  "query_type": "semantic",
  "no_good_results": false,
  "suggested_refinements": [],
  "query_id": "...",
  "latency_ms": 145
}
```

## Query Types

The system automatically classifies queries:

| Type | Example | Alpha | Description |
|------|---------|-------|-------------|
| `exact_match` | "ADR-0001" | 0.3 | Document ID lookup |
| `semantic` | "How does authentication work?" | 0.8 | Conceptual questions |
| `terminology` | "Contingency" | 0.4 | Term definitions |
| `mixed` | General queries | 0.6 | Balanced hybrid |

## Project Structure

```
rag-local-dev/
├── docker-compose.yml          # PostgreSQL + pgvector
├── config.yaml                 # Configuration
├── requirements.txt            # Python dependencies
├── src/
│   ├── parsers/               # Document parsers
│   │   ├── markdown_parser.py # ADRs, Principles
│   │   ├── pdf_parser.py      # PDF/DOCX policies
│   │   └── rdf_parser.py      # SKOS terminology
│   ├── embedding/             # Embedding providers
│   ├── database/              # Schema and operations
│   ├── search/                # Hybrid search implementation
│   ├── api/                   # FastAPI endpoints
│   └── evaluation/            # Test queries and metrics
├── scripts/
│   ├── setup_database.py      # Database initialization
│   ├── index_documents.py     # Main indexing script
│   ├── validate_chunks.py     # Chunk inspection
│   └── run_evaluation.py      # Evaluation suite
└── notebooks/
    └── chunk_explorer.ipynb   # Interactive exploration
```

## Data Paths

Configured in `config.yaml`:

```yaml
data_paths:
  adrs: "../data/esa-main-artifacts/doc/decisions"
  esa_principles: "../data/esa-main-artifacts/doc/principles"
  do_principles: "../data/do-artifacts/principles"
  ontology: "../data/esa-skosmos"
  do_policy_docs: "../data/do-artifacts/policy_docs"
  general_policies: "../data/general-artifacts/policies"
```

## Validation and Evaluation

```bash
# Validate indexed chunks
python scripts/validate_chunks.py --all

# Run evaluation suite
python scripts/run_evaluation.py

# Test single query
python scripts/run_evaluation.py -q "What is CIM?"
```

## Configuration

Key settings in `config.yaml`:

```yaml
# Search parameters
search:
  default_alpha: 0.7      # Vector vs BM25 weight
  default_k: 10           # Results to return
  min_confidence_threshold: 0.4

# Embedding
embedding:
  provider: "openai"
  openai:
    model: "text-embedding-3-small"
    dimensions: 1536
```

## Switching Embedding Providers

The system supports multiple embedding providers:

```yaml
embedding:
  provider: "together"  # Change from "openai"
  together:
    model: "intfloat/multilingual-e5-large-instruct"
```

**Note:** Changing providers requires re-indexing all documents.

## Hybrid Search

The search combines:
- **Vector similarity** (cosine distance via pgvector)
- **BM25 full-text search** (PostgreSQL tsvector)

Formula: `score = α × vector_score + (1-α) × bm25_score`

The system automatically adjusts α based on query type.

## Bilingual Support

- Full-text search uses both English and Dutch tsvectors
- Language is auto-detected per query
- SKOS terminology supports English and Dutch labels

## Troubleshooting

### Database connection fails
```bash
# Check if PostgreSQL is running
docker-compose ps

# View logs
docker-compose logs postgres
```

### Embedding errors
```bash
# Verify API key
echo $OPENAI_API_KEY

# Check rate limits in logs
```

### Low search quality
```bash
# Check chunk statistics
python scripts/validate_chunks.py --stats

# Sample chunks to inspect content
python scripts/validate_chunks.py --sample-chunks 5
```
