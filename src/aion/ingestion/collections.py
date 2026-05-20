"""Weaviate collection schema definitions and management."""

import logging

from weaviate import WeaviateClient
from weaviate.classes.config import (
    Configure,
    DataType,
    Property,
    Tokenization,
    VectorDistances,
)

from aion.config import settings

logger = logging.getLogger(__name__)


class CollectionManager:
    """Manager for Weaviate collection schemas."""

    # Collection names - Local (Nomic/Ollama)
    VOCABULARY_COLLECTION = "Vocabulary"
    ADR_COLLECTION = "ArchitecturalDecision"
    PRINCIPLE_COLLECTION = "Principle"
    POLICY_COLLECTION = "PolicyDocument"

    # Legacy OpenAI collection names — deleted on init if present
    _LEGACY_OPENAI_COLLECTIONS = [
        "Vocabulary_OpenAI",
        "ArchitecturalDecision_OpenAI",
        "Principle_OpenAI",
        "PolicyDocument_OpenAI",
    ]

    def __init__(self, client: WeaviateClient):
        """Initialize the collection manager.

        Args:
            client: Connected Weaviate client
        """
        self.client = client

    def create_all_collections(self, recreate: bool = False) -> None:
        """Create all required collections.

        All collections use client-side embeddings (Vectorizer.none()).
        The LLM provider used for inference is independent of embeddings.

        Args:
            recreate: If True, delete existing collections before creating
        """
        logger.info("Creating Weaviate collections...")

        if recreate:
            self.delete_all_collections()

        # Vocabulary is now served by SKOSMOS REST API — no Weaviate collection needed
        # self._create_vocabulary_collection()
        self._create_adr_collection()
        self._create_principle_collection()
        self._create_policy_collection()

        # Clean up legacy _OpenAI collections (no longer needed — all
        # providers use client-side embeddings with base collections)
        for legacy in self._LEGACY_OPENAI_COLLECTIONS:
            if self.client.collections.exists(legacy):
                self.client.collections.delete(legacy)
                logger.info(f"Deleted legacy collection: {legacy}")

        logger.info("All collections created successfully")

    def delete_all_collections(self) -> None:
        """Delete all project collections."""
        collections = [
            # self.VOCABULARY_COLLECTION,  # Served by SKOSMOS now
            self.ADR_COLLECTION,
            self.PRINCIPLE_COLLECTION,
            self.POLICY_COLLECTION,
        ]

        for collection_name in collections:
            if self.client.collections.exists(collection_name):
                logger.info(f"Deleting collection: {collection_name}")
                self.client.collections.delete(collection_name)

    def _get_vectorizer_config(self):
        """All collections use client-side embeddings (Vectorizer.none()).

        Embeddings are computed in Python via Ollama's nomic-embed-text model
        and passed to Weaviate during ingestion and search. This decouples
        the embedding provider from the LLM inference provider.
        """
        return Configure.Vectorizer.none()

    def _get_generative_config(self):
        """Get generative model configuration.

        Uses Ollama by default since generative config is only used for
        Weaviate's built-in generative queries (not by the RAG agent).
        """
        return Configure.Generative.ollama(
            api_endpoint=settings.ollama_docker_url,
            model=settings.ollama_model,
        )

    def _get_chunk_properties(self) -> list[Property]:
        """Get chunk-specific properties for chunked ingestion mode."""
        return [
            Property(
                name="chunk_type",
                data_type=DataType.TEXT,
                description="Chunk level: document, section, or semantic_unit",
                tokenization=Tokenization.FIELD,
            ),
            Property(
                name="section_name",
                data_type=DataType.TEXT,
                description="Section name (e.g., Context, Decision, Consequences)",
                tokenization=Tokenization.WORD,
            ),
            Property(
                name="chunk_index",
                data_type=DataType.INT,
                description="Position of this chunk within the parent document",
            ),
            Property(
                name="document_id",
                data_type=DataType.TEXT,
                description="ID linking chunks back to their parent document",
                tokenization=Tokenization.FIELD,
            ),
            Property(
                name="content_hash",
                data_type=DataType.TEXT,
                description="SHA-256 hash prefix for deduplication",
                tokenization=Tokenization.FIELD,
            ),
        ]

    def _get_ownership_properties(self) -> list[Property]:
        """Get common ownership properties for all document collections."""
        return [
            Property(
                name="owner_team",
                data_type=DataType.TEXT,
                description="Team/workgroup that owns this document (e.g., Energy System Architecture)",
                tokenization=Tokenization.WORD,
            ),
            Property(
                name="owner_team_abbr",
                data_type=DataType.TEXT,
                description="Abbreviated team name (e.g., ESA)",
                tokenization=Tokenization.FIELD,
            ),
            Property(
                name="owner_department",
                data_type=DataType.TEXT,
                description="Department that owns this document",
                tokenization=Tokenization.WORD,
            ),
            Property(
                name="owner_organization",
                data_type=DataType.TEXT,
                description="Organization (e.g., Alliander)",
                tokenization=Tokenization.FIELD,
            ),
            Property(
                name="owner_display",
                data_type=DataType.TEXT,
                description="Display name for ownership (Organization / Department / Team)",
                tokenization=Tokenization.WORD,
            ),
            Property(
                name="collection_name",
                data_type=DataType.TEXT,
                description="Name of the document collection from index.md",
                tokenization=Tokenization.WORD,
            ),
        ]

    def _create_vocabulary_collection(self) -> None:
        """Create collection for SKOS/OWL vocabulary concepts."""
        if self.client.collections.exists(self.VOCABULARY_COLLECTION):
            logger.info(f"Collection {self.VOCABULARY_COLLECTION} already exists")
            return

        logger.info(f"Creating collection: {self.VOCABULARY_COLLECTION}")

        self.client.collections.create(
            name=self.VOCABULARY_COLLECTION,
            description="SKOS concepts and OWL classes from energy sector vocabularies",
            vectorizer_config=self._get_vectorizer_config(),
            generative_config=self._get_generative_config(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
            properties=[
                Property(
                    name="uri",
                    data_type=DataType.TEXT,
                    description="Unique URI of the concept",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="pref_label",
                    data_type=DataType.TEXT,
                    description="Preferred label of the concept",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="alt_labels",
                    data_type=DataType.TEXT_ARRAY,
                    description="Alternative labels",
                ),
                Property(
                    name="definition",
                    data_type=DataType.TEXT,
                    description="Definition of the concept",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="broader",
                    data_type=DataType.TEXT_ARRAY,
                    description="URIs of broader concepts",
                ),
                Property(
                    name="narrower",
                    data_type=DataType.TEXT_ARRAY,
                    description="URIs of narrower concepts",
                ),
                Property(
                    name="related",
                    data_type=DataType.TEXT_ARRAY,
                    description="URIs of related concepts",
                ),
                Property(
                    name="in_scheme",
                    data_type=DataType.TEXT,
                    description="URI of the concept scheme",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="notation",
                    data_type=DataType.TEXT,
                    description="Notation/code of the concept",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="source_file",
                    data_type=DataType.TEXT,
                    description="Source file name",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="vocabulary_name",
                    data_type=DataType.TEXT,
                    description="Name of the vocabulary",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="content",
                    data_type=DataType.TEXT,
                    description="Combined searchable content",
                    tokenization=Tokenization.WORD,
                ),
            ],
        )

    def _create_adr_collection(self) -> None:
        """Create collection for Architectural Decision Records."""
        if self.client.collections.exists(self.ADR_COLLECTION):
            logger.info(f"Collection {self.ADR_COLLECTION} already exists")
            return

        logger.info(f"Creating collection: {self.ADR_COLLECTION}")

        self.client.collections.create(
            name=self.ADR_COLLECTION,
            description="Architectural Decision Records for Energy System Architecture",
            vectorizer_config=self._get_vectorizer_config(),
            generative_config=self._get_generative_config(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
            properties=[
                Property(
                    name="file_path",
                    data_type=DataType.TEXT,
                    description="Path to the source file",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="title",
                    data_type=DataType.TEXT,
                    description="Title of the ADR",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="adr_number",
                    data_type=DataType.TEXT,
                    description="ADR number extracted from filename (e.g., '0012')",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="status",
                    data_type=DataType.TEXT,
                    description="Status of the decision (proposed, accepted, deprecated, superseded)",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="context",
                    data_type=DataType.TEXT,
                    description="Context and problem statement",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="decision",
                    data_type=DataType.TEXT,
                    description="The decision outcome",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="consequences",
                    data_type=DataType.TEXT,
                    description="Consequences of the decision",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="content",
                    data_type=DataType.TEXT,
                    description="Full content of the ADR",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="full_text",
                    data_type=DataType.TEXT,
                    description="Combined searchable text",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="doc_type",
                    data_type=DataType.TEXT,
                    description="Document classification: content (actual ADR), index (list/overview), template",
                    tokenization=Tokenization.FIELD,
                ),
                # Dublin Core metadata from frontmatter
                Property(
                    name="dct_identifier",
                    data_type=DataType.TEXT,
                    description="Canonical document UUID from frontmatter (urn:uuid:...)",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="dct_issued",
                    data_type=DataType.TEXT,
                    description="Document issue date from frontmatter (ISO format)",
                    tokenization=Tokenization.FIELD,
                ),
                # Ownership properties from index.md
                *self._get_ownership_properties(),
                # Chunk properties for chunked ingestion mode
                *self._get_chunk_properties(),
            ],
        )

    def _create_principle_collection(self) -> None:
        """Create collection for architecture and governance principles."""
        if self.client.collections.exists(self.PRINCIPLE_COLLECTION):
            logger.info(f"Collection {self.PRINCIPLE_COLLECTION} already exists")
            return

        logger.info(f"Creating collection: {self.PRINCIPLE_COLLECTION}")

        self.client.collections.create(
            name=self.PRINCIPLE_COLLECTION,
            description="Architecture and data governance principles",
            vectorizer_config=self._get_vectorizer_config(),
            generative_config=self._get_generative_config(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
            properties=[
                Property(
                    name="file_path",
                    data_type=DataType.TEXT,
                    description="Path to the source file",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="title",
                    data_type=DataType.TEXT,
                    description="Title of the principle",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="principle_number",
                    data_type=DataType.TEXT,
                    description="Principle number extracted from filename (e.g., '0010')",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="content",
                    data_type=DataType.TEXT,
                    description="Full content of the principle",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="doc_type",
                    data_type=DataType.TEXT,
                    description="Type of document (governance/architecture)",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="full_text",
                    data_type=DataType.TEXT,
                    description="Combined searchable text",
                    tokenization=Tokenization.WORD,
                ),
                # Dublin Core metadata from frontmatter
                Property(
                    name="dct_identifier",
                    data_type=DataType.TEXT,
                    description="Canonical document UUID from frontmatter (urn:uuid:...)",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="dct_issued",
                    data_type=DataType.TEXT,
                    description="Document issue date from frontmatter (ISO format)",
                    tokenization=Tokenization.FIELD,
                ),
                # Ownership properties from index.md
                *self._get_ownership_properties(),
                # Chunk properties for chunked ingestion mode
                *self._get_chunk_properties(),
            ],
        )

    def _create_policy_collection(self) -> None:
        """Create collection for policy documents."""
        if self.client.collections.exists(self.POLICY_COLLECTION):
            logger.info(f"Collection {self.POLICY_COLLECTION} already exists")
            return

        logger.info(f"Creating collection: {self.POLICY_COLLECTION}")

        self.client.collections.create(
            name=self.POLICY_COLLECTION,
            description="Data governance policy documents",
            vectorizer_config=self._get_vectorizer_config(),
            generative_config=self._get_generative_config(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
            properties=[
                Property(
                    name="file_path",
                    data_type=DataType.TEXT,
                    description="Path to the source file",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="title",
                    data_type=DataType.TEXT,
                    description="Title of the policy document",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="content",
                    data_type=DataType.TEXT,
                    description="Full content of the document",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="file_type",
                    data_type=DataType.TEXT,
                    description="File type (docx/pdf)",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="page_count",
                    data_type=DataType.INT,
                    description="Number of pages (for PDF)",
                ),
                Property(
                    name="full_text",
                    data_type=DataType.TEXT,
                    description="Combined searchable text",
                    tokenization=Tokenization.WORD,
                ),
                # Ownership properties from index.md
                *self._get_ownership_properties(),
                # Chunk properties for chunked ingestion mode
                *self._get_chunk_properties(),
            ],
        )

    def get_collection_stats(self) -> dict:
        """Get statistics for all collections.

        Returns:
            Dictionary with collection statistics
        """
        stats = {}
        collections = [
            # self.VOCABULARY_COLLECTION,  # Served by SKOSMOS now
            self.ADR_COLLECTION,
            self.PRINCIPLE_COLLECTION,
            self.POLICY_COLLECTION,
        ]

        for collection_name in collections:
            if self.client.collections.exists(collection_name):
                collection = self.client.collections.get(collection_name)
                aggregate = collection.aggregate.over_all(total_count=True)
                stats[collection_name] = {
                    "exists": True,
                    "count": aggregate.total_count,
                }
            else:
                stats[collection_name] = {"exists": False, "count": 0}

        return stats
