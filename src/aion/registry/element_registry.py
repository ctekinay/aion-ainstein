"""Element Registry — stable identity for ArchiMate elements across generations.

Provides canonical IDs so the same conceptual element (e.g., "Grid Operations")
gets the same UUID whether generated in session A or session B. Uses the same
chat_history.db as chat_ui.py and session_store.py.

Matching is conservative: exact match on (element_type, canonical_name). Near-miss
detection (Levenshtein ≤ 3) is logged as warnings but never acted on automatically.
"""

import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Same database as chat_ui.py and session_store.py
_DB_PATH = Path(__file__).parent.parent.parent.parent / "chat_history.db"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_registry_table(db_path: Path | None = None) -> None:
    """Create element_registry table if it doesn't exist.

    Called from chat_ui.init_db() during startup — not independently.
    """
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS element_registry (
            canonical_id        TEXT PRIMARY KEY,
            workspace_id        TEXT NOT NULL DEFAULT 'default',
            element_type        TEXT NOT NULL,
            canonical_name      TEXT NOT NULL,
            display_name        TEXT NOT NULL,
            documentation       TEXT,
            dct_identifier      TEXT,
            dct_title           TEXT,
            source_doc_refs     TEXT,
            created_at          TEXT NOT NULL,
            last_used_at        TEXT NOT NULL,
            generation_count    INTEGER DEFAULT 1,
            provenance_artifact_id TEXT
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_unique_element
        ON element_registry(workspace_id, element_type, canonical_name)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_registry_workspace
        ON element_registry(workspace_id)
    """)

    conn.commit()
    conn.close()
    logger.debug("Element registry table initialized")


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

def _canonical_name(name: str) -> str:
    """Normalize element name for matching.

    Lowercase, collapse whitespace, strip trailing punctuation.
    NO article removal — "A/B Testing" must not become "b testing".
    """
    s = name.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = s.rstrip(".,;:!?")
    return s


def _levenshtein(s: str, t: str) -> int:
    """Standard Levenshtein distance (DP). Pure Python."""
    n, m = len(s), len(t)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if s[i - 1] == t[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[m]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def lookup_element(
    element_type: str,
    display_name: str,
    workspace_id: str = "default",
    db_path: Path | None = None,
) -> dict | None:
    """Find a registry entry by (element_type, canonical_name, workspace_id)."""
    path = db_path or _DB_PATH
    cn = _canonical_name(display_name)
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT canonical_id, element_type, canonical_name, display_name, "
        "documentation, dct_identifier, dct_title, source_doc_refs, "
        "created_at, last_used_at, generation_count, provenance_artifact_id "
        "FROM element_registry "
        "WHERE element_type = ? AND canonical_name = ? AND workspace_id = ?",
        (element_type, cn, workspace_id),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "canonical_id": row[0],
        "element_type": row[1],
        "canonical_name": row[2],
        "display_name": row[3],
        "documentation": row[4] or "",
        "dct_identifier": row[5] or "",
        "dct_title": row[6] or "",
        "source_doc_refs": json.loads(row[7]) if row[7] else [],
        "created_at": row[8],
        "last_used_at": row[9],
        "generation_count": row[10],
        "provenance_artifact_id": row[11] or "",
    }


def register_element(
    element_type: str,
    display_name: str,
    documentation: str = "",
    dct_identifier: str | None = None,
    dct_title: str | None = None,
    source_doc_refs: list[str] | None = None,
    workspace_id: str = "default",
    provenance_artifact_id: str | None = None,
    db_path: Path | None = None,
) -> str:
    """Register a new element. Returns canonical_id = 'id-{uuid4}'.

    Auto-generates dct_identifier (urn:uuid:...) if not provided.
    """
    path = db_path or _DB_PATH
    canonical_id = f"id-{uuid.uuid4()}"
    cn = _canonical_name(display_name)
    now = datetime.now().isoformat()

    if not dct_identifier:
        dct_identifier = f"urn:uuid:{uuid.uuid4()}"

    refs_json = json.dumps(source_doc_refs or [])

    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute("BEGIN IMMEDIATE")
    try:
        cursor.execute(
            "INSERT INTO element_registry "
            "(canonical_id, workspace_id, element_type, canonical_name, display_name, "
            "documentation, dct_identifier, dct_title, source_doc_refs, "
            "created_at, last_used_at, generation_count, provenance_artifact_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (
                canonical_id, workspace_id, element_type, cn, display_name,
                documentation, dct_identifier, dct_title or "", refs_json,
                now, now, provenance_artifact_id or "",
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # UNIQUE constraint hit — element was registered between lookup and insert
        conn.rollback()
        cursor.execute(
            "SELECT canonical_id FROM element_registry "
            "WHERE workspace_id = ? AND element_type = ? AND canonical_name = ?",
            (workspace_id, element_type, cn),
        )
        row = cursor.fetchone()
        if row:
            logger.warning(
                "Duplicate registration avoided for %s '%s' — returning existing %s",
                element_type, display_name, row[0],
            )
            conn.close()
            return row[0]
    conn.close()
    return canonical_id


def update_element_usage(
    canonical_id: str,
    new_doc_refs: list[str] | None = None,
    db_path: Path | None = None,
) -> None:
    """Bump generation_count and last_used_at. Merge new doc_refs."""
    path = db_path or _DB_PATH
    now = datetime.now().isoformat()

    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    if new_doc_refs:
        # Atomic JSON merge — no read-modify-write race
        # Build a JSON array literal for the new refs to merge
        new_refs_json = json.dumps(sorted(set(new_doc_refs)))
        cursor.execute(
            "UPDATE element_registry SET "
            "generation_count = generation_count + 1, "
            "last_used_at = ?, "
            "source_doc_refs = ("
            "  SELECT json_group_array(value) FROM ("
            "    SELECT DISTINCT value FROM ("
            "      SELECT value FROM json_each(COALESCE(source_doc_refs, '[]'))"
            "      UNION"
            "      SELECT value FROM json_each(?)"
            "    ) ORDER BY value"
            "  )"
            ") "
            "WHERE canonical_id = ?",
            (now, new_refs_json, canonical_id),
        )
    else:
        cursor.execute(
            "UPDATE element_registry SET generation_count = generation_count + 1, "
            "last_used_at = ? WHERE canonical_id = ?",
            (now, canonical_id),
        )

    if cursor.rowcount == 0:
        logger.warning(
            "update_element_usage: canonical_id '%s' not found in registry",
            canonical_id,
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Near-miss detection
# ---------------------------------------------------------------------------

def _check_near_miss(
    element_type: str,
    canonical_name: str,
    workspace_id: str = "default",
    db_path: Path | None = None,
) -> None:
    """Log warning if a newly registered element is close to an existing one."""
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT canonical_name, display_name FROM element_registry "
        "WHERE element_type = ? AND workspace_id = ? AND canonical_name != ?",
        (element_type, workspace_id, canonical_name),
    )
    rows = cursor.fetchall()
    conn.close()

    for existing_cn, existing_display in rows:
        dist = _levenshtein(canonical_name, existing_cn)
        if dist <= 3:
            logger.warning(
                "Near-duplicate detected: new '%s' vs existing '%s' "
                "(type=%s, distance=%d)",
                canonical_name, existing_display, element_type, dist,
            )


# ---------------------------------------------------------------------------
# Reconciliation — main entry point for generation pipeline
# ---------------------------------------------------------------------------

def reconcile_elements(
    elements: list[dict],
    doc_refs: list[str] | None = None,
    source_metadata: dict | None = None,
    workspace_id: str = "default",
    provenance_artifact_id: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """Reconcile elements against the registry. Returns {"elements": [...], "id_map": {...}}.

    For each element:
    - If (type, name) exists in registry: rewrite id to canonical, bump usage
    - If new: register, rewrite id, check near-misses

    source_metadata is used to look up dct_identifier for new elements
    via their source_ref field. Only rewrites id fields. Does NOT touch
    source_ref, properties, documentation, or name.
    """
    id_map: dict[str, str] = {}

    for elem in elements:
        original_id = elem.get("id", "")
        etype = elem.get("type", "")
        name = elem.get("name", "")

        if not etype or not name:
            logger.warning(
                "Skipping element with missing type or name: id=%s type=%r name=%r",
                original_id, etype, name,
            )
            continue

        existing = lookup_element(etype, name, workspace_id, db_path)

        if existing:
            canonical_id = existing["canonical_id"]
            update_element_usage(canonical_id, doc_refs, db_path)
            # Strip "id-" prefix — _parse_and_validate re-adds it
            new_short_id = canonical_id[3:] if canonical_id.startswith("id-") else canonical_id
        else:
            # Look up dct_identifier from source_metadata via source_ref
            dct_id = None
            if source_metadata:
                ref = elem.get("source_ref", "")
                if ref and ref in source_metadata:
                    dct_id = source_metadata[ref].get("kb_uuid")

            canonical_id = register_element(
                element_type=etype,
                display_name=name,
                documentation=elem.get("documentation", ""),
                dct_identifier=dct_id,
                source_doc_refs=doc_refs,
                workspace_id=workspace_id,
                provenance_artifact_id=provenance_artifact_id,
                db_path=db_path,
            )
            new_short_id = canonical_id[3:] if canonical_id.startswith("id-") else canonical_id
            cn = _canonical_name(name)
            _check_near_miss(etype, cn, workspace_id, db_path)

        id_map[original_id] = new_short_id
        elem["id"] = new_short_id

    return {"elements": elements, "id_map": id_map}


# ---------------------------------------------------------------------------
# Prompt context — registry elements for LLM prompt injection
# ---------------------------------------------------------------------------

def query_registry_for_prompt(
    doc_refs: list[str] | None = None,
    workspace_id: str = "default",
    limit: int = 30,
    db_path: Path | None = None,
) -> list[dict]:
    """Query registry elements for prompt injection, three-tier priority.

    Tier 1: source_doc_refs overlap with current doc_refs
    Tier 2: Recency (last_used_at DESC)
    Tier 3: Hub elements (generation_count DESC)

    Returns [{canonical_id, element_type, display_name, source_doc_refs}].
    """
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    results: list[dict] = []
    seen_ids: set[str] = set()

    def _add_rows(rows: list) -> None:
        for row in rows:
            cid = row[0]
            if cid not in seen_ids and len(results) < limit:
                seen_ids.add(cid)
                results.append({
                    "canonical_id": cid,
                    "element_type": row[1],
                    "display_name": row[2],
                    "source_doc_refs": json.loads(row[3]) if row[3] else [],
                })

    cols = "canonical_id, element_type, display_name, source_doc_refs"

    # Tier 1: doc_ref overlap
    if doc_refs:
        cursor.execute(
            f"SELECT {cols} FROM element_registry "
            "WHERE workspace_id = ? ORDER BY generation_count DESC",
            (workspace_id,),
        )
        all_rows = cursor.fetchall()
        ref_set = set(doc_refs)
        tier1 = [
            r for r in all_rows
            if ref_set & set(json.loads(r[3]) if r[3] else [])
        ]
        _add_rows(tier1)

    # Tier 2: recency
    if len(results) < limit:
        cursor.execute(
            f"SELECT {cols} FROM element_registry "
            "WHERE workspace_id = ? ORDER BY last_used_at DESC LIMIT ?",
            (workspace_id, limit),
        )
        _add_rows(cursor.fetchall())

    # Tier 3: hubs
    if len(results) < limit:
        cursor.execute(
            f"SELECT {cols} FROM element_registry "
            "WHERE workspace_id = ? ORDER BY generation_count DESC LIMIT ?",
            (workspace_id, limit),
        )
        _add_rows(cursor.fetchall())

    conn.close()
    return results


def format_registry_context(elements: list[dict]) -> str:
    """Format registry elements as YAML block for prompt injection."""
    if not elements:
        return ""
    lines = ["KNOWN ELEMENTS (reuse these IDs when applicable):"]
    for elem in elements:
        refs = ", ".join(elem.get("source_doc_refs", []))
        ref_note = f"  # from {refs}" if refs else ""
        lines.append(
            f"  - id: {elem['canonical_id']}"
            f"\n    type: {elem['element_type']}"
            f"\n    name: \"{elem['display_name']}\"{ref_note}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI support — list, merge, stats, near-duplicates
# ---------------------------------------------------------------------------

def list_all(
    element_type: str | None = None,
    workspace_id: str = "default",
    db_path: Path | None = None,
) -> list[dict]:
    """List all registry entries, optionally filtered by type."""
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    if element_type:
        cursor.execute(
            "SELECT canonical_id, element_type, display_name, source_doc_refs, "
            "generation_count, last_used_at "
            "FROM element_registry WHERE workspace_id = ? AND element_type = ? "
            "ORDER BY element_type, display_name",
            (workspace_id, element_type),
        )
    else:
        cursor.execute(
            "SELECT canonical_id, element_type, display_name, source_doc_refs, "
            "generation_count, last_used_at "
            "FROM element_registry WHERE workspace_id = ? "
            "ORDER BY element_type, display_name",
            (workspace_id,),
        )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "canonical_id": r[0],
            "element_type": r[1],
            "display_name": r[2],
            "source_doc_refs": json.loads(r[3]) if r[3] else [],
            "generation_count": r[4],
            "last_used_at": r[5],
        }
        for r in rows
    ]


def find_near_duplicates(
    workspace_id: str = "default",
    db_path: Path | None = None,
) -> list[tuple[dict, dict, int]]:
    """Find near-duplicate pairs (Levenshtein ≤ 3, same type).

    Returns [(entry_a, entry_b, distance), ...].
    """
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT canonical_id, element_type, canonical_name, display_name "
        "FROM element_registry WHERE workspace_id = ? "
        "ORDER BY element_type, canonical_name",
        (workspace_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    pairs: list[tuple[dict, dict, int]] = []
    for i, (cid_a, type_a, cn_a, dn_a) in enumerate(rows):
        for cid_b, type_b, cn_b, dn_b in rows[i + 1:]:
            if type_a != type_b:
                continue
            dist = _levenshtein(cn_a, cn_b)
            if dist <= 3:
                pairs.append((
                    {"canonical_id": cid_a, "element_type": type_a, "display_name": dn_a},
                    {"canonical_id": cid_b, "element_type": type_b, "display_name": dn_b},
                    dist,
                ))
    return pairs


def merge_elements(
    survivor_id: str,
    absorbed_id: str,
    db_path: Path | None = None,
) -> str:
    """Merge absorbed element into survivor. Returns survivor_id.

    Unions source_doc_refs, keeps max generation_count, deletes absorbed.
    """
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute("BEGIN IMMEDIATE")

    cursor.execute(
        "SELECT source_doc_refs, generation_count FROM element_registry "
        "WHERE canonical_id = ?",
        (survivor_id,),
    )
    survivor = cursor.fetchone()
    if not survivor:
        conn.close()
        raise ValueError(f"Survivor element {survivor_id} not found")

    cursor.execute(
        "SELECT source_doc_refs, generation_count FROM element_registry "
        "WHERE canonical_id = ?",
        (absorbed_id,),
    )
    absorbed = cursor.fetchone()
    if not absorbed:
        conn.close()
        raise ValueError(f"Absorbed element {absorbed_id} not found")

    # Union doc_refs
    survivor_refs = set(json.loads(survivor[0]) if survivor[0] else [])
    absorbed_refs = set(json.loads(absorbed[0]) if absorbed[0] else [])
    merged_refs = sorted(survivor_refs | absorbed_refs)

    # Keep max generation_count
    max_count = max(survivor[1], absorbed[1])

    cursor.execute(
        "UPDATE element_registry SET source_doc_refs = ?, generation_count = ? "
        "WHERE canonical_id = ?",
        (json.dumps(merged_refs), max_count, survivor_id),
    )
    cursor.execute(
        "DELETE FROM element_registry WHERE canonical_id = ?",
        (absorbed_id,),
    )

    conn.commit()
    conn.close()
    return survivor_id


def get_stats(
    workspace_id: str = "default",
    db_path: Path | None = None,
) -> dict:
    """Registry statistics: total, by_type breakdown, near_duplicates count."""
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM element_registry WHERE workspace_id = ?",
        (workspace_id,),
    )
    total = cursor.fetchone()[0]

    cursor.execute(
        "SELECT element_type, COUNT(*) FROM element_registry "
        "WHERE workspace_id = ? GROUP BY element_type ORDER BY element_type",
        (workspace_id,),
    )
    by_type = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()

    near_dupes = len(find_near_duplicates(workspace_id, db_path))

    return {
        "total": total,
        "by_type": by_type,
        "near_duplicates": near_dupes,
    }


def backfill_dct_identifiers(
    source_metadata: dict[str, dict],
    workspace_id: str = "default",
    db_path: Path | None = None,
) -> int:
    """Backfill dct_identifier for existing registry entries using source metadata.

    Matches entries by source_doc_refs overlap with source_metadata keys.
    Returns count of entries updated.
    """
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT canonical_id, source_doc_refs, dct_identifier "
        "FROM element_registry WHERE workspace_id = ?",
        (workspace_id,),
    )
    rows = cursor.fetchall()
    updated = 0

    for canonical_id, refs_json, current_dct_id in rows:
        refs = json.loads(refs_json) if refs_json else []
        # Find first matching source_metadata key
        new_dct_id = None
        for ref in refs:
            if ref in source_metadata:
                new_dct_id = source_metadata[ref].get("kb_uuid")
                if new_dct_id:
                    break

        if new_dct_id and new_dct_id != current_dct_id:
            cursor.execute(
                "UPDATE element_registry SET dct_identifier = ? WHERE canonical_id = ?",
                (new_dct_id, canonical_id),
            )
            updated += 1

    conn.commit()
    conn.close()
    return updated
