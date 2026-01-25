#!/usr/bin/env python3
"""
Main indexing script.
Processes all documents and populates the database.
"""

import os
import sys
from pathlib import Path
import json
import logging
import argparse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
import yaml
from tqdm import tqdm

from src.parsers.markdown_parser import (
    parse_markdown_directory,
    parse_adr,
    parse_principle,
    parse_governance_principle,
    parse_index_metadata,
)
from src.parsers.pdf_parser import parse_document_directory
from src.parsers.rdf_parser import parse_skos_directory, concept_to_embedding_text
from src.embedding.factory import get_embedder
from src.database.connection import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def index_adrs(conn, embedder, data_paths: dict, config: dict):
    """Index ADRs from markdown files."""
    adr_path = Path(__file__).parent.parent / data_paths.get("adrs", "")

    if not adr_path.exists():
        logger.warning(f"ADR path does not exist: {adr_path}")
        return 0

    logger.info(f"Indexing ADRs from: {adr_path}")

    # Get ownership info
    ownership = parse_index_metadata(adr_path / "index.md")

    # Find all markdown files
    files = [f for f in adr_path.glob("*.md") if f.name not in ["index.md", "adr-template.md"]]
    logger.info(f"Found {len(files)} ADR files")

    total_chunks = 0
    embedding_model = config["embedding"][config["embedding"]["provider"]]["model"]

    for filepath in tqdm(files, desc="Indexing ADRs"):
        try:
            chunks = parse_adr(filepath, ownership)

            if not chunks:
                continue

            # Generate embeddings in batch
            texts = [c.content for c in chunks]
            embeddings = embedder.embed(texts)

            # Insert into database
            with conn.cursor() as cur:
                for chunk, embedding in zip(chunks, embeddings):
                    cur.execute(
                        """
                        INSERT INTO chunks
                        (content, embedding, source_file, document_type, chunk_index,
                         total_chunks, section_header, document_id, document_title,
                         document_status, owner_team, owner_team_abbr, owner_department,
                         owner_organization, metadata, embedding_model, embedding_model_version)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            chunk.content,
                            embedding,
                            chunk.source_file,
                            chunk.document_type,
                            chunk.chunk_index,
                            len(chunks),
                            chunk.section_header,
                            chunk.document_id,
                            chunk.document_title,
                            chunk.document_status,
                            chunk.owner_team,
                            chunk.owner_team_abbr,
                            chunk.owner_department,
                            chunk.owner_organization,
                            json.dumps(chunk.metadata),
                            embedding_model,
                            "1.0",
                        ),
                    )
            conn.commit()
            total_chunks += len(chunks)

        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")
            conn.rollback()

    return total_chunks


def index_principles(conn, embedder, data_paths: dict, config: dict):
    """Index ESA Principles from markdown files."""
    principle_path = Path(__file__).parent.parent / data_paths.get("esa_principles", "")

    if not principle_path.exists():
        logger.warning(f"Principle path does not exist: {principle_path}")
        return 0

    logger.info(f"Indexing ESA Principles from: {principle_path}")

    ownership = parse_index_metadata(principle_path / "index.md")
    files = [f for f in principle_path.glob("*.md") if f.name not in ["index.md", "template.md"]]
    logger.info(f"Found {len(files)} Principle files")

    total_chunks = 0
    embedding_model = config["embedding"][config["embedding"]["provider"]]["model"]

    for filepath in tqdm(files, desc="Indexing Principles"):
        try:
            chunks = parse_principle(filepath, ownership)

            if not chunks:
                continue

            texts = [c.content for c in chunks]
            embeddings = embedder.embed(texts)

            with conn.cursor() as cur:
                for chunk, embedding in zip(chunks, embeddings):
                    cur.execute(
                        """
                        INSERT INTO chunks
                        (content, embedding, source_file, document_type, chunk_index,
                         total_chunks, section_header, document_id, document_title,
                         document_status, owner_team, owner_team_abbr, owner_department,
                         owner_organization, metadata, embedding_model, embedding_model_version)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            chunk.content,
                            embedding,
                            chunk.source_file,
                            chunk.document_type,
                            chunk.chunk_index,
                            len(chunks),
                            chunk.section_header,
                            chunk.document_id,
                            chunk.document_title,
                            chunk.document_status,
                            chunk.owner_team,
                            chunk.owner_team_abbr,
                            chunk.owner_department,
                            chunk.owner_organization,
                            json.dumps(chunk.metadata),
                            embedding_model,
                            "1.0",
                        ),
                    )
            conn.commit()
            total_chunks += len(chunks)

        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")
            conn.rollback()

    return total_chunks


def index_governance_principles(conn, embedder, data_paths: dict, config: dict):
    """Index Data Office governance principles (Dutch)."""
    principle_path = Path(__file__).parent.parent / data_paths.get("do_principles", "")

    if not principle_path.exists():
        logger.warning(f"DO Principle path does not exist: {principle_path}")
        return 0

    logger.info(f"Indexing Governance Principles from: {principle_path}")

    ownership = parse_index_metadata(principle_path / "index.md")
    files = [f for f in principle_path.glob("*.md") if f.name not in ["index.md", "template.md"]]
    logger.info(f"Found {len(files)} Governance Principle files")

    total_chunks = 0
    embedding_model = config["embedding"][config["embedding"]["provider"]]["model"]

    for filepath in tqdm(files, desc="Indexing Governance Principles"):
        try:
            chunks = parse_governance_principle(filepath, ownership)

            if not chunks:
                continue

            texts = [c.content for c in chunks]
            embeddings = embedder.embed(texts)

            with conn.cursor() as cur:
                for chunk, embedding in zip(chunks, embeddings):
                    cur.execute(
                        """
                        INSERT INTO chunks
                        (content, embedding, source_file, document_type, chunk_index,
                         total_chunks, section_header, document_id, document_title,
                         document_status, owner_team, owner_team_abbr, owner_department,
                         owner_organization, metadata, embedding_model, embedding_model_version)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            chunk.content,
                            embedding,
                            chunk.source_file,
                            "governance_principle",
                            chunk.chunk_index,
                            len(chunks),
                            chunk.section_header,
                            chunk.document_id,
                            chunk.document_title,
                            chunk.document_status,
                            chunk.owner_team,
                            chunk.owner_team_abbr,
                            chunk.owner_department,
                            chunk.owner_organization,
                            json.dumps(chunk.metadata),
                            embedding_model,
                            "1.0",
                        ),
                    )
            conn.commit()
            total_chunks += len(chunks)

        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")
            conn.rollback()

    return total_chunks


def index_policy_documents(conn, embedder, data_paths: dict, config: dict):
    """Index policy documents (PDF/DOCX)."""
    total_chunks = 0
    embedding_model = config["embedding"][config["embedding"]["provider"]]["model"]

    # Index from both policy directories
    for path_key in ["do_policy_docs", "general_policies"]:
        policy_path = Path(__file__).parent.parent / data_paths.get(path_key, "")

        if not policy_path.exists():
            logger.warning(f"Policy path does not exist: {policy_path}")
            continue

        logger.info(f"Indexing Policy Documents from: {policy_path}")

        chunks = parse_document_directory(policy_path)
        logger.info(f"Found {len(chunks)} chunks from policy documents")

        if not chunks:
            continue

        # Process in batches
        batch_size = config.get("embedding", {}).get("batch_size", 50)

        for i in tqdm(range(0, len(chunks), batch_size), desc=f"Indexing {path_key}"):
            batch = chunks[i : i + batch_size]
            texts = [c.content for c in batch]
            embeddings = embedder.embed(texts)

            with conn.cursor() as cur:
                for chunk, embedding in zip(batch, embeddings):
                    cur.execute(
                        """
                        INSERT INTO chunks
                        (content, embedding, source_file, document_type, chunk_index,
                         total_chunks, section_header, document_title, metadata,
                         embedding_model, embedding_model_version)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            chunk.content,
                            embedding,
                            chunk.source_file,
                            "policy",
                            chunk.chunk_index,
                            None,
                            chunk.section_header,
                            chunk.document_title,
                            json.dumps(
                                {
                                    "page_number": chunk.page_number,
                                    "has_tables": chunk.has_tables,
                                    "has_figures": chunk.has_figures,
                                    "file_type": chunk.file_type,
                                }
                            ),
                            embedding_model,
                            "1.0",
                        ),
                    )
            conn.commit()
            total_chunks += len(batch)

    return total_chunks


def index_terminology(conn, embedder, data_paths: dict, config: dict):
    """Index SKOS terminology from RDF files."""
    ontology_path = Path(__file__).parent.parent / data_paths.get("ontology", "")

    if not ontology_path.exists():
        logger.warning(f"Ontology path does not exist: {ontology_path}")
        return 0

    logger.info(f"Indexing SKOS terminology from: {ontology_path}")

    concepts = parse_skos_directory(ontology_path)
    logger.info(f"Found {len(concepts)} SKOS concepts")

    if not concepts:
        return 0

    # Process in batches
    batch_size = config.get("embedding", {}).get("batch_size", 100)
    total_indexed = 0

    for i in tqdm(range(0, len(concepts), batch_size), desc="Indexing terminology"):
        batch = concepts[i : i + batch_size]

        # Generate embedding texts
        texts = [concept_to_embedding_text(c) for c in batch]
        embeddings = embedder.embed(texts)

        with conn.cursor() as cur:
            for concept, embedding in zip(batch, embeddings):
                cur.execute(
                    """
                    INSERT INTO terminology
                    (concept_uri, pref_label_en, pref_label_nl, alt_labels,
                     definition, broader_uri, narrower_uris, related_uris,
                     in_scheme, notation, vocabulary_name, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (concept_uri) DO UPDATE SET
                        pref_label_en = EXCLUDED.pref_label_en,
                        pref_label_nl = EXCLUDED.pref_label_nl,
                        alt_labels = EXCLUDED.alt_labels,
                        definition = EXCLUDED.definition,
                        broader_uri = EXCLUDED.broader_uri,
                        narrower_uris = EXCLUDED.narrower_uris,
                        related_uris = EXCLUDED.related_uris,
                        in_scheme = EXCLUDED.in_scheme,
                        notation = EXCLUDED.notation,
                        vocabulary_name = EXCLUDED.vocabulary_name,
                        embedding = EXCLUDED.embedding,
                        indexed_at = CURRENT_TIMESTAMP
                """,
                    (
                        concept.concept_uri,
                        concept.pref_label_en,
                        concept.pref_label_nl,
                        concept.alt_labels or [],
                        concept.definition,
                        concept.broader_uri,
                        concept.narrower_uris or [],
                        concept.related_uris or [],
                        concept.in_scheme,
                        concept.notation,
                        concept.vocabulary_name,
                        embedding,
                    ),
                )
        conn.commit()
        total_indexed += len(batch)

    return total_indexed


def clear_all_data(conn):
    """Clear all data from the database."""
    logger.warning("Clearing all existing data...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE chunks RESTART IDENTITY CASCADE")
        cur.execute("TRUNCATE TABLE terminology RESTART IDENTITY CASCADE")
        cur.execute("TRUNCATE TABLE retrieval_logs RESTART IDENTITY CASCADE")
        cur.execute("TRUNCATE TABLE document_relationships RESTART IDENTITY CASCADE")
    conn.commit()
    logger.info("All data cleared")


def print_summary(conn):
    """Print indexing summary."""
    with conn.cursor() as cur:
        cur.execute("SELECT document_type, COUNT(*) FROM chunks GROUP BY document_type")
        chunk_counts = cur.fetchall()

        cur.execute("SELECT COUNT(*) FROM terminology")
        term_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT document_id) FROM chunks WHERE document_id IS NOT NULL")
        doc_count = cur.fetchone()[0]

        cur.execute("SELECT vocabulary_name, COUNT(*) FROM terminology GROUP BY vocabulary_name")
        vocab_counts = cur.fetchall()

    logger.info("=" * 50)
    logger.info("INDEXING COMPLETE")
    logger.info("=" * 50)
    logger.info(f"Total documents: {doc_count}")
    logger.info("Chunk counts by type:")
    for doc_type, count in chunk_counts:
        logger.info(f"  {doc_type}: {count}")
    logger.info(f"Total terminology concepts: {term_count}")
    logger.info("Terminology by vocabulary:")
    for vocab, count in vocab_counts[:10]:  # Show top 10
        logger.info(f"  {vocab}: {count}")
    if len(vocab_counts) > 10:
        logger.info(f"  ... and {len(vocab_counts) - 10} more vocabularies")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Index documents into RAG database")
    parser.add_argument("--clear", action="store_true", help="Clear all existing data before indexing")
    parser.add_argument("--only", choices=["adrs", "principles", "governance", "policies", "terminology"],
                        help="Only index specific document type")
    args = parser.parse_args()

    config = load_config()
    data_paths = config.get("data_paths", {})

    logger.info("Connecting to database...")
    conn = get_db_connection(config)

    if args.clear:
        clear_all_data(conn)

    logger.info("Initializing embedder...")
    embedder = get_embedder(config)

    logger.info("Starting indexing...")

    # Index based on --only flag or all
    if args.only is None or args.only == "adrs":
        adr_count = index_adrs(conn, embedder, data_paths, config)
        logger.info(f"Indexed {adr_count} ADR chunks")

    if args.only is None or args.only == "principles":
        principle_count = index_principles(conn, embedder, data_paths, config)
        logger.info(f"Indexed {principle_count} Principle chunks")

    if args.only is None or args.only == "governance":
        gov_count = index_governance_principles(conn, embedder, data_paths, config)
        logger.info(f"Indexed {gov_count} Governance Principle chunks")

    if args.only is None or args.only == "policies":
        policy_count = index_policy_documents(conn, embedder, data_paths, config)
        logger.info(f"Indexed {policy_count} Policy document chunks")

    if args.only is None or args.only == "terminology":
        term_count = index_terminology(conn, embedder, data_paths, config)
        logger.info(f"Indexed {term_count} terminology concepts")

    # Print summary
    print_summary(conn)

    conn.close()


if __name__ == "__main__":
    main()
