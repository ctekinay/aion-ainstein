"""Capability gap storage — lightweight SQLite CRUD.

Extracted from chat_ui.py so tests and tools can import without
pulling in FastAPI, Weaviate, and the full dependency chain.
"""

import sqlite3
import uuid
from datetime import datetime

from aion.config import settings

_db_path = settings.db_path


def save_capability_gap(conversation_id: str | None, agent: str, description: str) -> str:
    """Log a capability gap request from an agent."""
    gap_id = str(uuid.uuid4())
    conn = sqlite3.connect(_db_path)
    conn.execute(
        "INSERT INTO capability_gaps (id, conversation_id, agent, description, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (gap_id, conversation_id, agent, description, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return gap_id


def get_capability_gaps(limit: int = 100) -> list[dict]:
    """Retrieve logged capability gaps, most recent first."""
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM capability_gaps ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
