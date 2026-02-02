# Technical Handover Document: AION-AInstein RAG System

## Project Overview

**AION-AInstein** is a Retrieval-Augmented Generation (RAG) system for Alliander's Energy System Architecture (ESA) knowledge base. It provides a chat interface for querying architectural decisions (ADRs), principles, policies, and vocabulary (SKOS/OWL ontologies).

**Repository**: `https://github.com/ctekinay/aion-ainstein`
**Branch**: `feature/dual-stack-llm-comparison`

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Chat UI (FastAPI)                        │
│                      src/chat_ui.py:8081                         │
└───────────────────────────┬──────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   Ollama      │   │    OpenAI     │   │   Weaviate    │
│ (SmolLM3 +    │   │  (GPT-5.x +   │   │ (Vector DB)   │
│  Nomic embed) │   │  text-embed)  │   │  :8080        │
│  :11434       │   │   Cloud API   │   │               │
└───────────────┘   └───────────────┘   └───────────────┘
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `src/chat_ui.py` | FastAPI server | Chat API, SSE streaming, Test Mode comparison |
| `src/weaviate/` | Weaviate integration | Collections, ingestion, embeddings |
| `src/loaders/` | Document loaders | Markdown (ADR/Principles), RDF (SKOS), DOCX/PDF |
| `src/config.py` | Configuration | Settings from `.env` file |
| `src/static/index.html` | Frontend | Chat UI with Test Mode toggle |

---

## Dual-Stack LLM Comparison ("Test Mode")

The primary feature being developed is **side-by-side comparison** of two RAG stacks:

### Stack 1: Fully Local (Ollama)
- **Embeddings**: `nomic-embed-text-v2-moe` (768 dimensions) via Ollama
- **LLM**: SmolLM3 3.1B via Ollama
- **Collections**: `Vocabulary`, `ArchitecturalDecision`, `Principle`, `PolicyDocument`

### Stack 2: OpenAI Cloud
- **Embeddings**: `text-embedding-3-small` via Weaviate's `text2vec-openai` module
- **LLM**: GPT-5.2 / GPT-5.1 / GPT-4o-mini
- **Collections**: `*_OpenAI` variants (e.g., `ArchitecturalDecision_OpenAI`)

### Test Mode Flow
```
User Query
    │
    ├──► [Ollama Embedding] ──► Weaviate (local collections) ──► Context
    │                                                              │
    │                                                              ▼
    │                                                     [SmolLM3 Generation]
    │                                                              │
    │                                                              ▼
    │                                                     LEFT PANEL (response)
    │
    └──► [OpenAI Embedding via Weaviate] ──► Weaviate (OpenAI collections) ──► Context
                                                                                   │
                                                                                   ▼
                                                                          [GPT-5.x Generation]
                                                                                   │
                                                                                   ▼
                                                                          RIGHT PANEL (response)
```

---

## Critical Bugs Fixed

### 1. Weaviate text2vec-ollama Bug (#8406)

**Problem**: Weaviate's `text2vec-ollama` module ignores `apiEndpoint` configuration and always connects to `localhost:11434`, which fails in Docker where Ollama runs on `host.docker.internal:11434`.

**Workaround Implemented** (in `src/weaviate/embeddings.py`):
```python
# Instead of using Weaviate's vectorizer, we:
# 1. Configure collections with Vectorizer.none()
# 2. Generate embeddings client-side via Ollama /api/embed endpoint
# 3. Insert objects with pre-computed vectors
# 4. Query using near_vector with client-computed query embeddings

class OllamaEmbeddings:
    def embed(self, text: str) -> list[float]:
        response = self.client.post(
            f"{self.base_url}/api/embed",  # http://localhost:11434/api/embed
            json={"model": self.model, "input": text}
        )
        return response.json()["embeddings"][0]
```

**Files affected**:
- `src/weaviate/collections.py`: Changed `_get_ollama_vectorizer_config()` to return `Configure.Vectorizer.none()`
- `src/weaviate/embeddings.py`: New module with `OllamaEmbeddings` class
- `src/weaviate/ingestion.py`: Added `_insert_batch_with_embeddings()` method
- `src/chat_ui.py`: Added `embed_text()` call for query embedding

### 2. SmolLM3 Response Quality Issues

**Problem**: SmolLM3 was:
- Leaking `<think>...</think>` tags in responses
- Ignoring context and giving generic advice

**Fixes**:
```python
# src/chat_ui.py

def strip_think_tags(text: str) -> str:
    """Strip <think>...</think> tags from model output."""
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'</?think>', '', cleaned)
    return cleaned.strip()

# Improved prompt for SmolLM3 (explicit RAG instructions)
ollama_system_prompt = """You are an assistant that ONLY answers based on the provided context.
IMPORTANT RULES:
1. ONLY use information from the context below to answer
2. If the context contains the answer, provide it directly with specific details
3. If the context does NOT contain the answer, say "I don't have information about that"
4. Do NOT make up information or give general advice
5. Be concise and cite specific items from the context"""
```

### 3. Retrieval Quality - Index/Template Documents

**Problem**: Retrieval was returning index files and templates instead of actual content documents.

**Initial Fix (BAD - Hardcoded)**:
```python
# This was the wrong approach - static list of titles to skip
INDEX_TITLES = {
    'Decision Approval Record List',
    'Energy System Architecture - Decision Records',
    ...
}
```

**Proper Fix (Metadata-based filtering)**:

1. **Added `doc_type` property to collections** (`src/weaviate/collections.py`):
```python
Property(
    name="doc_type",
    data_type=DataType.TEXT,
    description="Document classification: content, index, template",
    tokenization=Tokenization.FIELD,
)
```

2. **Document classification during loading** (`src/loaders/markdown_loader.py`):
```python
def _classify_adr_document(self, file_path, title, content) -> str:
    # Index files
    if file_path.name.lower() in ['index.md', 'readme.md', 'overview.md']:
        return 'index'
    # Template files
    if any(ind in content.lower() for ind in ['{short title', 'template', '{insert ']):
        return 'template'
    # Default: actual content
    return 'content'
```

3. **Weaviate filter at query time** (`src/chat_ui.py`):
```python
from weaviate.classes.query import Filter

content_filter = Filter.by_property("doc_type").equal("content")

results = collection.query.hybrid(
    query=question,
    vector=query_vector,
    filters=content_filter,  # Excludes index/template docs
    limit=8,
    alpha=0.5,
)
```

### 4. Embedding Timeouts During Ingestion

**Problem**: Ollama embeddings timing out during batch ingestion, causing failed ingestion.

**Fixes** (`src/weaviate/embeddings.py`):
```python
# Increased timeout: 60s → 300s
timeout: float = 300.0

# Added retry logic with fallback
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

def embed_batch(self, texts):
    for attempt in range(MAX_RETRIES):
        try:
            # Try batch embedding
            ...
        except (httpx.HTTPError, httpx.TimeoutException):
            time.sleep(RETRY_DELAY_SECONDS)

    # Fallback: process one at a time
    for text in texts:
        embedding = self.embed(text)
        ...
```

**Reduced batch sizes** (`src/weaviate/ingestion.py`):
```python
DEFAULT_BATCH_SIZE_OLLAMA = 5   # Was 20
DEFAULT_BATCH_SIZE_OPENAI = 50  # Was 100
```

---

## Current State (as of 2026-02-02)

### Collections Status
| Collection | Local | OpenAI |
|------------|-------|--------|
| Vocabulary | 5,223 | 5,223 |
| ADRs | 40 | 40 |
| Principles | 71 | 71 |
| Policies | 76 | 76 |

### Git Commits on `feature/dual-stack-llm-comparison`
```
32feddf Fix embedding timeouts: add retry logic and reduce batch sizes
b8afefb Refactor retrieval to use proper RAG: metadata filters instead of static code
7ccbf19 Fix retrieval quality: filter index files, handle list queries
ffaa263 Add GPT-5.x model support, default to GPT-5.2
956868a Fix SmolLM3 response quality: strip think tags and improve prompt
298c04c Fix Weaviate text2vec-ollama bug with client-side embeddings workaround
```

---

## What's Working

1. **Ingestion pipeline**: Successfully ingests all document types with client-side embeddings
2. **Dual collection setup**: Both local (Nomic) and OpenAI collections populated
3. **Test Mode endpoint**: `/api/chat/stream/compare` returns side-by-side responses
4. **Metadata filtering**: `doc_type` field filters out index/template documents
5. **Hybrid search**: Combines BM25 keyword + vector similarity

## What Needs Work

### 1. Test Mode UI Verification
The frontend Test Mode UI (`src/static/index.html`) needs testing to verify:
- Toggle button works
- Split-screen layout displays correctly
- Both panels populate with responses
- Latency metrics display

### 2. Latency Optimization
Current latencies are high:
- Ollama embedding: ~5s per query
- SmolLM3 generation: ~10-30s
- Consider caching query embeddings

### 3. Response Quality Evaluation
Need systematic evaluation of:
- Source recall (are relevant documents retrieved?)
- Answer accuracy (does the LLM use the context correctly?)
- Comparison: Local vs OpenAI quality

### 4. Context Window Management
SmolLM3 has ~8K token context. Currently truncating at `SMOLLM3_MAX_INPUT_TOKENS = 6500`.
May need smarter chunking or summarization.

---

## Key Files to Understand

| File | Lines | Key Functions |
|------|-------|---------------|
| `src/chat_ui.py` | ~1400 | `perform_retrieval()`, `stream_comparison_response()`, `generate_with_ollama()` |
| `src/weaviate/embeddings.py` | ~200 | `OllamaEmbeddings`, `embed_text()`, `embed_texts()` |
| `src/weaviate/collections.py` | ~750 | Collection schemas, `_get_ollama_vectorizer_config()` |
| `src/weaviate/ingestion.py` | ~500 | `DataIngestionPipeline`, `_insert_batch_with_embeddings()` |
| `src/loaders/markdown_loader.py` | ~500 | `_classify_adr_document()`, `_classify_principle_document()` |
| `src/config.py` | ~100 | Settings class with all configuration |

---

## Running the System

### Prerequisites
```bash
# Weaviate running on localhost:8080
docker-compose up -d

# Ollama running with models
ollama pull nomic-embed-text
ollama pull alibayram/smollm3:latest

# OpenAI API key in .env
OPENAI_API_KEY=sk-...
```

### Commands
```bash
# Initialize/reingest data
python -m src.cli init --recreate --include-openai

# Check status
python -m src.cli status

# Start chat server
python -m src.cli chat
# Opens http://127.0.0.1:8081

# Run evaluation
python -m src.cli evaluate
```

---

## Environment Variables (.env)

```bash
WEAVIATE_URL=http://localhost:8080
OLLAMA_URL=http://localhost:11434
OLLAMA_DOCKER_URL=http://host.docker.internal:11434
OLLAMA_MODEL=alibayram/smollm3:latest
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL=gpt-5.2
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
LLM_PROVIDER=ollama
```

---

## Architecture Decisions

1. **Client-side embeddings for Ollama**: Workaround for Weaviate bug. OpenAI uses Weaviate's native vectorizer.

2. **Hybrid search**: Using `alpha=0.5` to balance keyword (BM25) and vector similarity.

3. **Metadata filtering**: Using `doc_type` property with Weaviate native filters rather than post-retrieval Python filtering.

4. **Parallel retrieval**: In Test Mode, both stacks retrieve and generate in parallel using `asyncio.gather()`.

5. **Streaming SSE**: Responses streamed via Server-Sent Events for real-time UI updates.

---

## Contact / Questions

This document was prepared for AI agent handover. The codebase is in Python 3.11+ with FastAPI, Weaviate, and Ollama/OpenAI integrations.
