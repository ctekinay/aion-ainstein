"""
Hybrid search combining vector similarity and BM25 full-text search.

IMPORTANT: The cosine distance operator <=> returns values in [0, 2], not [0, 1].
We normalize by dividing by 2 to get proper [0, 1] range for score combination.
"""

from typing import List, Optional
from dataclasses import dataclass
import logging

from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Represents a search result from hybrid search."""

    chunk_id: int
    content: str
    vector_score: float
    bm25_score: float
    hybrid_score: float
    document_id: Optional[str]
    document_type: str
    document_title: Optional[str]
    section_header: Optional[str]
    source_file: str
    owner_team: Optional[str]
    metadata: dict


def hybrid_search(
    conn,
    query_embedding: List[float],
    query_text: str,
    language: str = "en",
    alpha: float = 0.7,
    k: int = 10,
    document_types: Optional[List[str]] = None,
    owner_teams: Optional[List[str]] = None,
) -> List[SearchResult]:
    """
    Execute hybrid search combining vector similarity and BM25.

    Args:
        conn: Database connection
        query_embedding: Query vector from embedding model
        query_text: Original query text for BM25
        language: 'en', 'nl', or 'both'
        alpha: Weight for vector score (0-1). Higher = more semantic.
        k: Number of results to return
        document_types: Filter by document type (optional)
        owner_teams: Filter by owner team (optional)

    Returns:
        List of SearchResult ordered by hybrid score descending
    """
    # Build language-aware BM25 scoring
    if language == "nl":
        bm25_expr = "ts_rank_cd(search_vector_nl, plainto_tsquery('dutch', %(query_text)s))"
    elif language == "en":
        bm25_expr = "ts_rank_cd(search_vector_en, plainto_tsquery('english', %(query_text)s))"
    else:  # both
        bm25_expr = """GREATEST(
            ts_rank_cd(search_vector_en, plainto_tsquery('english', %(query_text)s)),
            ts_rank_cd(search_vector_nl, plainto_tsquery('dutch', %(query_text)s))
        )"""

    # Build query
    # CRITICAL: <=> returns cosine distance [0,2], normalize to [0,1] by dividing by 2
    query = f"""
        SELECT
            id,
            content,
            document_id,
            document_type,
            document_title,
            section_header,
            source_file,
            owner_team,
            metadata,
            (1 - (embedding <=> %(embedding)s::vector) / 2) AS vector_score,
            {bm25_expr} AS bm25_score,
            %(alpha)s * (1 - (embedding <=> %(embedding)s::vector) / 2) +
            (1 - %(alpha)s) * COALESCE({bm25_expr}, 0) AS hybrid_score
        FROM chunks
        WHERE embedding IS NOT NULL
    """

    params = {
        "embedding": query_embedding,
        "query_text": query_text,
        "alpha": alpha,
    }

    # Add document type filter if specified
    if document_types:
        query += " AND document_type = ANY(%(document_types)s)"
        params["document_types"] = document_types

    # Add owner team filter if specified
    if owner_teams:
        query += " AND owner_team = ANY(%(owner_teams)s)"
        params["owner_teams"] = owner_teams

    query += " ORDER BY hybrid_score DESC LIMIT %(k)s"
    params["k"] = k

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        SearchResult(
            chunk_id=row["id"],
            content=row["content"],
            vector_score=float(row["vector_score"] or 0),
            bm25_score=float(row["bm25_score"] or 0),
            hybrid_score=float(row["hybrid_score"] or 0),
            document_id=row["document_id"],
            document_type=row["document_type"],
            document_title=row["document_title"],
            section_header=row["section_header"],
            source_file=row["source_file"],
            owner_team=row["owner_team"],
            metadata=row["metadata"] or {},
        )
        for row in rows
    ]


def vector_search(
    conn,
    query_embedding: List[float],
    k: int = 10,
    document_types: Optional[List[str]] = None,
) -> List[SearchResult]:
    """
    Execute pure vector similarity search.

    Useful for semantic queries where BM25 might not help.
    """
    query = """
        SELECT
            id,
            content,
            document_id,
            document_type,
            document_title,
            section_header,
            source_file,
            owner_team,
            metadata,
            (1 - (embedding <=> %(embedding)s::vector) / 2) AS vector_score
        FROM chunks
        WHERE embedding IS NOT NULL
    """

    params = {"embedding": query_embedding}

    if document_types:
        query += " AND document_type = ANY(%(document_types)s)"
        params["document_types"] = document_types

    query += " ORDER BY embedding <=> %(embedding)s::vector LIMIT %(k)s"
    params["k"] = k

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        SearchResult(
            chunk_id=row["id"],
            content=row["content"],
            vector_score=float(row["vector_score"] or 0),
            bm25_score=0.0,
            hybrid_score=float(row["vector_score"] or 0),
            document_id=row["document_id"],
            document_type=row["document_type"],
            document_title=row["document_title"],
            section_header=row["section_header"],
            source_file=row["source_file"],
            owner_team=row["owner_team"],
            metadata=row["metadata"] or {},
        )
        for row in rows
    ]


def terminology_lookup(
    conn,
    query_text: str,
    query_embedding: List[float],
    k: int = 5,
    vocabulary_names: Optional[List[str]] = None,
) -> List[dict]:
    """
    Search terminology table for concept matches.
    Combines exact label matching with vector similarity.
    """
    query = """
        SELECT
            id,
            concept_uri,
            pref_label_en,
            pref_label_nl,
            alt_labels,
            definition,
            broader_uri,
            narrower_uris,
            vocabulary_name,
            (1 - (embedding <=> %(embedding)s::vector) / 2) AS similarity
        FROM terminology
        WHERE
            (pref_label_en ILIKE %(search_pattern)s
            OR pref_label_nl ILIKE %(search_pattern)s
            OR %(query_text)s = ANY(alt_labels)
            OR (embedding IS NOT NULL AND (1 - (embedding <=> %(embedding)s::vector) / 2) > 0.5))
    """

    params = {
        "embedding": query_embedding,
        "query_text": query_text,
        "search_pattern": f"%{query_text}%",
    }

    if vocabulary_names:
        query += " AND vocabulary_name = ANY(%(vocabulary_names)s)"
        params["vocabulary_names"] = vocabulary_names

    query += " ORDER BY similarity DESC NULLS LAST LIMIT %(k)s"
    params["k"] = k

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [dict(row) for row in rows]


def get_document_chunks(conn, document_id: str) -> List[SearchResult]:
    """
    Retrieve all chunks for a specific document ID.

    Useful for exact match queries like "ADR-0001".
    """
    query = """
        SELECT
            id,
            content,
            document_id,
            document_type,
            document_title,
            section_header,
            source_file,
            owner_team,
            metadata
        FROM chunks
        WHERE document_id = %(document_id)s
        ORDER BY chunk_index
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, {"document_id": document_id})
        rows = cur.fetchall()

    return [
        SearchResult(
            chunk_id=row["id"],
            content=row["content"],
            vector_score=1.0,  # Exact match
            bm25_score=1.0,
            hybrid_score=1.0,
            document_id=row["document_id"],
            document_type=row["document_type"],
            document_title=row["document_title"],
            section_header=row["section_header"],
            source_file=row["source_file"],
            owner_team=row["owner_team"],
            metadata=row["metadata"] or {},
        )
        for row in rows
    ]
