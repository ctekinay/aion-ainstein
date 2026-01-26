"""
CRUD operations for chunks and terminology tables.
"""

import json
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class ChunkRecord:
    """Represents a chunk record for database operations."""

    content: str
    embedding: List[float]
    source_file: str
    document_type: str
    chunk_index: int
    total_chunks: Optional[int] = None
    section_header: Optional[str] = None
    parent_header: Optional[str] = None
    document_id: Optional[str] = None
    document_title: Optional[str] = None
    document_status: Optional[str] = None
    owner_team: Optional[str] = None
    owner_team_abbr: Optional[str] = None
    owner_department: Optional[str] = None
    owner_organization: Optional[str] = None
    metadata: Optional[dict] = None
    embedding_model: Optional[str] = None
    embedding_model_version: Optional[str] = None


@dataclass
class TerminologyRecord:
    """Represents a terminology record for database operations."""

    concept_uri: str
    embedding: List[float]
    pref_label_en: Optional[str] = None
    pref_label_nl: Optional[str] = None
    alt_labels: Optional[List[str]] = None
    definition: Optional[str] = None
    broader_uri: Optional[str] = None
    narrower_uris: Optional[List[str]] = None
    related_uris: Optional[List[str]] = None
    in_scheme: Optional[str] = None
    notation: Optional[str] = None
    vocabulary_name: Optional[str] = None


def insert_chunk(conn, chunk: ChunkRecord) -> int:
    """Insert a single chunk into the database."""
    query = """
        INSERT INTO chunks
        (content, embedding, source_file, document_type, chunk_index,
         total_chunks, section_header, parent_header, document_id, document_title,
         document_status, owner_team, owner_team_abbr, owner_department,
         owner_organization, metadata, embedding_model, embedding_model_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (
                chunk.content,
                chunk.embedding,
                chunk.source_file,
                chunk.document_type,
                chunk.chunk_index,
                chunk.total_chunks,
                chunk.section_header,
                chunk.parent_header,
                chunk.document_id,
                chunk.document_title,
                chunk.document_status,
                chunk.owner_team,
                chunk.owner_team_abbr,
                chunk.owner_department,
                chunk.owner_organization,
                json.dumps(chunk.metadata) if chunk.metadata else "{}",
                chunk.embedding_model,
                chunk.embedding_model_version,
            ),
        )
        result = cur.fetchone()
        return result[0] if result else None


def insert_chunks_batch(conn, chunks: List[ChunkRecord]) -> List[int]:
    """Insert multiple chunks in a batch."""
    query = """
        INSERT INTO chunks
        (content, embedding, source_file, document_type, chunk_index,
         total_chunks, section_header, parent_header, document_id, document_title,
         document_status, owner_team, owner_team_abbr, owner_department,
         owner_organization, metadata, embedding_model, embedding_model_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    ids = []
    with conn.cursor() as cur:
        for chunk in chunks:
            cur.execute(
                query,
                (
                    chunk.content,
                    chunk.embedding,
                    chunk.source_file,
                    chunk.document_type,
                    chunk.chunk_index,
                    chunk.total_chunks,
                    chunk.section_header,
                    chunk.parent_header,
                    chunk.document_id,
                    chunk.document_title,
                    chunk.document_status,
                    chunk.owner_team,
                    chunk.owner_team_abbr,
                    chunk.owner_department,
                    chunk.owner_organization,
                    json.dumps(chunk.metadata) if chunk.metadata else "{}",
                    chunk.embedding_model,
                    chunk.embedding_model_version,
                ),
            )
            result = cur.fetchone()
            if result:
                ids.append(result[0])
    conn.commit()
    return ids


def insert_terminology(conn, term: TerminologyRecord) -> int:
    """Insert or update a terminology record."""
    query = """
        INSERT INTO terminology
        (concept_uri, pref_label_en, pref_label_nl, alt_labels,
         definition, broader_uri, narrower_uris, related_uris,
         in_scheme, notation, vocabulary_name, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (concept_uri) DO UPDATE SET
            pref_label_en = EXCLUDED.pref_label_en,
            pref_label_nl = EXCLUDED.pref_label_nl,
            alt_labels = EXCLUDED.alt_labels,
            definition = EXCLUDED.definition,
            broader_uri = EXCLUDED.broader_uri,
            narrower_uris = EXCLUDED.narrower_uris,
            related_uris = EXCLUDED.related_uris,
            in_scheme = EXCLUDED.in_scheme,
            notation = EXCLUDED.notation,
            vocabulary_name = EXCLUDED.vocabulary_name,
            embedding = EXCLUDED.embedding,
            indexed_at = CURRENT_TIMESTAMP
        RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (
                term.concept_uri,
                term.pref_label_en,
                term.pref_label_nl,
                term.alt_labels or [],
                term.definition,
                term.broader_uri,
                term.narrower_uris or [],
                term.related_uris or [],
                term.in_scheme,
                term.notation,
                term.vocabulary_name,
                term.embedding,
            ),
        )
        result = cur.fetchone()
        conn.commit()
        return result[0] if result else None


def insert_terminology_batch(conn, terms: List[TerminologyRecord]) -> List[int]:
    """Insert multiple terminology records in a batch."""
    ids = []
    for term in terms:
        term_id = insert_terminology(conn, term)
        if term_id:
            ids.append(term_id)
    return ids


def get_chunk_by_id(conn, chunk_id: int) -> Optional[dict]:
    """
    Retrieve a single chunk by its ID.

    Returns:
        Dict with all chunk fields, or None if not found
    """
    query = """
        SELECT id, content, document_id, document_type, document_title,
               section_header, source_file, chunk_index, total_chunks,
               owner_team, owner_team_abbr, owner_department, owner_organization,
               document_status, metadata, embedding_model, indexed_at
        FROM chunks WHERE id = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (chunk_id,))
        row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "content": row[1],
        "document_id": row[2],
        "document_type": row[3],
        "document_title": row[4],
        "section_header": row[5],
        "source_file": row[6],
        "chunk_index": row[7],
        "total_chunks": row[8],
        "owner_team": row[9],
        "owner_team_abbr": row[10],
        "owner_department": row[11],
        "owner_organization": row[12],
        "document_status": row[13],
        "metadata": row[14],
        "embedding_model": row[15],
        "indexed_at": row[16],
    }


def get_terminology_by_id(conn, term_id: int) -> Optional[dict]:
    """
    Retrieve a single terminology concept by its ID.

    Returns:
        Dict with all terminology fields, or None if not found
    """
    query = """
        SELECT id, concept_uri, pref_label_en, pref_label_nl, alt_labels,
               definition, broader_uri, narrower_uris, related_uris,
               in_scheme, notation, vocabulary_name, indexed_at
        FROM terminology WHERE id = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (term_id,))
        row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "concept_uri": row[1],
        "pref_label_en": row[2],
        "pref_label_nl": row[3],
        "alt_labels": row[4],
        "definition": row[5],
        "broader_uri": row[6],
        "narrower_uris": row[7],
        "related_uris": row[8],
        "in_scheme": row[9],
        "notation": row[10],
        "vocabulary_name": row[11],
        "indexed_at": row[12],
    }


def get_terminology_by_uri(conn, concept_uri: str) -> Optional[dict]:
    """
    Retrieve a terminology concept by its URI.

    Returns:
        Dict with all terminology fields, or None if not found
    """
    query = """
        SELECT id, concept_uri, pref_label_en, pref_label_nl, alt_labels,
               definition, broader_uri, narrower_uris, related_uris,
               in_scheme, notation, vocabulary_name, indexed_at
        FROM terminology WHERE concept_uri = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (concept_uri,))
        row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "concept_uri": row[1],
        "pref_label_en": row[2],
        "pref_label_nl": row[3],
        "alt_labels": row[4],
        "definition": row[5],
        "broader_uri": row[6],
        "narrower_uris": row[7],
        "related_uris": row[8],
        "in_scheme": row[9],
        "notation": row[10],
        "vocabulary_name": row[11],
        "indexed_at": row[12],
    }


def get_chunk_count_by_type(conn) -> dict:
    """Get chunk counts grouped by document type."""
    query = "SELECT document_type, COUNT(*) FROM chunks GROUP BY document_type"
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    return {row[0]: row[1] for row in rows}


def get_terminology_count(conn) -> int:
    """Get total terminology count."""
    query = "SELECT COUNT(*) FROM terminology"
    with conn.cursor() as cur:
        cur.execute(query)
        result = cur.fetchone()
    return result[0] if result else 0


def get_terminology_count_by_vocabulary(conn) -> dict:
    """Get terminology counts grouped by vocabulary."""
    query = "SELECT vocabulary_name, COUNT(*) FROM terminology GROUP BY vocabulary_name"
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    return {row[0] or "Unknown": row[1] for row in rows}


def clear_chunks(conn, document_type: Optional[str] = None):
    """Clear all chunks or chunks of a specific type."""
    if document_type:
        query = "DELETE FROM chunks WHERE document_type = %s"
        with conn.cursor() as cur:
            cur.execute(query, (document_type,))
    else:
        query = "TRUNCATE TABLE chunks RESTART IDENTITY CASCADE"
        with conn.cursor() as cur:
            cur.execute(query)
    conn.commit()


def clear_terminology(conn, vocabulary_name: Optional[str] = None):
    """Clear all terminology or terminology from a specific vocabulary."""
    if vocabulary_name:
        query = "DELETE FROM terminology WHERE vocabulary_name = %s"
        with conn.cursor() as cur:
            cur.execute(query, (vocabulary_name,))
    else:
        query = "TRUNCATE TABLE terminology RESTART IDENTITY CASCADE"
        with conn.cursor() as cur:
            cur.execute(query)
    conn.commit()


def insert_document_relationship(
    conn,
    source_doc_id: str,
    target_doc_id: str,
    relationship_type: str,
    confidence: float = 1.0,
    extracted_by: str = "manual",
    notes: Optional[str] = None,
) -> int:
    """Insert a document relationship."""
    query = """
        INSERT INTO document_relationships
        (source_doc_id, target_doc_id, relationship_type, confidence, extracted_by, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_doc_id, target_doc_id, relationship_type) DO UPDATE SET
            confidence = EXCLUDED.confidence,
            extracted_by = EXCLUDED.extracted_by,
            notes = EXCLUDED.notes
        RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (source_doc_id, target_doc_id, relationship_type, confidence, extracted_by, notes),
        )
        result = cur.fetchone()
        conn.commit()
        return result[0] if result else None
