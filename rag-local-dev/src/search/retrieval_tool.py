"""
Agent-oriented retrieval interface.
Provides structured outputs with confidence scores and explicit failure signals.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import time
import uuid
import logging
import re

from .hybrid_search import hybrid_search, terminology_lookup, get_document_chunks, SearchResult
from .query_processor import preprocess_query

logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    """A chunk result for agent consumption."""

    chunk_id: int
    content: str
    score: float
    source_file: str
    document_id: Optional[str]
    document_type: str
    document_title: Optional[str]
    section_header: Optional[str]
    owner_team: Optional[str] = None


@dataclass
class TermResult:
    """A terminology result for agent consumption."""

    concept_uri: str
    pref_label: str
    definition: Optional[str]
    score: float
    vocabulary_name: Optional[str] = None


@dataclass
class RetrievalResult:
    """Complete retrieval result with metadata for agents."""

    chunks: List[ChunkResult]
    terminology_matches: List[TermResult]

    # Agent-critical metadata
    confidence: float
    query_type_detected: str
    no_good_results: bool
    suggested_refinements: List[str]

    # Provenance
    query_id: str
    latency_ms: int


class RetrievalTool:
    """Agent-oriented retrieval interface."""

    def __init__(self, conn, embedder, config: dict):
        """
        Initialize retrieval tool.

        Args:
            conn: PostgreSQL database connection
            embedder: EmbeddingProvider instance
            config: Configuration dictionary
        """
        self.conn = conn
        self.embedder = embedder
        self.config = config

    def search(
        self,
        query: str,
        doc_types: Optional[List[str]] = None,
        min_confidence: float = 0.4,
        max_chunks: int = 5,
        include_terminology: bool = True,
        alpha: Optional[float] = None,
    ) -> RetrievalResult:
        """
        Main search method for agents.

        Returns structured result with confidence score and explicit
        'no_good_results' flag so agents don't have to guess.

        Args:
            query: Search query
            doc_types: Filter by document types (e.g., ['adr', 'principle'])
            min_confidence: Minimum confidence threshold for "good" results
            max_chunks: Maximum number of chunks to return
            include_terminology: Whether to include terminology lookup
            alpha: Override alpha value for hybrid search

        Returns:
            RetrievalResult with chunks, terminology, and metadata
        """
        start_time = time.time()
        query_id = str(uuid.uuid4())

        # Preprocess query
        processed = preprocess_query(query, self.config)
        logger.info(f"Query processed: type={processed['query_type']}, lang={processed['language']}")

        # Handle exact match queries (document IDs)
        if processed["query_type"] == "exact_match":
            return self._handle_exact_match(query, processed, query_id, start_time)

        # Use provided alpha or preprocessor's recommendation
        search_alpha = alpha if alpha is not None else processed["alpha"]

        # Generate query embedding
        query_embedding = self.embedder.embed_single(processed["expanded"])

        # Execute hybrid search
        results = hybrid_search(
            self.conn,
            query_embedding,
            processed["expanded"],
            language=processed["language"],
            alpha=search_alpha,
            k=max_chunks,
            document_types=doc_types,
        )

        # Convert to ChunkResult
        chunks = [
            ChunkResult(
                chunk_id=r.chunk_id,
                content=r.content,
                score=r.hybrid_score,
                source_file=r.source_file,
                document_id=r.document_id,
                document_type=r.document_type,
                document_title=r.document_title,
                section_header=r.section_header,
                owner_team=r.owner_team,
            )
            for r in results
        ]

        # Terminology lookup if requested
        term_results = []
        if include_terminology:
            terms = terminology_lookup(self.conn, query, query_embedding, k=3)
            term_results = [
                TermResult(
                    concept_uri=t["concept_uri"],
                    pref_label=t["pref_label_en"] or t["pref_label_nl"] or "",
                    definition=t["definition"],
                    score=float(t["similarity"] or 0),
                    vocabulary_name=t["vocabulary_name"],
                )
                for t in terms
            ]

        # Calculate confidence
        if chunks:
            top_score = chunks[0].score
            confidence = top_score
        else:
            confidence = 0.0

        # Determine if results are good enough
        no_good_results = confidence < min_confidence

        # Generate refinement suggestions if results are poor
        suggested_refinements = []
        if no_good_results:
            suggested_refinements = self._generate_refinements(query, processed)

        latency_ms = int((time.time() - start_time) * 1000)

        # Log the retrieval
        self._log_retrieval(
            query_id, query, query_embedding, processed, search_alpha, chunks, latency_ms
        )

        return RetrievalResult(
            chunks=chunks,
            terminology_matches=term_results,
            confidence=confidence,
            query_type_detected=processed["query_type"],
            no_good_results=no_good_results,
            suggested_refinements=suggested_refinements,
            query_id=query_id,
            latency_ms=latency_ms,
        )

    def _handle_exact_match(
        self, query: str, processed: dict, query_id: str, start_time: float
    ) -> RetrievalResult:
        """Handle exact match queries for document IDs."""
        # Extract document ID from query
        doc_id = self._extract_document_id(query)

        if doc_id:
            results = get_document_chunks(self.conn, doc_id)
            chunks = [
                ChunkResult(
                    chunk_id=r.chunk_id,
                    content=r.content,
                    score=r.hybrid_score,
                    source_file=r.source_file,
                    document_id=r.document_id,
                    document_type=r.document_type,
                    document_title=r.document_title,
                    section_header=r.section_header,
                    owner_team=r.owner_team,
                )
                for r in results
            ]

            confidence = 1.0 if chunks else 0.0
            no_good_results = len(chunks) == 0
        else:
            chunks = []
            confidence = 0.0
            no_good_results = True

        latency_ms = int((time.time() - start_time) * 1000)

        return RetrievalResult(
            chunks=chunks,
            terminology_matches=[],
            confidence=confidence,
            query_type_detected="exact_match",
            no_good_results=no_good_results,
            suggested_refinements=["Try a semantic search if this document ID doesn't exist"]
            if no_good_results
            else [],
            query_id=query_id,
            latency_ms=latency_ms,
        )

    def _extract_document_id(self, query: str) -> Optional[str]:
        """Extract document ID from query."""
        # Try ADR pattern
        match = re.match(r"^(ADR)-?(\d+)", query, re.IGNORECASE)
        if match:
            return f"ADR-{match.group(2).zfill(4)}"

        # Try PRINCIPLE pattern
        match = re.match(r"^(PRINCIPLE)-?(\d+)", query, re.IGNORECASE)
        if match:
            return f"PRINCIPLE-{match.group(2).zfill(4)}"

        # Try GOV-PRINCIPLE pattern
        match = re.match(r"^(GOV-PRINCIPLE)-?(\d+)", query, re.IGNORECASE)
        if match:
            return f"GOV-PRINCIPLE-{match.group(2).zfill(4)}"

        return None

    def get_document_by_id(self, doc_id: str) -> Optional[List[ChunkResult]]:
        """Retrieve all chunks for a specific document ID."""
        results = get_document_chunks(self.conn, doc_id)

        if not results:
            return None

        return [
            ChunkResult(
                chunk_id=r.chunk_id,
                content=r.content,
                score=1.0,
                document_id=r.document_id,
                document_type=r.document_type,
                document_title=r.document_title,
                section_header=r.section_header,
                source_file=r.source_file,
                owner_team=r.owner_team,
            )
            for r in results
        ]

    def _generate_refinements(self, query: str, processed: dict) -> List[str]:
        """Suggest query refinements when results are poor."""
        suggestions = []

        if processed["query_type"] == "terminology":
            suggestions.append(f"Try a more descriptive query: 'What is {query}?'")

        if len(query.split()) <= 3:
            suggestions.append("Try adding more context to your query")

        suggestions.append("Try searching for related ADRs or Principles by ID if known")
        suggestions.append("Check if the terminology exists in the SKOS vocabularies")

        return suggestions

    def _log_retrieval(
        self, query_id, query, embedding, processed, alpha, chunks, latency_ms
    ):
        """Log retrieval for analysis and tuning."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO retrieval_logs
                    (query_text, query_embedding, query_language, detected_query_type,
                     alpha_used, retrieved_chunk_ids, scores, latency_ms, result_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        query,
                        embedding,
                        processed["language"],
                        processed["query_type"],
                        alpha,
                        [c.chunk_id for c in chunks],
                        [c.score for c in chunks],
                        latency_ms,
                        len(chunks),
                    ),
                )
                self.conn.commit()
        except Exception as e:
            logger.warning(f"Failed to log retrieval: {e}")
            # Don't fail search if logging fails


def list_available_documents(conn, document_type: Optional[str] = None) -> List[dict]:
    """
    List all available documents in the database.

    Args:
        conn: Database connection
        document_type: Optional filter by document type

    Returns:
        List of document info dicts
    """
    query = """
        SELECT DISTINCT
            document_id,
            document_type,
            document_title,
            owner_team,
            COUNT(*) as chunk_count
        FROM chunks
        WHERE document_id IS NOT NULL
    """

    params = {}
    if document_type:
        query += " AND document_type = %(document_type)s"
        params["document_type"] = document_type

    query += " GROUP BY document_id, document_type, document_title, owner_team ORDER BY document_id"

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        {
            "document_id": row[0],
            "document_type": row[1],
            "document_title": row[2],
            "owner_team": row[3],
            "chunk_count": row[4],
        }
        for row in rows
    ]


def get_collection_stats(conn) -> dict:
    """Get statistics about the indexed collections."""
    stats = {}

    # Chunk counts by type
    with conn.cursor() as cur:
        cur.execute("SELECT document_type, COUNT(*) FROM chunks GROUP BY document_type")
        stats["chunks_by_type"] = {row[0]: row[1] for row in cur.fetchall()}

    # Total chunks
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM chunks")
        stats["total_chunks"] = cur.fetchone()[0]

    # Terminology counts
    with conn.cursor() as cur:
        cur.execute("SELECT vocabulary_name, COUNT(*) FROM terminology GROUP BY vocabulary_name")
        stats["terminology_by_vocabulary"] = {
            row[0] or "Unknown": row[1] for row in cur.fetchall()
        }

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM terminology")
        stats["total_terminology"] = cur.fetchone()[0]

    # Document counts
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(DISTINCT document_id) FROM chunks WHERE document_id IS NOT NULL")
        stats["total_documents"] = cur.fetchone()[0]

    return stats
