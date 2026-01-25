"""
FastAPI application providing search endpoints.
"""

import os
from contextlib import asynccontextmanager
from typing import List, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from ..database.connection import get_db_connection
from ..embedding.factory import get_embedder
from ..search.retrieval_tool import RetrievalTool, list_available_documents, get_collection_stats


# Global instances (initialized on startup)
_config = None
_embedder = None


def load_config():
    """Load configuration from config.yaml."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    global _config, _embedder

    _config = load_config()
    _embedder = get_embedder(_config)

    yield

    # Cleanup (if needed)


app = FastAPI(
    title="RAG Search API",
    description="Hybrid search API for architectural documentation, principles, and terminology",
    version="1.0.0",
    lifespan=lifespan,
)


# Request/Response Models


class SearchRequest(BaseModel):
    """Search request payload."""

    query: str = Field(..., description="Search query")
    doc_types: Optional[List[str]] = Field(
        None, description="Filter by document types (adr, principle, governance_principle, policy)"
    )
    max_results: int = Field(5, ge=1, le=50, description="Maximum number of results")
    include_terminology: bool = Field(True, description="Include terminology lookup")
    alpha: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Override alpha for hybrid search (0=BM25, 1=vector)"
    )
    min_confidence: float = Field(0.4, ge=0.0, le=1.0, description="Minimum confidence threshold")


class ChunkResponse(BaseModel):
    """A chunk in the search response."""

    chunk_id: int
    content: str
    score: float
    document_id: Optional[str]
    document_type: str
    document_title: Optional[str]
    section_header: Optional[str]
    source_file: str
    owner_team: Optional[str]


class TerminologyResponse(BaseModel):
    """A terminology match in the search response."""

    concept_uri: str
    pref_label: str
    definition: Optional[str]
    score: float
    vocabulary_name: Optional[str]


class SearchResponse(BaseModel):
    """Search response payload."""

    chunks: List[ChunkResponse]
    terminology_matches: List[TerminologyResponse]
    confidence: float
    query_type: str
    no_good_results: bool
    suggested_refinements: List[str]
    query_id: str
    latency_ms: int


class DocumentResponse(BaseModel):
    """Response for document retrieval."""

    document_id: str
    document_type: Optional[str]
    document_title: Optional[str]
    chunks: List[ChunkResponse]


class DocumentListItem(BaseModel):
    """An item in the document list."""

    document_id: str
    document_type: str
    document_title: Optional[str]
    owner_team: Optional[str]
    chunk_count: int


class StatsResponse(BaseModel):
    """Collection statistics response."""

    total_chunks: int
    total_documents: int
    total_terminology: int
    chunks_by_type: dict
    terminology_by_vocabulary: dict


# Endpoints


@app.post("/search", response_model=SearchResponse)
def search(request: SearchRequest):
    """
    Execute hybrid search combining vector similarity and BM25.

    The search automatically detects query type and adjusts parameters:
    - Exact match (ADR-001, PRINCIPLE-0010): Returns specific document
    - Semantic: Uses higher vector weight
    - Terminology: Includes SKOS concept lookup
    - Mixed: Balanced hybrid search
    """
    conn = get_db_connection(_config)

    try:
        tool = RetrievalTool(conn, _embedder, _config)

        result = tool.search(
            query=request.query,
            doc_types=request.doc_types,
            max_chunks=request.max_results,
            include_terminology=request.include_terminology,
            alpha=request.alpha,
            min_confidence=request.min_confidence,
        )

        return SearchResponse(
            chunks=[
                ChunkResponse(
                    chunk_id=c.chunk_id,
                    content=c.content,
                    score=c.score,
                    document_id=c.document_id,
                    document_type=c.document_type,
                    document_title=c.document_title,
                    section_header=c.section_header,
                    source_file=c.source_file,
                    owner_team=c.owner_team,
                )
                for c in result.chunks
            ],
            terminology_matches=[
                TerminologyResponse(
                    concept_uri=t.concept_uri,
                    pref_label=t.pref_label,
                    definition=t.definition,
                    score=t.score,
                    vocabulary_name=t.vocabulary_name,
                )
                for t in result.terminology_matches
            ],
            confidence=result.confidence,
            query_type=result.query_type_detected,
            no_good_results=result.no_good_results,
            suggested_refinements=result.suggested_refinements,
            query_id=result.query_id,
            latency_ms=result.latency_ms,
        )
    finally:
        conn.close()


@app.get("/document/{doc_id}", response_model=DocumentResponse)
def get_document(doc_id: str):
    """
    Retrieve all chunks for a document by ID.

    Document IDs follow patterns like:
    - ADR-0001
    - PRINCIPLE-0010
    - GOV-PRINCIPLE-0001
    """
    conn = get_db_connection(_config)

    try:
        tool = RetrievalTool(conn, _embedder, _config)
        chunks = tool.get_document_by_id(doc_id)

        if chunks is None:
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

        return DocumentResponse(
            document_id=doc_id,
            document_type=chunks[0].document_type if chunks else None,
            document_title=chunks[0].document_title if chunks else None,
            chunks=[
                ChunkResponse(
                    chunk_id=c.chunk_id,
                    content=c.content,
                    score=c.score,
                    document_id=c.document_id,
                    document_type=c.document_type,
                    document_title=c.document_title,
                    section_header=c.section_header,
                    source_file=c.source_file,
                    owner_team=c.owner_team,
                )
                for c in chunks
            ],
        )
    finally:
        conn.close()


@app.get("/documents", response_model=List[DocumentListItem])
def list_documents(
    doc_type: Optional[str] = Query(None, description="Filter by document type")
):
    """List all available documents."""
    conn = get_db_connection(_config)

    try:
        docs = list_available_documents(conn, doc_type)
        return [
            DocumentListItem(
                document_id=d["document_id"],
                document_type=d["document_type"],
                document_title=d["document_title"],
                owner_team=d["owner_team"],
                chunk_count=d["chunk_count"],
            )
            for d in docs
        ]
    finally:
        conn.close()


@app.get("/stats", response_model=StatsResponse)
def get_stats():
    """Get collection statistics."""
    conn = get_db_connection(_config)

    try:
        stats = get_collection_stats(conn)
        return StatsResponse(
            total_chunks=stats["total_chunks"],
            total_documents=stats["total_documents"],
            total_terminology=stats["total_terminology"],
            chunks_by_type=stats["chunks_by_type"],
            terminology_by_vocabulary=stats["terminology_by_vocabulary"],
        )
    finally:
        conn.close()


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
def root():
    """Root endpoint with API info."""
    return {
        "name": "RAG Search API",
        "version": "1.0.0",
        "endpoints": {
            "/search": "POST - Execute hybrid search",
            "/document/{doc_id}": "GET - Retrieve document by ID",
            "/documents": "GET - List all documents",
            "/stats": "GET - Collection statistics",
            "/health": "GET - Health check",
        },
    }
