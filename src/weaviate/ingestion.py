"""Data ingestion pipeline for loading documents into Weaviate."""

import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

from weaviate import WeaviateClient
from weaviate.classes.data import DataObject

from ..config import settings
from ..loaders import RDFLoader, MarkdownLoader, DocumentLoader
from .collections import CollectionManager
from .embeddings import embed_texts

logger = logging.getLogger(__name__)

# Default batch sizes per provider
# Ollama/Nomic embeddings are local and slower - need smaller batches to avoid timeout
# OpenAI embeddings are fast cloud API - can handle larger batches
DEFAULT_BATCH_SIZE_OLLAMA = 20
DEFAULT_BATCH_SIZE_OPENAI = 100


class DataIngestionPipeline:
    """Pipeline for ingesting all data types into Weaviate."""

    def __init__(self, client: WeaviateClient):
        """Initialize the ingestion pipeline.

        Args:
            client: Connected Weaviate client
        """
        self.client = client
        self.collection_manager = CollectionManager(client)

    def run_full_ingestion(
        self,
        recreate_collections: bool = False,
        batch_size: int = DEFAULT_BATCH_SIZE_OLLAMA,
        openai_batch_size: Optional[int] = None,
        include_openai: bool = False,
    ) -> dict:
        """Run full data ingestion pipeline.

        Args:
            recreate_collections: If True, recreate all collections
            batch_size: Number of objects per batch for local (Ollama/Nomic) collections
            openai_batch_size: Number of objects per batch for OpenAI collections (default: 100)
            include_openai: If True, also populate OpenAI-embedded collections

        Returns:
            Dictionary with ingestion statistics
        """
        # Use larger batch size for OpenAI (fast cloud API) vs Ollama (slow local)
        if openai_batch_size is None:
            openai_batch_size = DEFAULT_BATCH_SIZE_OPENAI

        logger.info("Starting full data ingestion pipeline...")
        logger.info(f"Batch sizes: Ollama={batch_size}, OpenAI={openai_batch_size}")
        if include_openai:
            logger.info("OpenAI collections will also be populated")

        # Create collections
        self.collection_manager.create_all_collections(
            recreate=recreate_collections,
            include_openai=include_openai
        )

        stats = {
            "vocabulary": 0,
            "adr": 0,
            "principle": 0,
            "policy": 0,
            "vocabulary_openai": 0,
            "adr_openai": 0,
            "principle_openai": 0,
            "policy_openai": 0,
            "errors": [],
        }

        # Ingest vocabularies (RDF/TTL)
        try:
            local_count, openai_count = self._ingest_vocabularies(
                batch_size, openai_batch_size, include_openai
            )
            stats["vocabulary"] = local_count
            stats["vocabulary_openai"] = openai_count
        except Exception as e:
            logger.error(f"Error ingesting vocabularies: {e}")
            stats["errors"].append(f"vocabulary: {str(e)}")

        # Ingest ADRs
        try:
            local_count, openai_count = self._ingest_adrs(
                batch_size, openai_batch_size, include_openai
            )
            stats["adr"] = local_count
            stats["adr_openai"] = openai_count
        except Exception as e:
            logger.error(f"Error ingesting ADRs: {e}")
            stats["errors"].append(f"adr: {str(e)}")

        # Ingest principles
        try:
            local_count, openai_count = self._ingest_principles(
                batch_size, openai_batch_size, include_openai
            )
            stats["principle"] = local_count
            stats["principle_openai"] = openai_count
        except Exception as e:
            logger.error(f"Error ingesting principles: {e}")
            stats["errors"].append(f"principle: {str(e)}")

        # Ingest policy documents
        try:
            local_count, openai_count = self._ingest_policies(
                batch_size, openai_batch_size, include_openai
            )
            stats["policy"] = local_count
            stats["policy_openai"] = openai_count
        except Exception as e:
            logger.error(f"Error ingesting policies: {e}")
            stats["errors"].append(f"policy: {str(e)}")

        logger.info(f"Ingestion complete. Stats: {stats}")
        return stats

    def _ingest_vocabularies(
        self,
        batch_size_local: int,
        batch_size_openai: int,
        include_openai: bool = False,
    ) -> tuple[int, int]:
        """Ingest RDF/SKOS vocabulary data.

        Args:
            batch_size_local: Number of objects per batch for local (Ollama) collection
            batch_size_openai: Number of objects per batch for OpenAI collection
            include_openai: If True, also ingest into OpenAI collection

        Returns:
            Tuple of (local_count, openai_count)
        """
        rdf_path = settings.resolve_path(settings.rdf_path)
        if not rdf_path.exists():
            logger.warning(f"RDF path does not exist: {rdf_path}")
            return 0, 0

        loader = RDFLoader(rdf_path)
        collection_local = self.client.collections.get(
            CollectionManager.VOCABULARY_COLLECTION
        )
        collection_openai = None
        if include_openai:
            collection_openai = self.client.collections.get(
                CollectionManager.VOCABULARY_COLLECTION_OPENAI
            )

        count = 0
        batch_local = []
        batch_openai = []

        for doc_dict in loader.load_all():
            batch_local.append(
                DataObject(
                    properties=doc_dict,
                    uuid=str(uuid4()),
                )
            )
            if include_openai:
                batch_openai.append(
                    DataObject(
                        properties=doc_dict,
                        uuid=str(uuid4()),
                    )
                )
            count += 1

            # Flush local batch when it reaches the local batch size
            # Use client-side embeddings for local (Ollama) collection
            if len(batch_local) >= batch_size_local:
                self._insert_batch_with_embeddings(
                    collection_local, batch_local, "vocabulary", "content"
                )
                batch_local = []

            # Flush OpenAI batch independently when it reaches the OpenAI batch size
            # OpenAI collections use Weaviate's text2vec-openai module (works correctly)
            if include_openai and len(batch_openai) >= batch_size_openai:
                self._insert_batch(collection_openai, batch_openai, "vocabulary_openai")
                batch_openai = []

        # Insert remaining
        if batch_local:
            self._insert_batch_with_embeddings(
                collection_local, batch_local, "vocabulary", "content"
            )
        if include_openai and batch_openai:
            self._insert_batch(collection_openai, batch_openai, "vocabulary_openai")

        logger.info(f"Ingested {count} vocabulary concepts")
        return count, count if include_openai else 0

    def _ingest_adrs(
        self,
        batch_size_local: int,
        batch_size_openai: int,
        include_openai: bool = False,
    ) -> tuple[int, int]:
        """Ingest Architectural Decision Records.

        Args:
            batch_size_local: Number of objects per batch for local (Ollama) collection
            batch_size_openai: Number of objects per batch for OpenAI collection
            include_openai: If True, also ingest into OpenAI collection

        Returns:
            Tuple of (local_count, openai_count)
        """
        adr_path = settings.resolve_path(settings.markdown_path) / "decisions"
        if not adr_path.exists():
            logger.warning(f"ADR path does not exist: {adr_path}")
            return 0, 0

        loader = MarkdownLoader(adr_path)
        collection_local = self.client.collections.get(CollectionManager.ADR_COLLECTION)
        collection_openai = None
        if include_openai:
            collection_openai = self.client.collections.get(
                CollectionManager.ADR_COLLECTION_OPENAI
            )

        count = 0
        batch_local = []
        batch_openai = []

        for doc_dict in loader.load_adrs(adr_path):
            batch_local.append(
                DataObject(
                    properties=doc_dict,
                    uuid=str(uuid4()),
                )
            )
            if include_openai:
                batch_openai.append(
                    DataObject(
                        properties=doc_dict,
                        uuid=str(uuid4()),
                    )
                )
            count += 1

            # Flush local batch when it reaches the local batch size
            # Use client-side embeddings for local (Ollama) collection
            if len(batch_local) >= batch_size_local:
                self._insert_batch_with_embeddings(
                    collection_local, batch_local, "adr", "full_text"
                )
                batch_local = []

            # Flush OpenAI batch independently when it reaches the OpenAI batch size
            # OpenAI collections use Weaviate's text2vec-openai module (works correctly)
            if include_openai and len(batch_openai) >= batch_size_openai:
                self._insert_batch(collection_openai, batch_openai, "adr_openai")
                batch_openai = []

        # Insert remaining
        if batch_local:
            self._insert_batch_with_embeddings(
                collection_local, batch_local, "adr", "full_text"
            )
        if include_openai and batch_openai:
            self._insert_batch(collection_openai, batch_openai, "adr_openai")

        logger.info(f"Ingested {count} ADRs")
        return count, count if include_openai else 0

    def _ingest_principles(
        self,
        batch_size_local: int,
        batch_size_openai: int,
        include_openai: bool = False,
    ) -> tuple[int, int]:
        """Ingest principle documents.

        Args:
            batch_size_local: Number of objects per batch for local (Ollama) collection
            batch_size_openai: Number of objects per batch for OpenAI collection
            include_openai: If True, also ingest into OpenAI collection

        Returns:
            Tuple of (local_count, openai_count)
        """
        # Load both architecture and governance principles
        paths = [
            settings.resolve_path(settings.markdown_path) / "principles",
            settings.resolve_path(settings.principles_path),
        ]

        collection_local = self.client.collections.get(CollectionManager.PRINCIPLE_COLLECTION)
        collection_openai = None
        if include_openai:
            collection_openai = self.client.collections.get(
                CollectionManager.PRINCIPLE_COLLECTION_OPENAI
            )

        count = 0
        batch_local = []
        batch_openai = []

        for principles_path in paths:
            if not principles_path.exists():
                logger.warning(f"Principles path does not exist: {principles_path}")
                continue

            loader = MarkdownLoader(principles_path)

            for doc_dict in loader.load_principles(principles_path):
                batch_local.append(
                    DataObject(
                        properties=doc_dict,
                        uuid=str(uuid4()),
                    )
                )
                if include_openai:
                    batch_openai.append(
                        DataObject(
                            properties=doc_dict,
                            uuid=str(uuid4()),
                        )
                    )
                count += 1

                # Flush local batch when it reaches the local batch size
                # Use client-side embeddings for local (Ollama) collection
                if len(batch_local) >= batch_size_local:
                    self._insert_batch_with_embeddings(
                        collection_local, batch_local, "principle", "full_text"
                    )
                    batch_local = []

                # Flush OpenAI batch independently when it reaches the OpenAI batch size
                # OpenAI collections use Weaviate's text2vec-openai module (works correctly)
                if include_openai and len(batch_openai) >= batch_size_openai:
                    self._insert_batch(collection_openai, batch_openai, "principle_openai")
                    batch_openai = []

        # Insert remaining
        if batch_local:
            self._insert_batch_with_embeddings(
                collection_local, batch_local, "principle", "full_text"
            )
        if include_openai and batch_openai:
            self._insert_batch(collection_openai, batch_openai, "principle_openai")

        logger.info(f"Ingested {count} principles")
        return count, count if include_openai else 0

    def _ingest_policies(
        self,
        batch_size_local: int,
        batch_size_openai: int,
        include_openai: bool = False,
    ) -> tuple[int, int]:
        """Ingest policy documents (DOCX/PDF) from multiple paths.

        Args:
            batch_size_local: Number of objects per batch for local (Ollama) collection
            batch_size_openai: Number of objects per batch for OpenAI collection
            include_openai: If True, also ingest into OpenAI collection

        Returns:
            Tuple of (local_count, openai_count)
        """
        # Load policies from both domain-specific and general policy paths
        policy_paths = [
            settings.resolve_path(settings.policy_path),
            settings.resolve_path(settings.general_policy_path),
        ]

        collection_local = self.client.collections.get(CollectionManager.POLICY_COLLECTION)
        collection_openai = None
        if include_openai:
            collection_openai = self.client.collections.get(
                CollectionManager.POLICY_COLLECTION_OPENAI
            )

        count = 0
        batch_local = []
        batch_openai = []

        for policy_path in policy_paths:
            if not policy_path.exists():
                logger.warning(f"Policy path does not exist: {policy_path}")
                continue

            loader = DocumentLoader(policy_path)

            for doc_dict in loader.load_all():
                batch_local.append(
                    DataObject(
                        properties=doc_dict,
                        uuid=str(uuid4()),
                    )
                )
                if include_openai:
                    batch_openai.append(
                        DataObject(
                            properties=doc_dict,
                            uuid=str(uuid4()),
                        )
                    )
                count += 1

                # Flush local batch when it reaches the local batch size
                # Use client-side embeddings for local (Ollama) collection
                if len(batch_local) >= batch_size_local:
                    self._insert_batch_with_embeddings(
                        collection_local, batch_local, "policy", "full_text"
                    )
                    batch_local = []

                # Flush OpenAI batch independently when it reaches the OpenAI batch size
                # OpenAI collections use Weaviate's text2vec-openai module (works correctly)
                if include_openai and len(batch_openai) >= batch_size_openai:
                    self._insert_batch(collection_openai, batch_openai, "policy_openai")
                    batch_openai = []

        # Insert remaining
        if batch_local:
            self._insert_batch_with_embeddings(
                collection_local, batch_local, "policy", "full_text"
            )
        if include_openai and batch_openai:
            self._insert_batch(collection_openai, batch_openai, "policy_openai")

        logger.info(f"Ingested {count} policy documents")
        return count, count if include_openai else 0

    def _insert_batch(self, collection, batch: list, doc_type: str) -> None:
        """Insert a batch of objects into a collection.

        Args:
            collection: Weaviate collection
            batch: List of DataObject instances
            doc_type: Type of documents for logging
        """
        try:
            result = collection.data.insert_many(batch)
            if result.has_errors:
                for error in result.errors.values():
                    logger.error(f"Batch insert error ({doc_type}): {error}")
            else:
                logger.debug(f"Inserted batch of {len(batch)} {doc_type} objects")
        except Exception as e:
            logger.error(f"Failed to insert batch ({doc_type}): {e}")
            raise

    def _insert_batch_with_embeddings(
        self,
        collection,
        batch: list,
        doc_type: str,
        text_field: str = "content",
    ) -> None:
        """Insert a batch with client-side generated embeddings.

        WORKAROUND for Weaviate text2vec-ollama bug (#8406).
        Generates embeddings using Ollama API and inserts with vectors.

        Args:
            collection: Weaviate collection
            batch: List of DataObject instances
            doc_type: Type of documents for logging
            text_field: Property name containing text to embed
        """
        try:
            # Extract texts for embedding
            texts = []
            for obj in batch:
                text = obj.properties.get(text_field, "")
                if not text:
                    # Fallback: try full_text for documents
                    text = obj.properties.get("full_text", "")
                texts.append(text or "")

            # Generate embeddings
            embeddings = embed_texts(texts)

            # Create objects with vectors
            objects_with_vectors = []
            for obj, vector in zip(batch, embeddings):
                objects_with_vectors.append(
                    DataObject(
                        properties=obj.properties,
                        uuid=obj.uuid,
                        vector=vector,
                    )
                )

            # Insert with vectors
            result = collection.data.insert_many(objects_with_vectors)
            if result.has_errors:
                for error in result.errors.values():
                    logger.error(f"Batch insert error ({doc_type}): {error}")
            else:
                logger.debug(f"Inserted batch of {len(batch)} {doc_type} objects with embeddings")
        except Exception as e:
            logger.error(f"Failed to insert batch with embeddings ({doc_type}): {e}")
            raise
