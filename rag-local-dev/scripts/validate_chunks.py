#!/usr/bin/env python3
"""
Chunk validation script.
Inspect chunks for quality and correctness.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
import logging
import argparse

from src.database.connection import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def show_chunk_stats(conn):
    """Display chunk statistics."""
    with conn.cursor() as cur:
        # Overall stats
        cur.execute("SELECT COUNT(*) FROM chunks")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NULL")
        no_embedding = cur.fetchone()[0]

        cur.execute("SELECT AVG(LENGTH(content)), MIN(LENGTH(content)), MAX(LENGTH(content)) FROM chunks")
        avg_len, min_len, max_len = cur.fetchone()

        # By type
        cur.execute("SELECT document_type, COUNT(*), AVG(LENGTH(content)) FROM chunks GROUP BY document_type")
        by_type = cur.fetchall()

    print("\n" + "=" * 60)
    print("CHUNK STATISTICS")
    print("=" * 60)
    print(f"Total chunks: {total}")
    print(f"Chunks without embedding: {no_embedding}")
    print(f"Content length - Avg: {avg_len:.0f}, Min: {min_len}, Max: {max_len}")
    print("\nBy document type:")
    for doc_type, count, avg in by_type:
        print(f"  {doc_type}: {count} chunks, avg length: {avg:.0f}")


def show_terminology_stats(conn):
    """Display terminology statistics."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM terminology")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM terminology WHERE embedding IS NULL")
        no_embedding = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM terminology WHERE definition IS NOT NULL")
        with_def = cur.fetchone()[0]

        cur.execute("SELECT vocabulary_name, COUNT(*) FROM terminology GROUP BY vocabulary_name ORDER BY COUNT(*) DESC")
        by_vocab = cur.fetchall()

    print("\n" + "=" * 60)
    print("TERMINOLOGY STATISTICS")
    print("=" * 60)
    print(f"Total concepts: {total}")
    print(f"Concepts without embedding: {no_embedding}")
    print(f"Concepts with definition: {with_def}")
    print("\nBy vocabulary:")
    for vocab, count in by_vocab[:15]:
        print(f"  {vocab}: {count}")
    if len(by_vocab) > 15:
        print(f"  ... and {len(by_vocab) - 15} more")


def sample_chunks(conn, doc_type: str = None, n: int = 5):
    """Show sample chunks."""
    query = "SELECT id, document_id, document_type, section_header, LEFT(content, 500) FROM chunks"
    params = {}

    if doc_type:
        query += " WHERE document_type = %(doc_type)s"
        params["doc_type"] = doc_type

    query += " ORDER BY RANDOM() LIMIT %(n)s"
    params["n"] = n

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    print("\n" + "=" * 60)
    print(f"SAMPLE CHUNKS" + (f" (type: {doc_type})" if doc_type else ""))
    print("=" * 60)

    for row in rows:
        print(f"\n--- Chunk ID: {row[0]} ---")
        print(f"Document: {row[1]} ({row[2]})")
        print(f"Section: {row[3]}")
        print(f"Content preview:\n{row[4]}...")


def sample_terminology(conn, vocab: str = None, n: int = 5):
    """Show sample terminology."""
    query = """
        SELECT concept_uri, pref_label_en, pref_label_nl, vocabulary_name, LEFT(definition, 300)
        FROM terminology
    """
    params = {}

    if vocab:
        query += " WHERE vocabulary_name ILIKE %(vocab)s"
        params["vocab"] = f"%{vocab}%"

    query += " ORDER BY RANDOM() LIMIT %(n)s"
    params["n"] = n

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    print("\n" + "=" * 60)
    print(f"SAMPLE TERMINOLOGY" + (f" (vocab: {vocab})" if vocab else ""))
    print("=" * 60)

    for row in rows:
        print(f"\n--- {row[1] or row[2]} ---")
        print(f"URI: {row[0]}")
        print(f"Vocabulary: {row[3]}")
        if row[4]:
            print(f"Definition: {row[4]}...")


def check_duplicates(conn):
    """Check for duplicate chunks."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT document_id, section_header, COUNT(*)
            FROM chunks
            WHERE document_id IS NOT NULL
            GROUP BY document_id, section_header
            HAVING COUNT(*) > 1
        """)
        duplicates = cur.fetchall()

    if duplicates:
        print("\n" + "=" * 60)
        print("POTENTIAL DUPLICATES")
        print("=" * 60)
        for doc_id, section, count in duplicates:
            print(f"  {doc_id} / {section}: {count} occurrences")
    else:
        print("\nNo duplicate chunks found.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate indexed chunks")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--sample-chunks", type=int, metavar="N", help="Show N sample chunks")
    parser.add_argument("--sample-terms", type=int, metavar="N", help="Show N sample terminology")
    parser.add_argument("--doc-type", help="Filter by document type")
    parser.add_argument("--vocab", help="Filter by vocabulary name")
    parser.add_argument("--check-duplicates", action="store_true", help="Check for duplicates")
    parser.add_argument("--all", action="store_true", help="Run all checks")
    args = parser.parse_args()

    config = load_config()
    conn = get_db_connection(config)

    try:
        if args.all or args.stats:
            show_chunk_stats(conn)
            show_terminology_stats(conn)

        if args.sample_chunks or args.all:
            n = args.sample_chunks or 3
            sample_chunks(conn, args.doc_type, n)

        if args.sample_terms or args.all:
            n = args.sample_terms or 3
            sample_terminology(conn, args.vocab, n)

        if args.check_duplicates or args.all:
            check_duplicates(conn)

        if not any([args.stats, args.sample_chunks, args.sample_terms, args.check_duplicates, args.all]):
            # Default: show stats
            show_chunk_stats(conn)
            show_terminology_stats(conn)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
