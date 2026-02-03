"""Database-agnostic chunk models for hierarchical document chunking.

These models are designed to work with both Weaviate and PostgreSQL+pgvector,
enabling gradual transition between vector stores.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ChunkType(Enum):
    """Hierarchical chunk types for document structure."""

    # Document level - the entire document
    DOCUMENT = "document"

    # Section level - major sections (e.g., ADR Context, Decision, Consequences)
    SECTION = "section"

    # Subsection level - sub-headers within sections
    SUBSECTION = "subsection"

    # Paragraph level - individual paragraphs
    PARAGRAPH = "paragraph"

    # Semantic unit - a semantically coherent chunk (may cross paragraph boundaries)
    SEMANTIC_UNIT = "semantic_unit"


@dataclass
class ChunkMetadata:
    """Rich metadata for a chunk, supporting both Weaviate and PostgreSQL schemas.

    This metadata structure supports:
    - Document provenance (file path, title, ownership)
    - Hierarchical relationships (parent chunk, position in document)
    - Structural information (section name, heading level)
    - Search optimization (keywords, summary)
    - Quality signals (confidence, completeness)
    """

    # Document identity
    source_file: str = ""
    document_title: str = ""
    document_type: str = ""  # adr, principle, policy, vocabulary

    # Ownership (from index.md)
    owner_team: str = ""
    owner_team_abbr: str = ""
    owner_department: str = ""
    owner_organization: str = ""
    owner_display: str = ""
    collection_name: str = ""

    # Structural metadata
    section_name: str = ""  # e.g., "Context", "Decision", "Consequences"
    section_type: str = ""  # e.g., "context", "decision", "consequences"
    heading_level: int = 0  # 1 = h1, 2 = h2, etc.
    position_in_document: int = 0  # Order within the document
    position_in_section: int = 0  # Order within the section

    # Hierarchical relationships
    parent_chunk_id: Optional[str] = None
    root_document_id: Optional[str] = None

    # Content characteristics
    char_count: int = 0
    word_count: int = 0
    has_code_block: bool = False
    has_table: bool = False
    has_list: bool = False
    language: str = "en"  # Detected language

    # ADR-specific
    adr_status: str = ""  # accepted, deprecated, superseded, etc.

    # Quality signals
    completeness: float = 1.0  # 0-1, how complete this chunk is
    confidence: float = 1.0  # 0-1, confidence in chunk boundaries

    # Timestamps
    created_at: str = ""
    modified_at: str = ""

    # Extension fields (for future use)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "source_file": self.source_file,
            "document_title": self.document_title,
            "document_type": self.document_type,
            "owner_team": self.owner_team,
            "owner_team_abbr": self.owner_team_abbr,
            "owner_department": self.owner_department,
            "owner_organization": self.owner_organization,
            "owner_display": self.owner_display,
            "collection_name": self.collection_name,
            "section_name": self.section_name,
            "section_type": self.section_type,
            "heading_level": self.heading_level,
            "position_in_document": self.position_in_document,
            "position_in_section": self.position_in_section,
            "parent_chunk_id": self.parent_chunk_id,
            "root_document_id": self.root_document_id,
            "char_count": self.char_count,
            "word_count": self.word_count,
            "has_code_block": self.has_code_block,
            "has_table": self.has_table,
            "has_list": self.has_list,
            "language": self.language,
            "adr_status": self.adr_status,
            "completeness": self.completeness,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            **self.extra,
        }


@dataclass
class Chunk:
    """A single chunk of content with full metadata.

    Designed to be database-agnostic:
    - `id`: Unique identifier (UUID for both Weaviate and PostgreSQL)
    - `content`: The actual text content
    - `full_text`: Enriched text for embedding (includes context)
    - `chunk_type`: Hierarchical level of this chunk
    - `metadata`: Rich metadata for filtering and context

    The chunk can be serialized to both Weaviate and PostgreSQL formats.
    """

    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content_hash: str = ""  # SHA-256 of content for deduplication

    # Content
    content: str = ""  # Raw content
    full_text: str = ""  # Enriched text for embedding
    summary: str = ""  # Optional summary for large chunks

    # Classification
    chunk_type: ChunkType = ChunkType.SEMANTIC_UNIT

    # Metadata
    metadata: ChunkMetadata = field(default_factory=ChunkMetadata)

    # Embedding (optional, populated after embedding generation)
    embedding: Optional[list[float]] = None

    def __post_init__(self):
        """Generate content hash if not provided."""
        if not self.content_hash and self.content:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]

        # Update metadata counts
        if self.content:
            self.metadata.char_count = len(self.content)
            self.metadata.word_count = len(self.content.split())

    def build_full_text(self, include_context: bool = True) -> str:
        """Build enriched text for embedding.

        Includes document context to improve semantic search quality.
        """
        parts = []

        if include_context:
            if self.metadata.document_title:
                parts.append(f"Document: {self.metadata.document_title}")
            if self.metadata.document_type:
                parts.append(f"Type: {self.metadata.document_type}")
            if self.metadata.section_name:
                parts.append(f"Section: {self.metadata.section_name}")
            if self.metadata.owner_display:
                parts.append(f"Owner: {self.metadata.owner_display}")
            if self.metadata.adr_status:
                parts.append(f"Status: {self.metadata.adr_status}")

        parts.append("")  # Empty line before content
        parts.append(self.content)

        return "\n".join(parts)

    def to_weaviate_dict(self) -> dict[str, Any]:
        """Convert to Weaviate-compatible dictionary.

        Maps chunk fields to Weaviate collection properties.
        """
        base = {
            "chunk_id": self.id,
            "content_hash": self.content_hash,
            "content": self.content,
            "full_text": self.full_text or self.build_full_text(),
            "summary": self.summary,
            "chunk_type": self.chunk_type.value,
        }
        base.update(self.metadata.to_dict())
        return base

    def to_postgres_dict(self) -> dict[str, Any]:
        """Convert to PostgreSQL-compatible dictionary.

        Maps chunk fields to PostgreSQL table columns.
        This format is compatible with pgvector.
        """
        return {
            "id": self.id,
            "content_hash": self.content_hash,
            "content": self.content,
            "full_text": self.full_text or self.build_full_text(),
            "summary": self.summary,
            "chunk_type": self.chunk_type.value,
            "embedding": self.embedding,  # pgvector array
            "metadata": self.metadata.to_dict(),  # JSONB column
            "source_file": self.metadata.source_file,
            "document_type": self.metadata.document_type,
            "section_type": self.metadata.section_type,
            "parent_chunk_id": self.metadata.parent_chunk_id,
            "created_at": self.metadata.created_at or datetime.utcnow().isoformat(),
        }

    def to_dict(self, format: str = "weaviate") -> dict[str, Any]:
        """Convert to dictionary for the specified storage format."""
        if format == "postgres":
            return self.to_postgres_dict()
        return self.to_weaviate_dict()


@dataclass
class ChunkedDocument:
    """A document broken into hierarchical chunks.

    Maintains the full document structure with parent-child relationships.
    """

    # Document identity
    document_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_file: str = ""
    document_title: str = ""
    document_type: str = ""

    # All chunks from this document
    chunks: list[Chunk] = field(default_factory=list)

    # Document-level chunk (the full document as a single chunk)
    document_chunk: Optional[Chunk] = None

    # Section-level chunks
    section_chunks: list[Chunk] = field(default_factory=list)

    # Granular chunks (paragraphs, semantic units)
    granular_chunks: list[Chunk] = field(default_factory=list)

    # Metadata
    total_chars: int = 0
    total_chunks: int = 0
    chunking_strategy: str = ""

    def add_chunk(self, chunk: Chunk) -> None:
        """Add a chunk and update relationships."""
        chunk.metadata.root_document_id = self.document_id
        self.chunks.append(chunk)

        if chunk.chunk_type == ChunkType.DOCUMENT:
            self.document_chunk = chunk
        elif chunk.chunk_type in (ChunkType.SECTION, ChunkType.SUBSECTION):
            self.section_chunks.append(chunk)
        else:
            self.granular_chunks.append(chunk)

        self.total_chunks = len(self.chunks)
        self.total_chars += chunk.metadata.char_count

    def get_chunks_for_indexing(self,
                                 include_document_level: bool = False,
                                 include_section_level: bool = True,
                                 include_granular: bool = True) -> list[Chunk]:
        """Get chunks to index based on desired granularity.

        Args:
            include_document_level: Include full document as a chunk
            include_section_level: Include section-level chunks
            include_granular: Include paragraph/semantic unit chunks

        Returns:
            List of chunks to index
        """
        result = []

        if include_document_level and self.document_chunk:
            result.append(self.document_chunk)

        if include_section_level:
            result.extend(self.section_chunks)

        if include_granular:
            result.extend(self.granular_chunks)

        return result
