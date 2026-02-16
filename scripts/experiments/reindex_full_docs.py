#!/usr/bin/env python3
"""Reindex documents as full-doc (1 object per document) for the chunking experiment.

Creates parallel collections with _FULL suffix:
  - ArchitecturalDecision_FULL
  - Principle_FULL

Each document is a single Weaviate object with the full text embedded.
This allows comparing retrieval accuracy between chunked and full-doc strategies.

Usage:
    python scripts/experiments/reindex_full_docs.py [--recreate]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import settings
from src.weaviate.client import get_weaviate_client
from src.weaviate.embeddings import embed_text, embed_texts

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Full-doc collection names
FULL_DOC_COLLECTIONS = {
    "adr": "ArchitecturalDecision_FULL",
    "principle": "Principle_FULL",
}


def create_full_doc_collections(client, recreate: bool = False):
    """Create full-doc collections with same schema as originals."""
    from weaviate.classes.config import (
        Configure,
        Property,
        DataType,
        Tokenization,
        VectorDistances,
    )

    for logical_name, collection_name in FULL_DOC_COLLECTIONS.items():
        if client.collections.exists(collection_name):
            if recreate:
                logger.info(f"Deleting existing collection: {collection_name}")
                client.collections.delete(collection_name)
            else:
                logger.info(f"Collection {collection_name} already exists, skipping")
                continue

        logger.info(f"Creating full-doc collection: {collection_name}")

        # Common properties for both ADR and Principle full-doc collections
        properties = [
            Property(name="file_path", data_type=DataType.TEXT, tokenization=Tokenization.FIELD),
            Property(name="title", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
            Property(name="content", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
            Property(name="full_text", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
            Property(name="doc_type", data_type=DataType.TEXT, tokenization=Tokenization.FIELD),
        ]

        if logical_name == "adr":
            properties.extend([
                Property(name="adr_number", data_type=DataType.TEXT, tokenization=Tokenization.FIELD),
                Property(name="status", data_type=DataType.TEXT, tokenization=Tokenization.FIELD),
                Property(name="context", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
                Property(name="decision", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
                Property(name="consequences", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
            ])
        elif logical_name == "principle":
            properties.extend([
                Property(name="principle_number", data_type=DataType.TEXT, tokenization=Tokenization.FIELD),
            ])

        client.collections.create(
            name=collection_name,
            description=f"Full-document {logical_name} collection for chunking experiment",
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
            properties=properties,
        )
        logger.info(f"Created: {collection_name}")


def _filter_properties(doc: dict, collection_type: str) -> dict:
    """Filter doc properties to only those defined in the collection schema."""
    common_keys = {"file_path", "title", "content", "full_text", "doc_type"}
    adr_keys = common_keys | {"adr_number", "status", "context", "decision", "consequences"}
    principle_keys = common_keys | {"principle_number"}
    allowed = adr_keys if collection_type == "adr" else principle_keys
    return {k: v for k, v in doc.items() if k in allowed}


def ingest_full_docs(client):
    """Ingest documents as single objects (1 per file, no chunking)."""
    from src.loaders.markdown_loader import MarkdownLoader
    from weaviate.classes.data import DataObject

    base_path = settings.resolve_path(settings.markdown_path)
    loader = MarkdownLoader(base_path)
    stats = {"adr": 0, "principle": 0, "errors": []}

    # --- ADRs ---
    adr_path = settings.resolve_path(settings.markdown_path) / "decisions"
    if adr_path.exists():
        adr_collection = client.collections.get(FULL_DOC_COLLECTIONS["adr"])
        adrs = list(loader.load_adrs(adr_path))
        logger.info(f"Loaded {len(adrs)} ADR documents")

        for adr in adrs:
            doc = adr.to_dict() if hasattr(adr, "to_dict") else adr
            # Skip templates and index files
            doc_type = doc.get("doc_type", "content")
            if doc_type in ("template", "index"):
                continue

            text = doc.get("full_text", doc.get("content", ""))
            if not text.strip():
                continue

            try:
                vector = embed_text(text)
                adr_collection.data.insert(
                    properties=_filter_properties(doc, "adr"),
                    vector=vector,
                )
                stats["adr"] += 1
            except Exception as e:
                stats["errors"].append(f"ADR {doc.get('file_path', '?')}: {e}")
                logger.error(f"Failed to ingest ADR: {e}")

    # --- Principles ---
    principle_paths = [
        settings.resolve_path(settings.markdown_path) / "principles",
        settings.resolve_path(settings.principles_path),
    ]
    principle_collection = client.collections.get(FULL_DOC_COLLECTIONS["principle"])

    for principle_path in principle_paths:
        if not principle_path.exists():
            continue

        principles = list(loader.load_principles(principle_path))
        logger.info(f"Loaded {len(principles)} principle documents from {principle_path}")

        for principle in principles:
            doc = principle.to_dict() if hasattr(principle, "to_dict") else principle
            doc_type = doc.get("doc_type", "content")
            if doc_type in ("template", "index"):
                continue

            text = doc.get("full_text", doc.get("content", ""))
            if not text.strip():
                continue

            try:
                vector = embed_text(text)
                principle_collection.data.insert(
                    properties=_filter_properties(doc, "principle"),
                    vector=vector,
                )
                stats["principle"] += 1
            except Exception as e:
                stats["errors"].append(f"Principle {doc.get('file_path', '?')}: {e}")
                logger.error(f"Failed to ingest principle: {e}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Reindex documents as full-doc for chunking experiment")
    parser.add_argument("--recreate", action="store_true", help="Recreate collections if they exist")
    args = parser.parse_args()

    logger.info("Starting full-doc reindexing...")
    client = get_weaviate_client()

    try:
        create_full_doc_collections(client, recreate=args.recreate)
        stats = ingest_full_docs(client)

        logger.info("=== Full-Doc Reindex Complete ===")
        logger.info(f"  ADRs ingested: {stats['adr']}")
        logger.info(f"  Principles ingested: {stats['principle']}")
        if stats["errors"]:
            logger.warning(f"  Errors: {len(stats['errors'])}")
            for err in stats["errors"]:
                logger.warning(f"    {err}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
