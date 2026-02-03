"""Abstract vector store interface for database-agnostic chunk storage.

This module provides an abstraction layer that allows the same chunking
code to work with both Weaviate and PostgreSQL+pgvector, enabling
gradual transition between vector stores.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from .models import Chunk, ChunkedDocument

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result from the vector store."""

    chunk: Chunk
    score: float  # Similarity/relevance score (higher is better)
    distance: float  # Vector distance (lower is better)
    highlights: list[str] = None  # Highlighted matching text


@dataclass
class SearchResults:
    """Collection of search results with metadata."""

    results: list[SearchResult]
    total_count: int
    query: str
    search_type: str  # "semantic", "keyword", "hybrid"


class VectorStore(ABC):
    """Abstract base class for vector store implementations.

    Provides a common interface for:
    - Storing chunks with embeddings
    - Semantic search (vector similarity)
    - Keyword search (BM25)
    - Hybrid search (combination)
    - Filtering by metadata

    Implementations:
    - WeaviateVectorStore: Uses Weaviate
    - PostgresVectorStore: Uses PostgreSQL + pgvector
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the vector store (create collections/tables if needed)."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connections and cleanup resources."""
        pass

    # ========== Storage Operations ==========

    @abstractmethod
    async def store_chunk(self, chunk: Chunk) -> str:
        """Store a single chunk.

        Args:
            chunk: The chunk to store

        Returns:
            The stored chunk's ID
        """
        pass

    @abstractmethod
    async def store_chunks(self, chunks: list[Chunk]) -> list[str]:
        """Store multiple chunks in batch.

        Args:
            chunks: List of chunks to store

        Returns:
            List of stored chunk IDs
        """
        pass

    @abstractmethod
    async def store_document(
        self,
        document: ChunkedDocument,
        include_document_level: bool = False,
        include_section_level: bool = True,
        include_granular: bool = True,
    ) -> list[str]:
        """Store all chunks from a chunked document.

        Args:
            document: The chunked document
            include_document_level: Store document-level chunk
            include_section_level: Store section-level chunks
            include_granular: Store paragraph/semantic chunks

        Returns:
            List of stored chunk IDs
        """
        pass

    # ========== Retrieval Operations ==========

    @abstractmethod
    async def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        """Retrieve a chunk by ID.

        Args:
            chunk_id: The chunk's unique identifier

        Returns:
            The chunk, or None if not found
        """
        pass

    @abstractmethod
    async def get_chunks_by_document(self, document_id: str) -> list[Chunk]:
        """Get all chunks belonging to a document.

        Args:
            document_id: The root document ID

        Returns:
            List of chunks from that document
        """
        pass

    # ========== Search Operations ==========

    @abstractmethod
    async def semantic_search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[dict] = None,
    ) -> SearchResults:
        """Perform semantic (vector similarity) search.

        Args:
            query: The search query (will be embedded)
            limit: Maximum results to return
            filters: Metadata filters to apply

        Returns:
            SearchResults with matched chunks
        """
        pass

    @abstractmethod
    async def keyword_search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[dict] = None,
    ) -> SearchResults:
        """Perform keyword (BM25) search.

        Args:
            query: The search query
            limit: Maximum results to return
            filters: Metadata filters to apply

        Returns:
            SearchResults with matched chunks
        """
        pass

    @abstractmethod
    async def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        alpha: float = 0.5,
        filters: Optional[dict] = None,
    ) -> SearchResults:
        """Perform hybrid search combining semantic and keyword.

        Args:
            query: The search query
            limit: Maximum results to return
            alpha: Weight for semantic vs keyword (1.0 = pure semantic, 0.0 = pure keyword)
            filters: Metadata filters to apply

        Returns:
            SearchResults with matched chunks
        """
        pass

    # ========== Delete Operations ==========

    @abstractmethod
    async def delete_chunk(self, chunk_id: str) -> bool:
        """Delete a chunk by ID.

        Args:
            chunk_id: The chunk's unique identifier

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def delete_by_document(self, document_id: str) -> int:
        """Delete all chunks from a document.

        Args:
            document_id: The root document ID

        Returns:
            Number of chunks deleted
        """
        pass

    @abstractmethod
    async def delete_by_source_file(self, source_file: str) -> int:
        """Delete all chunks from a source file.

        Args:
            source_file: Path to the source file

        Returns:
            Number of chunks deleted
        """
        pass

    # ========== Utility Operations ==========

    @abstractmethod
    async def count_chunks(self, filters: Optional[dict] = None) -> int:
        """Count chunks in the store.

        Args:
            filters: Optional metadata filters

        Returns:
            Number of chunks matching filters
        """
        pass

    @abstractmethod
    async def get_document_types(self) -> list[str]:
        """Get all unique document types in the store.

        Returns:
            List of document type strings
        """
        pass


class VectorStoreFactory:
    """Factory for creating vector store instances.

    Supports gradual migration by allowing configuration
    of which backend to use.
    """

    _registry: dict[str, type[VectorStore]] = {}

    @classmethod
    def register(cls, name: str, store_class: type[VectorStore]) -> None:
        """Register a vector store implementation.

        Args:
            name: Name to register under (e.g., "weaviate", "postgres")
            store_class: The VectorStore subclass
        """
        cls._registry[name.lower()] = store_class

    @classmethod
    def create(cls, name: str, **kwargs) -> VectorStore:
        """Create a vector store instance.

        Args:
            name: Name of the registered store
            **kwargs: Arguments to pass to the store constructor

        Returns:
            VectorStore instance

        Raises:
            ValueError: If store name is not registered
        """
        name = name.lower()
        if name not in cls._registry:
            available = ", ".join(cls._registry.keys())
            raise ValueError(
                f"Unknown vector store '{name}'. Available: {available}"
            )

        return cls._registry[name](**kwargs)

    @classmethod
    def available_stores(cls) -> list[str]:
        """Get list of registered store names."""
        return list(cls._registry.keys())


# Placeholder implementations for documentation purposes
# Actual implementations would be in separate files

class WeaviateVectorStore(VectorStore):
    """Weaviate vector store implementation.

    This is a placeholder - the actual implementation would connect
    to Weaviate and use its API for storage and search.
    """

    def __init__(
        self,
        url: str = "http://localhost:8080",
        api_key: Optional[str] = None,
        collection_name: str = "Chunks",
    ):
        self.url = url
        self.api_key = api_key
        self.collection_name = collection_name
        self._client = None

    async def initialize(self) -> None:
        """Initialize Weaviate connection and schema."""
        # TODO: Implement Weaviate initialization
        logger.info(f"Initializing Weaviate connection to {self.url}")

    async def close(self) -> None:
        """Close Weaviate connection."""
        if self._client:
            self._client.close()

    async def store_chunk(self, chunk: Chunk) -> str:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def store_chunks(self, chunks: list[Chunk]) -> list[str]:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def store_document(self, document: ChunkedDocument, **kwargs) -> list[str]:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def get_chunks_by_document(self, document_id: str) -> list[Chunk]:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def semantic_search(self, query: str, **kwargs) -> SearchResults:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def keyword_search(self, query: str, **kwargs) -> SearchResults:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def hybrid_search(self, query: str, **kwargs) -> SearchResults:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def delete_chunk(self, chunk_id: str) -> bool:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def delete_by_document(self, document_id: str) -> int:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def delete_by_source_file(self, source_file: str) -> int:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def count_chunks(self, filters: Optional[dict] = None) -> int:
        raise NotImplementedError("Weaviate store not yet implemented")

    async def get_document_types(self) -> list[str]:
        raise NotImplementedError("Weaviate store not yet implemented")


class PostgresVectorStore(VectorStore):
    """PostgreSQL + pgvector implementation.

    This is a placeholder - the actual implementation would use
    asyncpg and pgvector for storage and similarity search.
    """

    def __init__(
        self,
        connection_string: str,
        table_name: str = "chunks",
    ):
        self.connection_string = connection_string
        self.table_name = table_name
        self._pool = None

    async def initialize(self) -> None:
        """Initialize PostgreSQL connection pool and schema."""
        # TODO: Implement PostgreSQL initialization
        # Would create table with pgvector column type
        logger.info("Initializing PostgreSQL connection")

    async def close(self) -> None:
        """Close PostgreSQL connection pool."""
        if self._pool:
            await self._pool.close()

    async def store_chunk(self, chunk: Chunk) -> str:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def store_chunks(self, chunks: list[Chunk]) -> list[str]:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def store_document(self, document: ChunkedDocument, **kwargs) -> list[str]:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def get_chunks_by_document(self, document_id: str) -> list[Chunk]:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def semantic_search(self, query: str, **kwargs) -> SearchResults:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def keyword_search(self, query: str, **kwargs) -> SearchResults:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def hybrid_search(self, query: str, **kwargs) -> SearchResults:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def delete_chunk(self, chunk_id: str) -> bool:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def delete_by_document(self, document_id: str) -> int:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def delete_by_source_file(self, source_file: str) -> int:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def count_chunks(self, filters: Optional[dict] = None) -> int:
        raise NotImplementedError("PostgreSQL store not yet implemented")

    async def get_document_types(self) -> list[str]:
        raise NotImplementedError("PostgreSQL store not yet implemented")


# Register default stores
VectorStoreFactory.register("weaviate", WeaviateVectorStore)
VectorStoreFactory.register("postgres", PostgresVectorStore)
VectorStoreFactory.register("postgresql", PostgresVectorStore)
