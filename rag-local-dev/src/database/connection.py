"""
Database connection management for PostgreSQL + pgvector.
"""

import os
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.extras import RealDictCursor
from pgvector.psycopg2 import register_vector


class DatabaseConnection:
    """Database connection manager with pgvector support."""

    def __init__(self, config: dict):
        self.config = config
        self._conn = None

    @property
    def connection_params(self) -> dict:
        """Get connection parameters from config."""
        db_config = self.config.get("database", {})
        return {
            "host": db_config.get("host", "localhost"),
            "port": db_config.get("port", 5432),
            "dbname": db_config.get("name", "rag_dev"),
            "user": db_config.get("user", "rag_user"),
            "password": os.environ.get("RAG_DB_PASSWORD", db_config.get("password", "")),
        }

    def connect(self) -> psycopg2.extensions.connection:
        """Create a new database connection with pgvector support."""
        conn = psycopg2.connect(**self.connection_params)
        register_vector(conn)
        return conn

    def get_connection(self) -> psycopg2.extensions.connection:
        """Get or create a database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = self.connect()
        return self._conn

    def close(self):
        """Close the database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None

    @contextmanager
    def cursor(self, dict_cursor: bool = True) -> Generator:
        """Context manager for database cursors."""
        conn = self.get_connection()
        cursor_factory = RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    @contextmanager
    def transaction(self) -> Generator:
        """Context manager for transactions."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_db_connection(config: dict) -> psycopg2.extensions.connection:
    """Get a database connection with pgvector registered."""
    db_config = config.get("database", {})
    conn = psycopg2.connect(
        host=db_config.get("host", "localhost"),
        port=db_config.get("port", 5432),
        dbname=db_config.get("name", "rag_dev"),
        user=db_config.get("user", "rag_user"),
        password=os.environ.get("RAG_DB_PASSWORD", db_config.get("password", "")),
    )
    register_vector(conn)
    return conn
