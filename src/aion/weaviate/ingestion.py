"""Data ingestion pipeline for loading documents into Weaviate."""

import logging
import re
from pathlib import Path
from uuid import uuid4

from weaviate import WeaviateClient
from weaviate.classes.data import DataObject

from src.aion.chunking.strategies import ChunkingConfig
from src.aion.config import settings
from src.aion.loaders import DocumentLoader, MarkdownLoader
from src.aion.loaders.registry_parser import get_registry_lookup
from src.aion.weaviate.collections import CollectionManager
from src.aion.weaviate.embeddings import embed_texts

logger = logging.getLogger(__name__)

# Default batch size for client-side embeddings (Ollama/Nomic)
DEFAULT_BATCH_SIZE = 5  # Small batches to avoid local embedding timeouts


class DataIngestionPipeline:
    """Pipeline for ingesting all data types into Weaviate."""

    def __init__(self, client: WeaviateClient):
        """Initialize the ingestion pipeline.

        Args:
            client: Connected Weaviate client
        """
        self.client = client
        self.collection_manager = CollectionManager(client)
        self._registry = get_registry_lookup()

    def _enrich_from_registry(self, doc_dict: dict, doc_type: str) -> dict:
        """Enrich a document dict with metadata from esa_doc_registry.md.

        Only fills fields that are empty/missing. Frontmatter values are
        authoritative and are never overwritten.

        Args:
            doc_dict: Document properties dict from the loader
            doc_type: "adr" or "principle"

        Returns:
            The same dict, potentially enriched with registry data
        """
        if not self._registry:
            return doc_dict

        # Build lookup key from the document number
        if doc_type == "adr":
            number = doc_dict.get("adr_number", "")
            prefix = "ADR"
        else:
            number = doc_dict.get("principle_number", "")
            prefix = "PCP"

        if not number:
            return doc_dict

        # Try padded format first (e.g., "ADR.0029")
        registry_entry = self._registry.get(f"{prefix}.{number}")
        if not registry_entry:
            return doc_dict

        # Enrich only empty fields — frontmatter is authoritative
        enriched = False

        if not doc_dict.get("status") and registry_entry.get("status"):
            doc_dict["status"] = registry_entry["status"]
            enriched = True

        if not doc_dict.get("owner_display") and registry_entry.get("owner"):
            doc_dict["owner_display"] = registry_entry["owner"]
            enriched = True

        if enriched:
            doc_dict["registry_enriched"] = True
            logger.debug(f"Enriched {prefix}.{number} from registry: status={doc_dict.get('status')}")
        else:
            doc_dict["registry_enriched"] = False

        return doc_dict

    def run_full_ingestion(
        self,
        recreate_collections: bool = False,
        batch_size: int = DEFAULT_BATCH_SIZE,
        chunked: bool = False,
    ) -> dict:
        """Run full data ingestion pipeline.

        All collections use client-side embeddings (Ollama/Nomic). The LLM
        provider used for inference is independent of embeddings.

        Args:
            recreate_collections: If True, recreate all collections
            batch_size: Number of objects per embedding batch
            chunked: If True, use section-based chunking (multiple chunks per document)

        Returns:
            Dictionary with ingestion statistics
        """
        logger.info("Starting full data ingestion pipeline...")
        logger.info(f"Batch size: {batch_size}, Chunked mode: {chunked}")

        # Create collections (also cleans up legacy _OpenAI collections)
        self.collection_manager.create_all_collections(recreate=recreate_collections)

        stats = {
            "vocabulary": 0,
            "adr": 0,
            "principle": 0,
            "policy": 0,
            "errors": [],
        }

        # Vocabulary ingestion disabled — SKOSMOS REST API is now the
        # source of truth for vocabulary lookups. The Weaviate Vocabulary
        # collection was stale ingested .ttl data and has been deleted.
        # try:
        #     stats["vocabulary"] = self._ingest_vocabularies(batch_size)
        # except Exception as e:
        #     logger.error(f"Error ingesting vocabularies: {e}")
        #     stats["errors"].append(f"vocabulary: {str(e)}")

        if chunked:
            # Chunked ingestion path: section-level chunks per document
            try:
                stats["adr"] = self._ingest_adrs_chunked(batch_size)
            except Exception as e:
                logger.error(f"Error ingesting chunked ADRs: {e}")
                stats["errors"].append(f"adr: {str(e)}")

            try:
                stats["principle"] = self._ingest_principles_chunked(batch_size)
            except Exception as e:
                logger.error(f"Error ingesting chunked principles: {e}")
                stats["errors"].append(f"principle: {str(e)}")

            try:
                stats["policy"] = self._ingest_policies_chunked(batch_size)
            except Exception as e:
                logger.error(f"Error ingesting chunked policies: {e}")
                stats["errors"].append(f"policy: {str(e)}")
        else:
            # Legacy ingestion path: one document = one Weaviate object
            try:
                stats["adr"] = self._ingest_adrs(batch_size)
            except Exception as e:
                logger.error(f"Error ingesting ADRs: {e}")
                stats["errors"].append(f"adr: {str(e)}")

            try:
                stats["principle"] = self._ingest_principles(batch_size)
            except Exception as e:
                logger.error(f"Error ingesting principles: {e}")
                stats["errors"].append(f"principle: {str(e)}")

            try:
                stats["policy"] = self._ingest_policies(batch_size)
            except Exception as e:
                logger.error(f"Error ingesting policies: {e}")
                stats["errors"].append(f"policy: {str(e)}")

        logger.info(f"Ingestion complete. Stats: {stats}")
        return stats

    def _ingest_adrs(self, batch_size: int) -> int:
        """Ingest Architectural Decision Records.

        Returns:
            Number of ADRs ingested.
        """
        adr_path = settings.resolve_path(settings.markdown_path) / "decisions"
        if not adr_path.exists():
            logger.warning(f"ADR path does not exist: {adr_path}")
            return 0

        loader = MarkdownLoader(adr_path)
        collection = self.client.collections.get(CollectionManager.ADR_COLLECTION)

        count = 0
        batch = []
        enriched_count = 0

        for doc_dict in loader.load_adrs(adr_path):
            doc_dict = self._enrich_from_registry(doc_dict, "adr")
            if doc_dict.get("registry_enriched"):
                enriched_count += 1

            batch.append(DataObject(properties=doc_dict, uuid=str(uuid4())))
            count += 1

            if len(batch) >= batch_size:
                self._insert_batch_with_embeddings(collection, batch, "adr", "full_text")
                batch = []

        if batch:
            self._insert_batch_with_embeddings(collection, batch, "adr", "full_text")

        logger.info(f"Ingested {count} ADRs ({enriched_count} enriched from registry)")
        return count

    def _ingest_principles(self, batch_size: int) -> int:
        """Ingest principle documents.

        Returns:
            Number of principles ingested.
        """
        principles_path = settings.resolve_path(settings.principles_path)
        if not principles_path.exists():
            logger.warning(f"Principles path does not exist: {principles_path}")
            return 0

        collection = self.client.collections.get(CollectionManager.PRINCIPLE_COLLECTION)
        loader = MarkdownLoader(principles_path)

        count = 0
        enriched_count = 0
        batch = []

        for doc_dict in loader.load_principles(principles_path):
            doc_dict = self._enrich_from_registry(doc_dict, "principle")
            if doc_dict.get("registry_enriched"):
                enriched_count += 1

            batch.append(DataObject(properties=doc_dict, uuid=str(uuid4())))
            count += 1

            if len(batch) >= batch_size:
                self._insert_batch_with_embeddings(collection, batch, "principle", "full_text")
                batch = []

        if batch:
            self._insert_batch_with_embeddings(collection, batch, "principle", "full_text")

        logger.info(f"Ingested {count} principles ({enriched_count} enriched from registry)")
        return count

    def _get_policy_paths(self) -> list[Path]:
        """Return all configured policy source directories that exist."""
        paths = []
        for attr in ("policy_path", "corporate_policy_path"):
            p = settings.resolve_path(getattr(settings, attr))
            if p.exists():
                paths.append(p)
            else:
                logger.warning(f"Policy path does not exist: {p}")
        return paths

    def _ingest_policies(self, batch_size: int) -> int:
        """Ingest policy documents (DOCX/PDF) from all configured paths.

        Returns:
            Number of policy documents ingested.
        """
        policy_paths = self._get_policy_paths()
        if not policy_paths:
            return 0

        collection = self.client.collections.get(CollectionManager.POLICY_COLLECTION)

        count = 0
        batch = []

        for policy_path in policy_paths:
            loader = DocumentLoader(policy_path)
            for doc_dict in loader.load_all():
                batch.append(DataObject(properties=doc_dict, uuid=str(uuid4())))
                count += 1

                if len(batch) >= batch_size:
                    self._insert_batch_with_embeddings(collection, batch, "policy", "full_text")
                    batch = []

        if batch:
            self._insert_batch_with_embeddings(collection, batch, "policy", "full_text")

        logger.info(f"Ingested {count} policy documents")
        return count

    # =====================================================================
    # Chunked ingestion methods
    # =====================================================================

    def _enrich_chunk_from_registry(self, chunk, doc_type: str, number: str) -> None:
        """Enrich a Chunk's metadata with registry data if fields are missing.

        Modifies the chunk in-place so build_full_text() picks up status/owner.
        """
        if not self._registry or not number:
            return

        prefix = "ADR" if doc_type == "adr" else "PCP"
        padded = number.zfill(4)
        entry = self._registry.get(f"{prefix}.{padded}")
        if not entry:
            return

        if not chunk.metadata.adr_status and entry.get("status"):
            chunk.metadata.adr_status = entry["status"]
        if not chunk.metadata.owner_display and entry.get("owner"):
            chunk.metadata.owner_display = entry["owner"]

    def _chunk_to_properties(self, chunk, doc_type: str, number: str, chunk_index: int) -> dict:
        """Convert a Chunk to a Weaviate-compatible properties dict.

        Maps chunk fields to the existing collection schema while adding
        chunk-specific fields.
        """
        props = {
            # Standard fields expected by the collection schema
            "file_path": chunk.metadata.source_file,
            "title": chunk.metadata.document_title,
            "content": chunk.content,
            "full_text": chunk.full_text or chunk.build_full_text(),
            "doc_type": chunk.metadata.document_type or doc_type,
            "status": chunk.metadata.adr_status,
            # Chunk-specific fields (Step 3)
            "chunk_type": chunk.chunk_type.value,
            "section_name": chunk.metadata.section_name,
            "chunk_index": chunk_index,
            "document_id": chunk.metadata.root_document_id or "",
            "content_hash": chunk.content_hash,
            # Ownership fields
            "owner_team": chunk.metadata.owner_team,
            "owner_team_abbr": chunk.metadata.owner_team_abbr,
            "owner_department": chunk.metadata.owner_department,
            "owner_organization": chunk.metadata.owner_organization,
            "owner_display": chunk.metadata.owner_display,
            "collection_name": chunk.metadata.collection_name,
        }

        # ADR-specific fields
        if doc_type == "adr":
            props["adr_number"] = number
            props["context"] = ""
            props["decision"] = ""
            props["consequences"] = ""
            # For section chunks, populate the matching field
            section_type = chunk.metadata.section_type
            if section_type == "context":
                props["context"] = chunk.content
            elif section_type == "decision":
                props["decision"] = chunk.content
            elif section_type == "consequences":
                props["consequences"] = chunk.content

        # Principle-specific fields
        if doc_type == "principle":
            props["principle_number"] = number

        return props

    def _ingest_adrs_chunked(self, batch_size: int) -> int:
        """Ingest ADRs using section-based chunking.

        Returns:
            Number of ADR chunks ingested.
        """
        adr_path = settings.resolve_path(settings.markdown_path) / "decisions"
        if not adr_path.exists():
            logger.warning(f"ADR path does not exist: {adr_path}")
            return 0

        loader = MarkdownLoader(adr_path)
        collection = self.client.collections.get(CollectionManager.ADR_COLLECTION)

        count = 0
        batch = []

        config = ChunkingConfig(index_document_level=True, index_section_level=True, index_granular=False)

        for chunked_doc in loader.load_adrs_chunked(adr_path, config):
            title_lower = chunked_doc.document_title.lower()
            source_lower = chunked_doc.source_file.lower()
            # Skip non-content files: templates and index pages are
            # navigation/metadata, not actual ADR documents.
            filename = Path(chunked_doc.source_file).name.lower()
            if "template" in title_lower or "template" in source_lower or filename == "index.md":
                logger.debug(f"Skipping non-content file: {chunked_doc.source_file}")
                continue

            number_match = re.match(r"(\d{4})D?-", Path(chunked_doc.source_file).name)
            adr_number = number_match.group(1) if number_match else ""

            chunks = chunked_doc.get_chunks_for_indexing(
                include_document_level=config.index_document_level,
                include_section_level=config.index_section_level,
                include_granular=config.index_granular,
            )

            for chunk_idx, chunk in enumerate(chunks):
                self._enrich_chunk_from_registry(chunk, "adr", adr_number)
                chunk.full_text = chunk.build_full_text()

                props = self._chunk_to_properties(chunk, "adr", adr_number, chunk_idx)
                batch.append(DataObject(properties=props, uuid=str(uuid4())))
                count += 1

                if len(batch) >= batch_size:
                    self._insert_batch_with_embeddings(collection, batch, "adr_chunked", "full_text")
                    batch = []

        if batch:
            self._insert_batch_with_embeddings(collection, batch, "adr_chunked", "full_text")

        logger.info(f"Ingested {count} ADR chunks")
        return count

    def _ingest_principles_chunked(self, batch_size: int) -> int:
        """Ingest principles using section-based chunking.

        Returns:
            Number of principle chunks ingested.
        """
        principles_path = settings.resolve_path(settings.principles_path)
        if not principles_path.exists():
            logger.warning(f"Principles path does not exist: {principles_path}")
            return 0

        collection = self.client.collections.get(CollectionManager.PRINCIPLE_COLLECTION)
        loader = MarkdownLoader(principles_path)

        count = 0
        batch = []

        config = ChunkingConfig(index_document_level=True, index_section_level=True, index_granular=False)

        for chunked_doc in loader.load_principles_chunked(principles_path, config):
            title_lower = chunked_doc.document_title.lower()
            source_lower = chunked_doc.source_file.lower()
            filename = Path(chunked_doc.source_file).name.lower()
            if "template" in title_lower or "template" in source_lower or filename == "index.md":
                logger.debug(f"Skipping non-content file: {chunked_doc.source_file}")
                continue

            number_match = re.match(r"(\d{4})D?-", Path(chunked_doc.source_file).name)
            principle_number = number_match.group(1) if number_match else ""

            chunks = chunked_doc.get_chunks_for_indexing(
                include_document_level=config.index_document_level,
                include_section_level=config.index_section_level,
                include_granular=config.index_granular,
            )

            for chunk_idx, chunk in enumerate(chunks):
                self._enrich_chunk_from_registry(chunk, "principle", principle_number)
                chunk.full_text = chunk.build_full_text()

                props = self._chunk_to_properties(chunk, "principle", principle_number, chunk_idx)
                batch.append(DataObject(properties=props, uuid=str(uuid4())))
                count += 1

                if len(batch) >= batch_size:
                    self._insert_batch_with_embeddings(collection, batch, "principle_chunked", "full_text")
                    batch = []

        if batch:
            self._insert_batch_with_embeddings(collection, batch, "principle_chunked", "full_text")

        logger.info(f"Ingested {count} principle chunks")
        return count

    def _ingest_policies_chunked(self, batch_size: int) -> int:
        """Ingest policy documents from all configured paths using structure-aware chunking.

        Returns:
            Number of policy chunks ingested.
        """
        policy_paths = self._get_policy_paths()
        if not policy_paths:
            return 0

        collection = self.client.collections.get(CollectionManager.POLICY_COLLECTION)

        count = 0
        batch = []

        for policy_path in policy_paths:
            loader = DocumentLoader(policy_path)
            for chunked_doc in loader.load_all_chunked():
                chunks = chunked_doc.get_chunks_for_indexing(
                    include_document_level=True,
                    include_section_level=True,
                    include_granular=False,
                )

                for chunk_idx, chunk in enumerate(chunks):
                    chunk.full_text = chunk.build_full_text()

                    props = {
                        "file_path": chunk.metadata.source_file,
                        "title": chunk.metadata.document_title,
                        "content": chunk.content,
                        "full_text": chunk.full_text,
                        "file_type": Path(chunk.metadata.source_file).suffix.lstrip(".") if chunk.metadata.source_file else "",
                        "page_count": 0,
                        "chunk_type": chunk.chunk_type.value,
                        "section_name": chunk.metadata.section_name,
                        "chunk_index": chunk_idx,
                        "document_id": chunk.metadata.root_document_id or "",
                        "content_hash": chunk.content_hash,
                        "owner_team": chunk.metadata.owner_team,
                        "owner_team_abbr": chunk.metadata.owner_team_abbr,
                        "owner_department": chunk.metadata.owner_department,
                        "owner_organization": chunk.metadata.owner_organization,
                        "owner_display": chunk.metadata.owner_display,
                        "collection_name": chunk.metadata.collection_name,
                    }

                    batch.append(DataObject(properties=props, uuid=str(uuid4())))
                    count += 1

                    if len(batch) >= batch_size:
                        self._insert_batch_with_embeddings(collection, batch, "policy_chunked", "full_text")
                        batch = []

        if batch:
            self._insert_batch_with_embeddings(collection, batch, "policy_chunked", "full_text")

        logger.info(f"Ingested {count} policy chunks")
        return count

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
