"""
Populate golden dataset with actual chunk IDs after indexing.
Run this after index_documents.py to link queries to real chunks.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import yaml
import psycopg2


def load_config():
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_connection(config):
    return psycopg2.connect(
        host=config["database"]["host"],
        port=config["database"]["port"],
        dbname=config["database"]["name"],
        user=config["database"]["user"],
        password=os.environ.get("RAG_DB_PASSWORD", ""),
    )


def find_chunk_ids(conn, document_id: str, section: str = None) -> list:
    """Find chunk IDs for a document, optionally filtered by section."""
    query = "SELECT id FROM chunks WHERE document_id = %s"
    params = [document_id]

    if section and section != "*":
        query += " AND section_header = %s"
        params.append(section)

    with conn.cursor() as cur:
        cur.execute(query, params)
        return [row[0] for row in cur.fetchall()]


def find_term_ids(conn, pref_label: str = None, concept_uri: str = None) -> list:
    """Find terminology IDs by label or URI."""
    if concept_uri:
        query = "SELECT id FROM terminology WHERE concept_uri = %s"
        params = [concept_uri]
    elif pref_label:
        query = "SELECT id FROM terminology WHERE pref_label_en ILIKE %s OR pref_label_nl ILIKE %s"
        params = [f"%{pref_label}%", f"%{pref_label}%"]
    else:
        return []

    with conn.cursor() as cur:
        cur.execute(query, params)
        return [row[0] for row in cur.fetchall()]


def populate_golden_dataset():
    config = load_config()
    conn = get_connection(config)

    # Load golden dataset
    golden_path = Path(__file__).parent.parent / "evaluation" / "golden_dataset.yaml"
    with open(golden_path) as f:
        golden = yaml.safe_load(f)

    updated_count = 0
    missing_count = 0

    for query_entry in golden.get("queries", []):
        # Populate chunk IDs for relevant chunks
        for chunk in query_entry.get("relevant_chunks", []):
            if chunk.get("document_id"):
                chunk_ids = find_chunk_ids(conn, chunk["document_id"], chunk.get("section"))
                if chunk_ids:
                    chunk["chunk_ids"] = chunk_ids
                    updated_count += 1
                else:
                    print(
                        f"Warning: No chunks found for document_id={chunk['document_id']}, section={chunk.get('section')}"
                    )
                    missing_count += 1

        # Populate term IDs for relevant terms
        for term in query_entry.get("relevant_terms", []):
            term_ids = find_term_ids(
                conn,
                pref_label=term.get("pref_label_en") or term.get("pref_label_nl"),
                concept_uri=term.get("concept_uri"),
            )
            if term_ids:
                term["term_ids"] = term_ids
                updated_count += 1
            else:
                print(
                    f"Warning: No terms found for label={term.get('pref_label_en') or term.get('pref_label_nl')}"
                )
                missing_count += 1

    # Save updated golden dataset
    output_path = Path(__file__).parent.parent / "evaluation" / "golden_dataset_populated.yaml"
    with open(output_path, "w") as f:
        yaml.dump(golden, f, default_flow_style=False, allow_unicode=True)

    print(f"\nUpdated {updated_count} entries")
    print(f"Missing {missing_count} entries (no matching chunks/terms found)")
    print(f"Saved to {output_path}")

    conn.close()


if __name__ == "__main__":
    populate_golden_dataset()
