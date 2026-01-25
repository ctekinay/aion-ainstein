-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Main chunks table
CREATE TABLE chunks (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI text-embedding-3-small dimensions

    -- Source tracking
    source_file TEXT NOT NULL,
    document_type TEXT NOT NULL,  -- 'adr', 'principle', 'policy'
    chunk_index INTEGER NOT NULL,
    total_chunks INTEGER,

    -- Structure metadata
    section_header TEXT,
    parent_header TEXT,

    -- Document identification
    document_id TEXT,           -- e.g., "ADR-001", "PRINCIPLE-012"
    document_title TEXT,
    document_status TEXT,       -- For ADRs: proposed, accepted, deprecated

    -- Ownership metadata (for DSO attribution)
    owner_team TEXT,            -- e.g., "Energy System Architecture"
    owner_team_abbr TEXT,       -- e.g., "ESA"
    owner_department TEXT,      -- e.g., "System Operations"
    owner_organization TEXT,    -- e.g., "Alliander"

    -- Extensible metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Full-text search vectors (bilingual)
    search_vector_en tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    search_vector_nl tsvector GENERATED ALWAYS AS (to_tsvector('dutch', content)) STORED,

    -- Timestamps
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_modified_at TIMESTAMP,

    -- Embedding metadata
    embedding_model TEXT,
    embedding_model_version TEXT
);

-- Indexes for chunks
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_search_en_idx ON chunks USING GIN (search_vector_en);
CREATE INDEX chunks_search_nl_idx ON chunks USING GIN (search_vector_nl);
CREATE INDEX chunks_document_type_idx ON chunks (document_type);
CREATE INDEX chunks_document_id_idx ON chunks (document_id);
CREATE INDEX chunks_source_file_idx ON chunks (source_file);
CREATE INDEX chunks_metadata_idx ON chunks USING GIN (metadata);
CREATE INDEX chunks_owner_team_idx ON chunks (owner_team);

-- Separate terminology table for SKOS concepts
-- (SKOS concepts are sparse and need different handling than document chunks)
CREATE TABLE terminology (
    id SERIAL PRIMARY KEY,
    concept_uri TEXT UNIQUE NOT NULL,
    pref_label_en TEXT,
    pref_label_nl TEXT,
    alt_labels TEXT[],
    definition TEXT,
    broader_uri TEXT,
    narrower_uris TEXT[],
    related_uris TEXT[],
    in_scheme TEXT,             -- Which vocabulary/scheme this belongs to
    notation TEXT,              -- Standard notation (e.g., IEC code)
    vocabulary_name TEXT,       -- Human-readable vocabulary name
    embedding vector(1536),
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', COALESCE(pref_label_en, '') || ' ' ||
                              COALESCE(pref_label_nl, '') || ' ' ||
                              COALESCE(array_to_string(alt_labels, ' '), '') || ' ' ||
                              COALESCE(definition, ''))
    ) STORED,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX terminology_embedding_idx ON terminology USING hnsw (embedding vector_cosine_ops);
CREATE INDEX terminology_search_idx ON terminology USING GIN (search_vector);
CREATE INDEX terminology_pref_en_idx ON terminology (pref_label_en);
CREATE INDEX terminology_pref_nl_idx ON terminology (pref_label_nl);
CREATE INDEX terminology_vocabulary_idx ON terminology (vocabulary_name);
CREATE INDEX terminology_in_scheme_idx ON terminology (in_scheme);

-- Retrieval logging for tuning and debugging
CREATE TABLE retrieval_logs (
    id SERIAL PRIMARY KEY,
    query_text TEXT NOT NULL,
    query_embedding vector(1536),
    query_language TEXT,
    detected_query_type TEXT,  -- 'semantic', 'exact_match', 'terminology', 'mixed'
    alpha_used FLOAT,
    retrieved_chunk_ids INTEGER[],
    scores FLOAT[],
    latency_ms INTEGER,
    result_count INTEGER,

    -- Feedback (populated later for tuning)
    feedback_signal TEXT,      -- 'useful', 'irrelevant', 'partial'
    feedback_notes TEXT,

    -- Context
    session_id TEXT,
    agent_id TEXT,             -- NULL for human queries

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX retrieval_logs_created_idx ON retrieval_logs (created_at);
CREATE INDEX retrieval_logs_session_idx ON retrieval_logs (session_id);

-- Document relationships (for tracking ADR supersedes, principle dependencies)
CREATE TABLE document_relationships (
    id SERIAL PRIMARY KEY,
    source_doc_id TEXT NOT NULL,
    target_doc_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,  -- 'supersedes', 'implements', 'relates_to'
    confidence FLOAT DEFAULT 1.0,
    extracted_by TEXT,                -- 'frontmatter', 'manual', 'llm'
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_doc_id, target_doc_id, relationship_type)
);

CREATE INDEX doc_rel_source_idx ON document_relationships (source_doc_id);
CREATE INDEX doc_rel_target_idx ON document_relationships (target_doc_id);
