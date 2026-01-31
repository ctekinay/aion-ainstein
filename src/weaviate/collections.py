"""Weaviate collection schema definitions and management."""

import logging
from typing import Optional

from weaviate import WeaviateClient
from weaviate.classes.config import Configure, Property, DataType, Tokenization, VectorDistances

from .embeddings import EMBEDDING_DIMENSION

from ..config import settings

logger = logging.getLogger(__name__)


class CollectionManager:
    """Manager for Weaviate collection schemas."""

    # Collection names - Local (Nomic/Ollama)
    VOCABULARY_COLLECTION = "Vocabulary"
    ADR_COLLECTION = "ArchitecturalDecision"
    PRINCIPLE_COLLECTION = "Principle"
    POLICY_COLLECTION = "PolicyDocument"

    # Collection names - OpenAI
    VOCABULARY_COLLECTION_OPENAI = "Vocabulary_OpenAI"
    ADR_COLLECTION_OPENAI = "ArchitecturalDecision_OpenAI"
    PRINCIPLE_COLLECTION_OPENAI = "Principle_OpenAI"
    POLICY_COLLECTION_OPENAI = "PolicyDocument_OpenAI"

    def __init__(self, client: WeaviateClient):
        """Initialize the collection manager.

        Args:
            client: Connected Weaviate client
        """
        self.client = client

    def create_all_collections(self, recreate: bool = False, include_openai: bool = False) -> None:
        """Create all required collections.

        Args:
            recreate: If True, delete existing collections before creating
            include_openai: If True, also create OpenAI-embedded collections for comparison
        """
        logger.info("Creating Weaviate collections...")

        if recreate:
            self.delete_all_collections(include_openai=include_openai)

        # Create local (Nomic/Ollama) collections
        self._create_vocabulary_collection()
        self._create_adr_collection()
        self._create_principle_collection()
        self._create_policy_collection()

        # Create OpenAI collections if requested
        if include_openai:
            logger.info("Creating OpenAI-embedded collections for comparison...")
            self._create_vocabulary_collection_openai()
            self._create_adr_collection_openai()
            self._create_principle_collection_openai()
            self._create_policy_collection_openai()

        logger.info("All collections created successfully")

    def delete_all_collections(self, include_openai: bool = False) -> None:
        """Delete all project collections.

        Args:
            include_openai: If True, also delete OpenAI collections
        """
        collections = [
            self.VOCABULARY_COLLECTION,
            self.ADR_COLLECTION,
            self.PRINCIPLE_COLLECTION,
            self.POLICY_COLLECTION,
        ]

        if include_openai:
            collections.extend([
                self.VOCABULARY_COLLECTION_OPENAI,
                self.ADR_COLLECTION_OPENAI,
                self.PRINCIPLE_COLLECTION_OPENAI,
                self.POLICY_COLLECTION_OPENAI,
            ])

        for collection_name in collections:
            if self.client.collections.exists(collection_name):
                logger.info(f"Deleting collection: {collection_name}")
                self.client.collections.delete(collection_name)

    def _get_vectorizer_config(self):
        """Get vectorizer configuration based on LLM provider."""
        if settings.llm_provider == "ollama":
            return self._get_ollama_vectorizer_config()
        else:
            return self._get_openai_vectorizer_config()

    def _get_ollama_vectorizer_config(self):
        """Get vectorizer configuration for Ollama collections.

        WORKAROUND for Weaviate text2vec-ollama bug (#8406):
        The module ignores apiEndpoint and always connects to localhost:11434,
        which fails in Docker environments.

        Instead, we use Vectorizer.none() and handle embeddings client-side:
        - During ingestion: compute embeddings via Ollama API and insert with vectors
        - During search: compute query embedding and use near_vector search
        """
        return Configure.Vectorizer.none()

    def _get_openai_vectorizer_config(self):
        """Get OpenAI vectorizer configuration."""
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required. Please set it in your .env file."
            )
        return Configure.Vectorizer.text2vec_openai(
            model=settings.openai_embedding_model,
        )

    def _get_generative_config(self):
        """Get generative model configuration based on LLM provider."""
        if settings.llm_provider == "ollama":
            return self._get_ollama_generative_config()
        else:
            return self._get_openai_generative_config()

    def _get_ollama_generative_config(self):
        """Get Ollama generative configuration."""
        return Configure.Generative.ollama(
            api_endpoint=settings.ollama_docker_url,
            model=settings.ollama_model,
        )

    def _get_openai_generative_config(self):
        """Get OpenAI generative configuration."""
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required. Please set it in your .env file."
            )
        return Configure.Generative.openai(
            model=settings.openai_chat_model,
        )

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
                # Ownership properties from index.md
                *self._get_ownership_properties(),
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
                # Ownership properties from index.md
                *self._get_ownership_properties(),
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
            ],
        )

    # ============== OpenAI Collection Creation Methods ==============

    def _create_vocabulary_collection_openai(self) -> None:
        """Create OpenAI-embedded collection for SKOS/OWL vocabulary concepts."""
        if self.client.collections.exists(self.VOCABULARY_COLLECTION_OPENAI):
            logger.info(f"Collection {self.VOCABULARY_COLLECTION_OPENAI} already exists")
            return

        logger.info(f"Creating collection: {self.VOCABULARY_COLLECTION_OPENAI}")

        self.client.collections.create(
            name=self.VOCABULARY_COLLECTION_OPENAI,
            description="SKOS concepts and OWL classes (OpenAI embeddings)",
            vectorizer_config=self._get_openai_vectorizer_config(),
            generative_config=self._get_openai_generative_config(),
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

    def _create_adr_collection_openai(self) -> None:
        """Create OpenAI-embedded collection for Architectural Decision Records."""
        if self.client.collections.exists(self.ADR_COLLECTION_OPENAI):
            logger.info(f"Collection {self.ADR_COLLECTION_OPENAI} already exists")
            return

        logger.info(f"Creating collection: {self.ADR_COLLECTION_OPENAI}")

        self.client.collections.create(
            name=self.ADR_COLLECTION_OPENAI,
            description="Architectural Decision Records (OpenAI embeddings)",
            vectorizer_config=self._get_openai_vectorizer_config(),
            generative_config=self._get_openai_generative_config(),
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
                    name="status",
                    data_type=DataType.TEXT,
                    description="Status of the decision",
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
                *self._get_ownership_properties(),
            ],
        )

    def _create_principle_collection_openai(self) -> None:
        """Create OpenAI-embedded collection for principles."""
        if self.client.collections.exists(self.PRINCIPLE_COLLECTION_OPENAI):
            logger.info(f"Collection {self.PRINCIPLE_COLLECTION_OPENAI} already exists")
            return

        logger.info(f"Creating collection: {self.PRINCIPLE_COLLECTION_OPENAI}")

        self.client.collections.create(
            name=self.PRINCIPLE_COLLECTION_OPENAI,
            description="Architecture and governance principles (OpenAI embeddings)",
            vectorizer_config=self._get_openai_vectorizer_config(),
            generative_config=self._get_openai_generative_config(),
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
                    name="content",
                    data_type=DataType.TEXT,
                    description="Full content of the principle",
                    tokenization=Tokenization.WORD,
                ),
                Property(
                    name="doc_type",
                    data_type=DataType.TEXT,
                    description="Type of document",
                    tokenization=Tokenization.FIELD,
                ),
                Property(
                    name="full_text",
                    data_type=DataType.TEXT,
                    description="Combined searchable text",
                    tokenization=Tokenization.WORD,
                ),
                *self._get_ownership_properties(),
            ],
        )

    def _create_policy_collection_openai(self) -> None:
        """Create OpenAI-embedded collection for policy documents."""
        if self.client.collections.exists(self.POLICY_COLLECTION_OPENAI):
            logger.info(f"Collection {self.POLICY_COLLECTION_OPENAI} already exists")
            return

        logger.info(f"Creating collection: {self.POLICY_COLLECTION_OPENAI}")

        self.client.collections.create(
            name=self.POLICY_COLLECTION_OPENAI,
            description="Data governance policy documents (OpenAI embeddings)",
            vectorizer_config=self._get_openai_vectorizer_config(),
            generative_config=self._get_openai_generative_config(),
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
                *self._get_ownership_properties(),
            ],
        )

    def get_collection_stats(self, include_openai: bool = True) -> dict:
        """Get statistics for all collections.

        Args:
            include_openai: If True, include OpenAI collections in stats

        Returns:
            Dictionary with collection statistics
        """
        stats = {}
        collections = [
            self.VOCABULARY_COLLECTION,
            self.ADR_COLLECTION,
            self.PRINCIPLE_COLLECTION,
            self.POLICY_COLLECTION,
        ]

        if include_openai:
            collections.extend([
                self.VOCABULARY_COLLECTION_OPENAI,
                self.ADR_COLLECTION_OPENAI,
                self.PRINCIPLE_COLLECTION_OPENAI,
                self.POLICY_COLLECTION_OPENAI,
            ])

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
