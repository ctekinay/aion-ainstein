"""Hybrid chunking module for document-aware, hierarchical chunking.

This module provides:
- Database-agnostic chunk models that work with both Weaviate and PostgreSQL+pgvector
- Document-type specific chunking strategies (ADR, Principle, Policy)
- Hierarchical chunking with parent-child relationships
- Content-aware chunking that respects document structure
"""

from aion.chunking.models import Chunk, ChunkedDocument, ChunkMetadata, ChunkType
from aion.chunking.strategies import (
    ADRChunkingStrategy,
    ChunkingConfig,
    ChunkingStrategy,
    PolicyChunkingStrategy,
    PrincipleChunkingStrategy,
    VocabularyChunkingStrategy,
    get_chunking_strategy,
)

__all__ = [
    "Chunk",
    "ChunkType",
    "ChunkMetadata",
    "ChunkedDocument",
    "ChunkingStrategy",
    "ChunkingConfig",
    "ADRChunkingStrategy",
    "PrincipleChunkingStrategy",
    "PolicyChunkingStrategy",
    "VocabularyChunkingStrategy",
    "get_chunking_strategy",
]
