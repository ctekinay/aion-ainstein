"""Memory management CLI commands.

Provides reset, show, and profile management for testing and debugging.
Wired into src/aion/cli.py as the `memory` subcommand.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.aion.memory.session_store import (
    _DB_PATH,
    init_memory_tables,
    get_running_summary,
    get_user_profile,
    upsert_user_profile,
)

app = typer.Typer(
    name="memory",
    help="Manage AInstein session memory and user profiles.",
    add_completion=False,
)
console = Console()


def _get_db_path() -> Path:
    """Return the database path, initializing tables if needed."""
    init_memory_tables(_DB_PATH)
    return _DB_PATH


@app.command()
def show():
    """Show current memory state: sessions, summaries, and user profile."""
    db = _get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Sessions
    cursor.execute(
        "SELECT session_id, conversation_id, started_at, ended_at, "
        "LENGTH(running_summary) as summary_len, running_summary "
        "FROM sessions ORDER BY started_at DESC"
    )
    sessions = cursor.fetchall()

    if sessions:
        table = Table(title="Sessions")
        table.add_column("Session ID", style="cyan", max_width=20)
        table.add_column("Started", style="green")
        table.add_column("Ended", style="yellow")
        table.add_column("Summary", style="white", max_width=60)

        for row in sessions:
            session_id = row[0][:16] + "..." if len(row[0]) > 16 else row[0]
            started = row[2] or ""
            ended = row[3] or "[dim]active[/dim]"
            summary_len = row[4] or 0
            summary_text = row[5] or ""
            # Show first 80 chars of summary
            summary_preview = (
                f"({summary_len} chars) {summary_text[:80]}..."
                if summary_len > 80
                else summary_text or "[dim]empty[/dim]"
            )
            table.add_row(session_id, started, ended, summary_preview)

        console.print(table)
    else:
        console.print("[dim]No sessions found.[/dim]")

    # User profile
    profile = get_user_profile(db_path=db)
    if profile:
        console.print(Panel(
            f"Name: {profile.get('display_name') or '[dim]not set[/dim]'}\n"
            f"Profile: {profile.get('profile_block') or '[dim]empty[/dim]'}\n"
            f"Updated: {profile.get('updated_at', 'N/A')}",
            title="User Profile",
            style="blue",
        ))
    else:
        console.print("[dim]No user profile found.[/dim]")

    # Message count
    cursor.execute("SELECT COUNT(*) FROM messages")
    msg_count = cursor.fetchone()[0]
    console.print(f"\n[dim]Total messages in database: {msg_count}[/dim]")
    console.print(f"[dim]Database: {db}[/dim]")

    conn.close()


@app.command()
def reset(
    keep_messages: bool = typer.Option(
        False, "--keep-messages", "-k",
        help="Keep messages but clear sessions and summaries",
    ),
):
    """Wipe all sessions and summaries. Optionally keep message history."""
    db = _get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM sessions")
    session_count = cursor.rowcount

    if not keep_messages:
        cursor.execute("DELETE FROM messages")
        msg_count = cursor.rowcount
        cursor.execute("DELETE FROM conversations")
        conv_count = cursor.rowcount
        conn.commit()
        conn.close()
        console.print(
            f"[green]Reset complete:[/green] {session_count} sessions, "
            f"{conv_count} conversations, {msg_count} messages deleted."
        )
    else:
        conn.commit()
        conn.close()
        console.print(
            f"[green]Reset complete:[/green] {session_count} sessions cleared. "
            "Messages and conversations preserved."
        )


@app.command(name="reset-profile")
def reset_profile():
    """Wipe all user profiles."""
    db = _get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM user_profiles")
    count = cursor.rowcount

    conn.commit()
    conn.close()

    console.print(f"[green]Profile reset:[/green] {count} profile(s) deleted.")


@app.command()
def export():
    """Export current memory state as JSON for debugging."""
    db = _get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Sessions
    cursor.execute(
        "SELECT session_id, conversation_id, started_at, ended_at, running_summary "
        "FROM sessions ORDER BY started_at DESC"
    )
    sessions = [
        {
            "session_id": r[0],
            "conversation_id": r[1],
            "started_at": r[2],
            "ended_at": r[3],
            "running_summary": r[4],
        }
        for r in cursor.fetchall()
    ]

    # Profile
    profile = get_user_profile(db_path=db)

    # Recent messages (last 20)
    cursor.execute(
        "SELECT conversation_id, role, turn_summary, timestamp "
        "FROM messages ORDER BY timestamp DESC LIMIT 20"
    )
    recent_messages = [
        {
            "conversation_id": r[0],
            "role": r[1],
            "turn_summary": r[2],
            "timestamp": r[3],
        }
        for r in cursor.fetchall()
    ]

    conn.close()

    state = {
        "sessions": sessions,
        "user_profile": profile,
        "recent_messages": recent_messages,
    }

    console.print(json.dumps(state, indent=2))
