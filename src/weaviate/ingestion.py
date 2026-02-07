"""Data ingestion pipeline for loading documents into Weaviate."""

import logging
import re
from pathlib import Path
from typing import Optional, Any
from uuid import uuid4

from weaviate import WeaviateClient
from weaviate.classes.data import DataObject

from ..config import settings
from ..loaders import RDFLoader, MarkdownLoader, DocumentLoader
from .collections import CollectionManager
from .embeddings import embed_texts

# Import chunking module (optional)
try:
    from ..chunking import ChunkedDocument, Chunk
    CHUNKING_AVAILABLE = True
except ImportError:
    CHUNKING_AVAILABLE = False

logger = logging.getLogger(__name__)

# Default batch sizes per provider
# Ollama/Nomic embeddings are local and slower - need smaller batches to avoid timeout
# OpenAI embeddings are fast cloud API - can handle larger batches
DEFAULT_BATCH_SIZE_OLLAMA = 5  # Reduced from 20 to avoid timeouts
DEFAULT_BATCH_SIZE_OPENAI = 50  # Reduced from 100 for more reliable ingestion


def _chunk_to_adr_dict(chunk: "Chunk", adr_number: str = "") -> dict[str, Any]:
    """Convert a Chunk object to ADR-compatible dictionary for existing schema.

    Maps chunk metadata to existing ADR collection properties, enabling
    chunked ingestion without schema changes.

    Args:
        chunk: The Chunk object to convert
        adr_number: ADR number extracted from filename

    Returns:
        Dictionary compatible with existing ADR collection schema
    """
    meta = chunk.metadata

    # Map section_type to appropriate field
    section_content = {
        "context": "",
        "decision": "",
        "consequences": "",
    }
    if meta.section_type in section_content:
        section_content[meta.section_type] = chunk.content

    return {
        "file_path": meta.source_file,
        "title": f"{meta.document_title} - {meta.section_name}" if meta.section_name else meta.document_title,
        "adr_number": adr_number,
        "status": meta.adr_status,
        "context": section_content.get("context", ""),
        "decision": section_content.get("decision", ""),
        "consequences": section_content.get("consequences", ""),
        "content": chunk.content,
        "full_text": chunk.full_text or chunk.build_full_text(),
        "doc_type": meta.document_type or "content",
        # Ownership properties
        "owner_team": meta.owner_team,
        "owner_team_abbr": meta.owner_team_abbr,
        "owner_department": meta.owner_department,
        "owner_organization": meta.owner_organization,
        "owner_display": meta.owner_display,
        "collection_name": meta.collection_name,
    }


def _chunk_to_principle_dict(chunk: "Chunk", principle_number: str = "") -> dict[str, Any]:
    """Convert a Chunk object to Principle-compatible dictionary for existing schema.

    Args:
        chunk: The Chunk object to convert
        principle_number: Principle number extracted from filename (e.g., '0010')

    Returns:
        Dictionary compatible with existing Principle collection schema
    """
    meta = chunk.metadata

    # Extract principle number from filename (e.g., "0010-" or "0018D-")
    principle_match = re.search(r'(\d{4})D?-', meta.source_file)
    principle_number = principle_match.group(1) if principle_match else ""

    return {
        "file_path": meta.source_file,
        "title": f"{meta.document_title} - {meta.section_name}" if meta.section_name else meta.document_title,
        "principle_number": principle_number,
        "doc_type": meta.document_type or "principle",
        "category": "",  # Could be extracted from section_type
        "principle_number": principle_number,
        "statement": chunk.content if meta.section_type == "statement" else "",
        "rationale": chunk.content if meta.section_type == "rationale" else "",
        "implications": chunk.content if meta.section_type == "implications" else "",
        "content": chunk.content,
        "full_text": chunk.full_text or chunk.build_full_text(),
        # Ownership properties
        "owner_team": meta.owner_team,
        "owner_team_abbr": meta.owner_team_abbr,
        "owner_department": meta.owner_department,
        "owner_organization": meta.owner_organization,
        "owner_display": meta.owner_display,
        "collection_name": meta.collection_name,
    }


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
        enable_chunking: bool = False,
    ) -> dict:
        """Run full data ingestion pipeline.

        Args:
            recreate_collections: If True, recreate all collections
            batch_size: Number of objects per batch for local (Ollama/Nomic) collections
            openai_batch_size: Number of objects per batch for OpenAI collections (default: 100)
            include_openai: If True, also populate OpenAI-embedded collections
            enable_chunking: If True, use hierarchical chunking for documents (recommended)

        Returns:
            Dictionary with ingestion statistics
        """
        # Use larger batch size for OpenAI (fast cloud API) vs Ollama (slow local)
        if openai_batch_size is None:
            openai_batch_size = DEFAULT_BATCH_SIZE_OPENAI

        logger.info("Starting full data ingestion pipeline...")
        logger.info(f"Batch sizes: Ollama={batch_size}, OpenAI={openai_batch_size}")
        if enable_chunking:
            if CHUNKING_AVAILABLE:
                logger.info("Chunking ENABLED - documents will be split into sections")
            else:
                logger.warning("Chunking requested but not available - falling back to non-chunked")
                enable_chunking = False
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
            "chunking_enabled": enable_chunking,
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
                batch_size, openai_batch_size, include_openai, enable_chunking
            )
            stats["adr"] = local_count
            stats["adr_openai"] = openai_count
        except Exception as e:
            logger.error(f"Error ingesting ADRs: {e}")
            stats["errors"].append(f"adr: {str(e)}")

        # Ingest principles
        try:
            local_count, openai_count = self._ingest_principles(
                batch_size, openai_batch_size, include_openai, enable_chunking
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
        enable_chunking: bool = False,
    ) -> tuple[int, int]:
        """Ingest Architectural Decision Records.

        Args:
            batch_size_local: Number of objects per batch for local (Ollama) collection
            batch_size_openai: Number of objects per batch for OpenAI collection
            include_openai: If True, also ingest into OpenAI collection
            enable_chunking: If True, use hierarchical section-based chunking

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
        doc_count = 0
        batch_local = []
        batch_openai = []

        # Helper to add a document dict to batches
        def add_to_batches(doc_dict: dict) -> None:
            nonlocal count, batch_local, batch_openai
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

        # Helper to flush batches when full
        def flush_if_needed() -> None:
            nonlocal batch_local, batch_openai
            if len(batch_local) >= batch_size_local:
                self._insert_batch_with_embeddings(
                    collection_local, batch_local, "adr", "full_text"
                )
                batch_local = []
            if include_openai and len(batch_openai) >= batch_size_openai:
                self._insert_batch(collection_openai, batch_openai, "adr_openai")
                batch_openai = []

        if enable_chunking and CHUNKING_AVAILABLE:
            # Use chunked loading - each section becomes a separate object
            logger.info("Using chunked ADR loading")
            for chunked_doc in loader.load_adrs_chunked(adr_path):
                doc_count += 1
                # Extract ADR number from file path
                adr_match = re.search(r'(\d{4})', chunked_doc.source_file)
                adr_number = adr_match.group(1) if adr_match else ""

                # Get section-level chunks (not document or paragraph level)
                # This gives us Context, Decision, Consequences as separate objects
                chunks = chunked_doc.get_chunks_for_indexing(
                    include_document_level=False,
                    include_section_level=True,
                    include_granular=False,  # Don't include paragraphs
                )

                for chunk in chunks:
                    doc_dict = _chunk_to_adr_dict(chunk, adr_number)
                    add_to_batches(doc_dict)
                    flush_if_needed()

            logger.info(f"Processed {doc_count} ADR documents into {count} section chunks")
        else:
            # Use legacy non-chunked loading - one object per document
            for doc_dict in loader.load_adrs(adr_path):
                add_to_batches(doc_dict)
                doc_count += 1
                flush_if_needed()

        # Insert remaining
        if batch_local:
            self._insert_batch_with_embeddings(
                collection_local, batch_local, "adr", "full_text"
            )
        if include_openai and batch_openai:
            self._insert_batch(collection_openai, batch_openai, "adr_openai")

        logger.info(f"Ingested {count} ADR objects from {doc_count} documents")
        return count, count if include_openai else 0

    def _ingest_principles(
        self,
        batch_size_local: int,
        batch_size_openai: int,
        include_openai: bool = False,
        enable_chunking: bool = False,
    ) -> tuple[int, int]:
        """Ingest principle documents.

        Args:
            batch_size_local: Number of objects per batch for local (Ollama) collection
            batch_size_openai: Number of objects per batch for OpenAI collection
            include_openai: If True, also ingest into OpenAI collection
            enable_chunking: If True, use hierarchical section-based chunking

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
        doc_count = 0
        batch_local = []
        batch_openai = []

        # Helper to add a document dict to batches
        def add_to_batches(doc_dict: dict) -> None:
            nonlocal count, batch_local, batch_openai
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

        # Helper to flush batches when full
        def flush_if_needed() -> None:
            nonlocal batch_local, batch_openai
            if len(batch_local) >= batch_size_local:
                self._insert_batch_with_embeddings(
                    collection_local, batch_local, "principle", "full_text"
                )
                batch_local = []
            if include_openai and len(batch_openai) >= batch_size_openai:
                self._insert_batch(collection_openai, batch_openai, "principle_openai")
                batch_openai = []

        for principles_path in paths:
            if not principles_path.exists():
                logger.warning(f"Principles path does not exist: {principles_path}")
                continue

            loader = MarkdownLoader(principles_path)

            if enable_chunking and CHUNKING_AVAILABLE:
                # Use chunked loading - each section becomes a separate object
                logger.info(f"Using chunked principle loading for {principles_path}")
                for chunked_doc in loader.load_principles_chunked(principles_path):
                    doc_count += 1
                    # Extract principle number from file path (e.g., "0010" from "0010-name.md")
                    principle_match = re.search(r'(\d{4})D?-', chunked_doc.source_file)
                    principle_number = principle_match.group(1) if principle_match else ""

                    # Get section-level chunks
                    chunks = chunked_doc.get_chunks_for_indexing(
                        include_document_level=False,
                        include_section_level=True,
                        include_granular=False,
                    )

                    for chunk in chunks:
                        doc_dict = _chunk_to_principle_dict(chunk, principle_number)
                        add_to_batches(doc_dict)
                        flush_if_needed()
            else:
                # Use legacy non-chunked loading
                for doc_dict in loader.load_principles(principles_path):
                    add_to_batches(doc_dict)
                    doc_count += 1
                    flush_if_needed()

        # Insert remaining
        if batch_local:
            self._insert_batch_with_embeddings(
                collection_local, batch_local, "principle", "full_text"
            )
        if include_openai and batch_openai:
            self._insert_batch(collection_openai, batch_openai, "principle_openai")

        logger.info(f"Ingested {count} principle objects from {doc_count} documents")
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
