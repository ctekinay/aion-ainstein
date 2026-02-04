# RAG Implementation Audit Report

**Generated:** 2026-01-26 (Updated after fixes)
**System:** PostgreSQL + pgvector RAG
**Branch:** main

---

## 1. CHUNKING

### Chunk Statistics by Document Type

| Document Type | Chunks | Docs | Avg Length | Min Length | Max Length |
|--------------|--------|------|------------|------------|------------|
| **adr** | 120 | 16 | 673 chars | 113 chars | 6,784 chars |
| **principle** | 58 | 10 | 568 chars | 162 chars | 2,252 chars |
| **governance_principle** | 22 | 6 | 491 chars | 110 chars | 956 chars |
| **policy** (PDF) | 233 | 4 | 1,051 chars | 257 chars | 2,158 chars |
| **TOTAL** | **433** | **36** | - | - | - |

> **Note:** Policy chunks were re-indexed with hierarchical PDF parser. Previous max was 31,022 chars.

### Parsers Used

| Document Type | Parser | File |
|--------------|--------|------|
| ADR | `markdown_parser.py` → `parse_adr()` | Markdown with YAML frontmatter |
| Principle | `markdown_parser.py` → `parse_principle()` | Markdown with YAML frontmatter |
| Governance Principle | `markdown_parser.py` → `parse_governance_principle()` | Plain Markdown (Dutch) |
| Policy (PDF) | `pdf_parser.py` → `parse_pdf()` | **Hierarchical parser** (max 2000 chars) |
| SKOS Terminology | `rdf_parser.py` | RDF/Turtle parsing |

### Contextual Prefix Examples

**ADR Chunk:**
```
ADR: Use Markdown Architectural Decision Records (ID: ADR-0000, Status: accepted)
Section: Introduction

# Use Markdown Architectural Decision Records
```

**Principle Chunk:**
```
Architectural Principle: Eventual Consistency by Design (ID: PRINCIPLE-0010) (Status: Proposed)
Section: Related principles

- Design for Resilience
- Timestamp Everything
```

**Governance Principle Chunk (Dutch):**
```
Data Governance Principe: Data is begrijpelijk (ID: GOV-PRINCIPLE-0003)
Sectie: Introduction

# Data is begrijpelijk
```

**Policy/PDF Chunk (NEW - with hierarchical context):**
```
Document: Sjabloon Rapport Alliander (ID: POLICY-45C64C)
Subsection: Definitief

Datum
06-02-2024
Opdrachtgever Data Office
...
```

---

## 2. EMBEDDING

### Configuration

| Setting | Value |
|---------|-------|
| **Model** | `text-embedding-3-small` |
| **Dimensions** | 1536 |
| **Provider** | OpenAI |
| **Batch Size** | 100 |

### Database Verification

```sql
SELECT embedding_model, embedding_model_version, COUNT(*)
FROM chunks GROUP BY embedding_model, embedding_model_version;
```

| embedding_model | embedding_model_version | count |
|-----------------|-------------------------|-------|
| text-embedding-3-small | 1.0 | 433 |

**Vector Dimensions Verified:** 1536

---

## 3. SEARCH

### Default Alpha Value

From `config.yaml`:
```yaml
search:
  default_alpha: 0.7
  alpha_presets:
    semantic: 0.8
    exact_match: 0.3
    terminology: 0.4
    mixed: 0.6
```

### Hybrid Search SQL

Location: `rag-local-dev/src/search/hybrid_search.py` (lines 74-91)

```sql
SELECT
    id, content, document_id, document_type, document_title,
    section_header, source_file, owner_team, metadata,
    (1 - (embedding <=> %(embedding)s::vector) / 2) AS vector_score,
    ts_rank_cd(search_vector_en, plainto_tsquery('english', %(query_text)s)) AS bm25_score,
    %(alpha)s * (1 - (embedding <=> %(embedding)s::vector) / 2) +
    (1 - %(alpha)s) * COALESCE(ts_rank_cd(...), 0) AS hybrid_score
FROM chunks
WHERE embedding IS NOT NULL
ORDER BY hybrid_score DESC LIMIT %(k)s
```

**Note:** Cosine distance `<=>` returns [0,2], normalized to [0,1] by dividing by 2.

### Query Type Detection (UPDATED)

Location: `rag-local-dev/src/search/query_processor.py` (lines 49-128)

```python
def detect_query_type(query: str, semantic_trigger_terms: List[str]) -> str:
    query_lower = query.lower().strip()
    query_upper = query.upper().strip()

    # === EXACT MATCH PATTERNS ===
    exact_id_patterns = [
        r'\bADR[-_\s]?0*(\d+)\b',           # ADR-0012, ADR0012, ADR 12
        r'\bPRINCIPLE[-_\s]?0*(\d+)\b',     # PRINCIPLE-0017
        r'\bGOV[-_]?PRINCIPLE[-_\s]?0*(\d+)\b',  # GOV-PRINCIPLE-0003
        r'\b(?:POLICY|POL)[-_\s]?0*(\d+)\b',    # POLICY-001
        r'^(?:IEC|NEN|ISO)[-_\s]?\d+$',     # IEC 61968 (exact lookup only)
    ]

    # === SEMANTIC TRIGGER TERMS ===
    # Includes energy standards: "iec 61968", "cim standard", "nen 3610", etc.

    # === QUESTION PATTERNS ===
    # what, how, why, explain, describe, etc.

    # === TERMINOLOGY LOOKUP ===
    # Short queries (1-2 words) without question words
```

### Semantic Trigger Terms (UPDATED)

Energy standards added to `config.yaml`:
```yaml
energy_standards:
  - "cim"
  - "cim standard"
  - "common information model"
  - "iec 61968"
  - "iec 61970"
  - "iec 62325"
  - "iec 62056"
  - "iec 61850"
  - "iec cim"
  - "nen 3610"
  - "nen 2660"
  - "inspire"
  - "sgam"
  - "smart grid architecture model"
```

---

## 4. SAMPLE CHUNKS

### ADR Sample

```
Document ID: ADR-0000
Source: 0000-use-markdown-architectural-decision-records.md
Section: Introduction

Content:
ADR: Use Markdown Architectural Decision Records (ID: ADR-0000, Status: accepted)
Section: Introduction

# Use Markdown Architectural Decision Records
```

### Principle Sample

```
Document ID: PRINCIPLE-0010
Section: Related principles

Content:
Architectural Principle: Eventual Consistency by Design (ID: PRINCIPLE-0010) (Status: Proposed)
Section: Related principles

- Design for Resilience
- Timestamp Everything
- Loose Coupling over Tight Integration
```

### Governance Principle Sample (Dutch)

```
Document ID: GOV-PRINCIPLE-0003
Section: Introduction

Content:
Data Governance Principe: Data is begrijpelijk (ID: GOV-PRINCIPLE-0003)
Sectie: Introduction

# Data is begrijpelijk
```

### Policy/PDF Sample (NEW - with document_id)

```
Document ID: POLICY-45C64C
Section: Definitief
Length: 860 chars

Content:
Document: Sjabloon Rapport Alliander (ID: POLICY-45C64C)
Subsection: Definitief

Datum
06-02-2024
Opdrachtgever Data Office
...
```

### Terminology Sample

| Field | Value |
|-------|-------|
| **concept_uri** | http://vocabs.alliander.com/terms/aaio/MultimodalAI |
| **pref_label_en** | Multimodal AI |
| **pref_label_nl** | Multimodal AI |
| **vocabulary_name** | AAIO |
| **definition** | AI systems capable of processing and generating content across multiple data modalities. |

---

## 5. INDEX VERIFICATION

### Chunks Table Indexes

| Index Name | Type |
|------------|------|
| `chunks_pkey` | UNIQUE btree (id) |
| `chunks_embedding_idx` | **HNSW** (embedding vector_cosine_ops) |
| `chunks_search_en_idx` | **GIN** (search_vector_en) |
| `chunks_search_nl_idx` | **GIN** (search_vector_nl) |
| `chunks_document_type_idx` | btree (document_type) |
| `chunks_document_id_idx` | btree (document_id) |
| `chunks_source_file_idx` | btree (source_file) |
| `chunks_metadata_idx` | GIN (metadata) |
| `chunks_owner_team_idx` | btree (owner_team) |

### Terminology Table Indexes

| Index Name | Type |
|------------|------|
| `terminology_pkey` | UNIQUE btree (id) |
| `terminology_concept_uri_key` | UNIQUE btree (concept_uri) |
| `terminology_embedding_idx` | **HNSW** (embedding vector_cosine_ops) |
| `terminology_search_idx` | **GIN** (search_vector) |
| `terminology_pref_en_idx` | btree (pref_label_en) |
| `terminology_pref_nl_idx` | btree (pref_label_nl) |

### Terminology Statistics

| Vocabulary | Concepts |
|------------|----------|
| Alliander Poolparty - Glossary | 3,098 |
| eur-lex | 550 |
| LIDO-BWBR0037940 | 222 |
| IEC 61970 - Core Equipment (CGMES) | 210 |
| esa | 134 |
| **TOTAL** | **4,688** |

---

## 6. EVALUATION RESULTS

### Results by Category (Post-Fix)

| Category | Recall@5 | MRR | NDCG@5 | Assessment |
|----------|----------|-----|--------|------------|
| **governance_dutch** | 0.910 | 1.000 | 0.991 | Excellent |
| **principle_semantic** | 0.794 | 1.000 | 1.000 | Excellent |
| **principle_exact** | 0.774 | 1.000 | 1.000 | Excellent |
| **process** | 0.670 | 1.000 | 0.821 | Good |
| **energy_standards** | 0.667 | 1.000 | 0.830 | Good |
| **adr_exact** | 0.568 | 1.000 | 1.000 | Good |
| **adr_semantic** | 0.495 | 0.917 | 0.916 | Moderate |
| **cross_document** | 0.309 | 0.750 | 0.759 | Needs work |
| **energy_semantic** | 0.292 | 1.000 | 0.491 | Needs work |
| **bilingual_dutch** | 0.083 | 0.271 | 0.138 | Poor |

### Comparison: Before vs After Fixes

| Category | Before | After | Change |
|----------|--------|-------|--------|
| **energy_standards** | 0.000 | 0.667 | **+66.7%** |
| governance_dutch | 0.910 | 0.910 | — |
| principle_semantic | 0.794 | 0.794 | — |
| principle_exact | 0.774 | 0.774 | — |
| process | 0.670 | 0.670 | — |
| adr_exact | 0.568 | 0.568 | — |
| adr_semantic | 0.495 | 0.495 | — |
| cross_document | 0.309 | 0.309 | — |
| energy_semantic | 0.292 | 0.292 | — |
| bilingual_dutch | 0.189 | 0.083 | -10.6% |

---

## 7. SUMMARY

### Component Status

| Component | Status | Notes |
|-----------|--------|-------|
| **HNSW Vector Index** | ✅ Active | Using `vector_cosine_ops` |
| **BM25 Full-Text (EN)** | ✅ Active | GIN index on `search_vector_en` |
| **BM25 Full-Text (NL)** | ✅ Active | GIN index on `search_vector_nl` |
| **Contextual Prefixes** | ✅ Implemented | All document types have context |
| **Embedding Model** | ✅ Consistent | All 433 chunks use `text-embedding-3-small` |
| **Hybrid Search** | ✅ Working | Alpha-weighted combination |
| **Query Type Detection** | ✅ Improved | Updated regex patterns |
| **PDF Hierarchical Parser** | ✅ NEW | Max 2000 chars per chunk |

### Fixes Applied

| Issue | Fix | Result |
|-------|-----|--------|
| Policy chunks too large (31,022 chars) | Hierarchical PDF parser | Max now 2,158 chars |
| Policy documents missing document_id | Extract from filename/metadata | All policies have IDs |
| Energy standards queries failing | Added to semantic triggers | 66.7% recall (was 0%) |
| Query type detection inaccurate | Improved regex patterns | Better ID recognition |

### Remaining Issues

1. **Bilingual search underperforming** - 8.3% recall on Dutch→English queries (regression)
2. **Cross-document queries** - 31% recall needs improvement
3. **ADR semantic queries** - 49.5% recall could be improved

### Recommendations

1. **Fix bilingual golden dataset** - Review expected documents for Dutch queries
2. **Add cross-encoder reranking** - For improved ranking on cross-document queries
3. **Tune bilingual alpha** - Lower alpha (more lexical) for cross-language queries
4. **Expand ADR content coverage** - May need more context in chunks
