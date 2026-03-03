"""SQLite session and user profile operations.

Uses the same chat_history.db as chat_ui.py — one database, no
coordination issues. Adds two tables: sessions and user_profiles.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Same database as chat_ui.py
_DB_PATH = Path(__file__).parent.parent.parent.parent / "chat_history.db"


def init_memory_tables(db_path: Optional[Path] = None) -> None:
    """Create sessions and user_profiles tables if they don't exist.

    Called from chat_ui.init_db() during startup — not independently.
    """
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            running_summary TEXT DEFAULT '',
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            display_name TEXT,
            profile_block TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    logger.debug("Memory tables initialized")


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

def create_session(conversation_id: str, db_path: Optional[Path] = None) -> str:
    """Create a session record for a conversation. Returns session_id.

    session_id == conversation_id (1:1 mapping for Phase 1).
    """
    path = db_path or _DB_PATH
    session_id = conversation_id
    now = datetime.now().isoformat()

    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    # Upsert — if session already exists, leave it alone
    cursor.execute(
        "INSERT OR IGNORE INTO sessions (session_id, conversation_id, started_at) VALUES (?, ?, ?)",
        (session_id, conversation_id, now),
    )

    conn.commit()
    conn.close()
    return session_id


def get_running_summary(conversation_id: str, db_path: Optional[Path] = None) -> str:
    """Get the running summary for a conversation's session."""
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT running_summary FROM sessions WHERE conversation_id = ?",
        (conversation_id,),
    )
    row = cursor.fetchone()
    conn.close()

    return (row[0] or "") if row else ""


def update_running_summary(
    conversation_id: str, summary: str, db_path: Optional[Path] = None
) -> None:
    """Persist an updated running summary for the session."""
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE sessions SET running_summary = ? WHERE conversation_id = ?",
        (summary, conversation_id),
    )

    conn.commit()
    conn.close()


def end_session(conversation_id: str, db_path: Optional[Path] = None) -> None:
    """Mark a session as ended."""
    path = db_path or _DB_PATH
    now = datetime.now().isoformat()

    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE sessions SET ended_at = ? WHERE conversation_id = ?",
        (now, conversation_id),
    )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# User profile CRUD (Phase 1: single default user)
# ---------------------------------------------------------------------------

_DEFAULT_USER = "default"


def get_user_profile(user_id: str = _DEFAULT_USER, db_path: Optional[Path] = None) -> dict:
    """Get a user profile. Returns empty dict if not found."""
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT user_id, display_name, profile_block, created_at, updated_at "
        "FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {}

    return {
        "user_id": row[0],
        "display_name": row[1] or "",
        "profile_block": row[2] or "",
        "created_at": row[3],
        "updated_at": row[4],
    }


def upsert_user_profile(
    display_name: str = "",
    profile_block: str = "",
    user_id: str = _DEFAULT_USER,
    db_path: Optional[Path] = None,
) -> None:
    """Create or update a user profile."""
    path = db_path or _DB_PATH
    now = datetime.now().isoformat()

    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute(
        """INSERT INTO user_profiles (user_id, display_name, profile_block, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             display_name = COALESCE(NULLIF(excluded.display_name, ''), user_profiles.display_name),
             profile_block = excluded.profile_block,
             updated_at = excluded.updated_at""",
        (user_id, display_name, profile_block, now, now),
    )

    conn.commit()
    conn.close()
