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

logger = logging.getLogger(__name__)


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
        batch_size: int = 100,
    ) -> dict:
        """Run full data ingestion pipeline.

        Args:
            recreate_collections: If True, recreate all collections
            batch_size: Number of objects per batch

        Returns:
            Dictionary with ingestion statistics
        """
        logger.info("Starting full data ingestion pipeline...")

        # Create collections
        self.collection_manager.create_all_collections(recreate=recreate_collections)

        stats = {
            "vocabulary": 0,
            "adr": 0,
            "principle": 0,
            "policy": 0,
            "errors": [],
        }

        # Ingest vocabularies (RDF/TTL)
        try:
            stats["vocabulary"] = self._ingest_vocabularies(batch_size)
        except Exception as e:
            logger.error(f"Error ingesting vocabularies: {e}")
            stats["errors"].append(f"vocabulary: {str(e)}")

        # Ingest ADRs
        try:
            stats["adr"] = self._ingest_adrs(batch_size)
        except Exception as e:
            logger.error(f"Error ingesting ADRs: {e}")
            stats["errors"].append(f"adr: {str(e)}")

        # Ingest principles
        try:
            stats["principle"] = self._ingest_principles(batch_size)
        except Exception as e:
            logger.error(f"Error ingesting principles: {e}")
            stats["errors"].append(f"principle: {str(e)}")

        # Ingest policy documents
        try:
            stats["policy"] = self._ingest_policies(batch_size)
        except Exception as e:
            logger.error(f"Error ingesting policies: {e}")
            stats["errors"].append(f"policy: {str(e)}")

        logger.info(f"Ingestion complete. Stats: {stats}")
        return stats

    def _ingest_vocabularies(self, batch_size: int) -> int:
        """Ingest RDF/SKOS vocabulary data.

        Args:
            batch_size: Number of objects per batch

        Returns:
            Number of objects ingested
        """
        rdf_path = settings.resolve_path(settings.rdf_path)
        if not rdf_path.exists():
            logger.warning(f"RDF path does not exist: {rdf_path}")
            return 0

        loader = RDFLoader(rdf_path)
        collection = self.client.collections.get(
            CollectionManager.VOCABULARY_COLLECTION
        )

        count = 0
        batch = []

        for doc_dict in loader.load_all():
            batch.append(
                DataObject(
                    properties=doc_dict,
                    uuid=str(uuid4()),
                )
            )
            count += 1

            if len(batch) >= batch_size:
                self._insert_batch(collection, batch, "vocabulary")
                batch = []

        # Insert remaining
        if batch:
            self._insert_batch(collection, batch, "vocabulary")

        logger.info(f"Ingested {count} vocabulary concepts")
        return count

    def _ingest_adrs(self, batch_size: int) -> int:
        """Ingest Architectural Decision Records.

        Args:
            batch_size: Number of objects per batch

        Returns:
            Number of objects ingested
        """
        adr_path = settings.resolve_path(settings.markdown_path) / "decisions"
        if not adr_path.exists():
            logger.warning(f"ADR path does not exist: {adr_path}")
            return 0

        loader = MarkdownLoader(adr_path)
        collection = self.client.collections.get(CollectionManager.ADR_COLLECTION)

        count = 0
        batch = []

        for doc_dict in loader.load_adrs(adr_path):
            batch.append(
                DataObject(
                    properties=doc_dict,
                    uuid=str(uuid4()),
                )
            )
            count += 1

            if len(batch) >= batch_size:
                self._insert_batch(collection, batch, "adr")
                batch = []

        # Insert remaining
        if batch:
            self._insert_batch(collection, batch, "adr")

        logger.info(f"Ingested {count} ADRs")
        return count

    def _ingest_principles(self, batch_size: int) -> int:
        """Ingest principle documents.

        Args:
            batch_size: Number of objects per batch

        Returns:
            Number of objects ingested
        """
        # Load both architecture and governance principles
        paths = [
            settings.resolve_path(settings.markdown_path) / "principles",
            settings.resolve_path(settings.principles_path),
        ]

        collection = self.client.collections.get(CollectionManager.PRINCIPLE_COLLECTION)

        count = 0
        batch = []

        for principles_path in paths:
            if not principles_path.exists():
                logger.warning(f"Principles path does not exist: {principles_path}")
                continue

            loader = MarkdownLoader(principles_path)

            for doc_dict in loader.load_principles(principles_path):
                batch.append(
                    DataObject(
                        properties=doc_dict,
                        uuid=str(uuid4()),
                    )
                )
                count += 1

                if len(batch) >= batch_size:
                    self._insert_batch(collection, batch, "principle")
                    batch = []

        # Insert remaining
        if batch:
            self._insert_batch(collection, batch, "principle")

        logger.info(f"Ingested {count} principles")
        return count

    def _ingest_policies(self, batch_size: int) -> int:
        """Ingest policy documents (DOCX/PDF) from multiple paths.

        Args:
            batch_size: Number of objects per batch

        Returns:
            Number of objects ingested
        """
        # Load policies from both domain-specific and general policy paths
        policy_paths = [
            settings.resolve_path(settings.policy_path),
            settings.resolve_path(settings.general_policy_path),
        ]

        collection = self.client.collections.get(CollectionManager.POLICY_COLLECTION)

        count = 0
        batch = []

        for policy_path in policy_paths:
            if not policy_path.exists():
                logger.warning(f"Policy path does not exist: {policy_path}")
                continue

            loader = DocumentLoader(policy_path)

            for doc_dict in loader.load_all():
                batch.append(
                    DataObject(
                        properties=doc_dict,
                        uuid=str(uuid4()),
                    )
                )
                count += 1

                if len(batch) >= batch_size:
                    self._insert_batch(collection, batch, "policy")
                    batch = []

        # Insert remaining
        if batch:
            self._insert_batch(collection, batch, "policy")

        logger.info(f"Ingested {count} policy documents")
        return count

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
