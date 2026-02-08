# AInstein System Architecture

This document describes the three-layer architecture of the AInstein RAG system.

## Architecture Overview

The system separates concerns into three distinct layers:

| Layer | Path | Purpose | Embedded in RAG? |
|-------|------|---------|------------------|
| **Domain Knowledge** | `/data/` | Alliander ADRs, Principles, Policies, SKOSMOS ontologies | Yes |
| **Behavior Rules** | `/skills/` | LLM instructions, formatting, anti-hallucination rules | No (prompt injection) |
| **Project Decisions** | `/docs/implementation-records/` | AInstein implementation rationale | No (developer docs) |

## Layer 1: Domain Knowledge (`/data/`)

This layer contains **Alliander's organizational knowledge** that users query through the RAG system.

### Content Sources

| Path | Content | Owner | Weaviate Collection |
|------|---------|-------|---------------------|
| `data/esa-main-artifacts/doc/decisions/` | ESA ADRs and DARs | ESA Team | `ADR_Ollama` |
| `data/esa-main-artifacts/doc/principles/` | ESA Principles | ESA Team | `Principle_Ollama` |
| `data/esa-skosmos/` | SKOSMOS ontologies (.ttl) | ESA Team | `Vocabulary_Ollama` |
| `data/do-artifacts/policy_docs/` | Data Office policies | Data Office | `Policy_Ollama` |
| `data/general-artifacts/policies/` | General policies | Various | `Policy_Ollama` |

### Document Types

Within the decisions folder, files are classified by type:

| File Pattern | Document Type | Embedded? | Purpose |
|--------------|---------------|-----------|---------|
| `0010-name.md` | ADR (Architecture Decision Record) | Yes | Technical decisions |
| `0010D-name.md` | DAR (Decision Approval Record) | Yes | DACI approval history |
| `adr-template.md` | Template | **No** (skipped) | Document templates |
| `index.md` | Index | **No** (skipped) | Registry/metadata |

**Note:** Templates and index files are skipped at ingestion time to save embedding tokens and storage. They were previously embedded and filtered at query time, but skipping at ingestion is more efficient.

**Note:** The `index.md` file is still **parsed** for ownership metadata (team, department, organization) even though it's not embedded. This enrichment happens via a separate code path in `index_metadata_loader.py`.

### DAR Handling

DARs (Decision Approval Records) contain governance information:
- Who approved a decision (DACI process)
- Approval dates and conditions
- Stakeholder sign-offs

DARs are:
- **Embedded** in Weaviate (they contain searchable governance info)
- **Excluded by default** at query time (most questions are about decisions, not approvals)
- **Included** when the query is about approvals (e.g., "Who approved ADR-10?")

This behavior is controlled by `src/skills/filters.py`.

## Layer 2: Behavior Rules (`/skills/`)

This layer contains **instructions for LLM behavior**, not knowledge. Skills are injected into prompts to control how the LLM responds.

### Current Skills

| Skill | Purpose |
|-------|---------|
| `rag-quality-assurance` | Anti-hallucination rules, citation requirements, abstention |
| `response-formatter` | Rich formatting, statistics, follow-up questions |
| `response-contract` | Structured JSON output schema |

### How Skills Work

1. Skills are defined in `/skills/{skill-name}/SKILL.md`
2. The skill registry (`skills/registry.yaml`) defines triggers and auto-activation
3. Skill content is injected into the LLM prompt at runtime
4. Skills modify **behavior**, not **knowledge**

Skills are **NOT embedded** in Weaviate. They don't answer user questions - they control how answers are generated and formatted.

## Layer 3: Project Decisions (`/docs/implementation-records/`)

This layer contains **AInstein project technical decisions** - documentation for developers about why the system is built the way it is.

### Important Distinction

| | ESA ADRs (Layer 1) | AInstein Implementation Records (Layer 3) |
|---|---|---|
| **Path** | `/data/esa-main-artifacts/doc/decisions/` | `/docs/implementation-records/` |
| **Content** | Alliander architectural decisions (CIM, OAuth, TLS) | AInstein system design (BM25 fallback, abstention logic) |
| **Governed by** | ESA Team, DACI process | AInstein Project Team |
| **Embedded?** | Yes | No |
| **Purpose** | Answer user questions | Document implementation rationale |

### Why Not Embedded?

1. **Different audience**: ESA ADRs help architects. Implementation records help developers.
2. **Circular dependency**: Embedding "how the RAG works" into the RAG creates confusion.
3. **Different governance**: ESA ADRs go through DACI. Implementation records are dev documentation.

## Data Flow

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 2: Skills (Behavior)                              │
│ - Injected into prompt                                  │
│ - Controls formatting, anti-hallucination, etc.         │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 1: Domain Knowledge (RAG)                         │
│ - Weaviate hybrid search (BM25 + vector)                │
│ - Returns ADRs, Principles, Policies, Vocabulary        │
│ - Filters exclude templates, indexes (and DARs by       │
│   default unless query is about approvals)              │
└─────────────────────────────────────────────────────────┘
    │
    ▼
LLM Generation (with skill-injected behavior)
    │
    ▼
Response to User
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Vector DB | Weaviate | Hybrid BM25 + vector search |
| Embeddings (Local) | Ollama + `nomic-embed-text-v2-moe` | Client-side embedding generation |
| Embeddings (Cloud) | OpenAI `text-embedding-3-small` | Server-side embedding generation |
| LLM (Local) | Ollama + `smollm3`, `qwen3:4b` | Response generation |
| LLM (Cloud) | OpenAI `gpt-5.2`, `gpt-4o-mini` | Response generation |
| Framework | Elysia (Weaviate) | Agentic RAG orchestration |
| DB | SQLite | Conversation history |
| Container | Docker | Weaviate, Ollama deployment |
| Backend | Python + FastAPI | Web UI, API |

## Key Files

| File | Purpose |
|------|---------|
| `src/loaders/markdown_loader.py` | Loads and classifies ADRs/Principles |
| `src/loaders/index_metadata_loader.py` | Parses index.md for ownership metadata |
| `src/skills/filters.py` | Builds query-time filters (DAR exclusion, etc.) |
| `src/chat_ui.py` | Main retrieval function (`perform_retrieval`) |
| `src/weaviate/embeddings.py` | Client-side embedding generation |
| `skills/registry.yaml` | Skill definitions and triggers |
