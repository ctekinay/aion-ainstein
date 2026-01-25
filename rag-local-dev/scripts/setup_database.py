#!/usr/bin/env python3
"""
Database setup script.
Creates extensions and schema if not using docker-entrypoint.
Useful for manual setup or schema updates.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
import yaml
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_connection(config, database="postgres"):
    """Connect to database. Use 'postgres' db for initial setup."""
    db_config = config.get("database", {})
    return psycopg2.connect(
        host=db_config.get("host", "localhost"),
        port=db_config.get("port", 5432),
        dbname=database,
        user=db_config.get("user", "rag_user"),
        password=os.environ.get("RAG_DB_PASSWORD", db_config.get("password", "")),
    )


def create_database(config):
    """Create the RAG database if it doesn't exist."""
    conn = get_connection(config, database="postgres")
    conn.autocommit = True

    db_name = config["database"]["name"]

    with conn.cursor() as cur:
        # Check if database exists
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cur.fetchone()

        if not exists:
            logger.info(f"Creating database {db_name}...")
            cur.execute(f'CREATE DATABASE "{db_name}"')
            logger.info(f"Database {db_name} created")
        else:
            logger.info(f"Database {db_name} already exists")

    conn.close()


def setup_schema(config):
    """Create extensions and tables."""
    conn = get_connection(config, database=config["database"]["name"])

    schema_file = Path(__file__).parent.parent / "src" / "database" / "schema.sql"

    if schema_file.exists():
        logger.info("Executing schema.sql...")
        with open(schema_file) as f:
            schema_sql = f.read()

        with conn.cursor() as cur:
            cur.execute(schema_sql)

        conn.commit()
        logger.info("Schema created successfully")
    else:
        logger.error(f"Schema file not found: {schema_file}")

    conn.close()


def verify_setup(config):
    """Verify that setup completed correctly."""
    conn = get_connection(config, database=config["database"]["name"])

    with conn.cursor() as cur:
        # Check extensions
        cur.execute("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')")
        extensions = [row[0] for row in cur.fetchall()]
        logger.info(f"Installed extensions: {extensions}")

        # Check tables
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename IN ('chunks', 'terminology', 'retrieval_logs', 'document_relationships')
        """
        )
        tables = [row[0] for row in cur.fetchall()]
        logger.info(f"Created tables: {tables}")

        # Check indexes
        cur.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname = 'public'
            AND (indexname LIKE 'chunks_%' OR indexname LIKE 'terminology_%')
        """
        )
        indexes = [row[0] for row in cur.fetchall()]
        logger.info(f"Created indexes: {len(indexes)} indexes")

    conn.close()

    # Verify all required components
    required_extensions = {"vector", "pg_trgm"}
    required_tables = {"chunks", "terminology", "retrieval_logs"}

    if required_extensions.issubset(set(extensions)) and required_tables.issubset(set(tables)):
        logger.info("✓ Database setup verified successfully")
        return True
    else:
        logger.error("✗ Database setup incomplete")
        if not required_extensions.issubset(set(extensions)):
            missing = required_extensions - set(extensions)
            logger.error(f"  Missing extensions: {missing}")
        if not required_tables.issubset(set(tables)):
            missing = required_tables - set(tables)
            logger.error(f"  Missing tables: {missing}")
        return False


def main():
    """Main entry point."""
    config = load_config()

    logger.info("Setting up RAG database...")

    # Create database
    create_database(config)

    # Create schema
    setup_schema(config)

    # Verify
    success = verify_setup(config)

    if success:
        logger.info("Database setup complete!")
    else:
        logger.error("Database setup failed. Check logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
