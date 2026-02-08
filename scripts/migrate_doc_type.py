#!/usr/bin/env python3
"""
Migration script to backfill doc_type in Weaviate collections.

Phase 3 of enterprise-grade ADR filtering implementation.

This script:
1. Paginates all objects in the target Weaviate class
2. Computes doc_type via the classifier
3. Batch updates objects with computed doc_type
4. Prints summary table (counts per type, null before/after)

Usage:
    python scripts/migrate_doc_type.py --collection ArchitecturalDecision
    python scripts/migrate_doc_type.py --collection Principle
    python scripts/migrate_doc_type.py --all
    python scripts/migrate_doc_type.py --dry-run --collection ArchitecturalDecision

Environment:
    Requires Weaviate connection (uses settings from src/config.py)
"""

import argparse
import logging
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import UUID

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.config import settings
from src.weaviate.client import get_weaviate_client
from src.doc_type_classifier import (
    DocType,
    classify_adr_document,
    classify_principle_document,
    doc_type_from_legacy,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

console = Console()

# Batch size for updates
UPDATE_BATCH_SIZE = 100


@dataclass
class MigrationStats:
    """Statistics from migration run."""
    collection: str
    total_objects: int
    null_before: int
    null_after: int
    updated: int
    skipped: int
    errors: int
    type_counts: Counter


def get_collection_type(collection_name: str) -> str:
    """Map collection name to collection type for classifier."""
    mapping = {
        "ArchitecturalDecision": "adr",
        "ArchitecturalDecision_OpenAI": "adr",
        "Principle": "principle",
        "Principle_OpenAI": "principle",
    }
    return mapping.get(collection_name, "unknown")


def migrate_collection(
    client,
    collection_name: str,
    dry_run: bool = False,
) -> MigrationStats:
    """Migrate a single collection to have doc_type populated.

    Args:
        client: Weaviate client
        collection_name: Name of the collection to migrate
        dry_run: If True, don't actually update objects

    Returns:
        MigrationStats with counts and distribution
    """
    console.print(f"\n[bold blue]Migrating collection: {collection_name}[/bold blue]")

    if not client.collections.exists(collection_name):
        console.print(f"[red]Collection {collection_name} does not exist[/red]")
        return MigrationStats(
            collection=collection_name,
            total_objects=0,
            null_before=0,
            null_after=0,
            updated=0,
            skipped=0,
            errors=0,
            type_counts=Counter(),
        )

    collection = client.collections.get(collection_name)
    collection_type = get_collection_type(collection_name)

    # Get initial count
    aggregate = collection.aggregate.over_all(total_count=True)
    total_count = aggregate.total_count
    console.print(f"  Total objects: {total_count}")

    if total_count == 0:
        return MigrationStats(
            collection=collection_name,
            total_objects=0,
            null_before=0,
            null_after=0,
            updated=0,
            skipped=0,
            errors=0,
            type_counts=Counter(),
        )

    # Track statistics
    null_before = 0
    null_after = 0
    updated = 0
    skipped = 0
    errors = 0
    type_counts = Counter()
    updates_batch = []

    # Determine which properties to fetch
    if collection_type == "adr":
        return_props = ["title", "file_path", "content", "doc_type"]
    else:
        return_props = ["title", "file_path", "content", "doc_type"]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Processing {collection_name}...", total=total_count)

        # Paginate through all objects
        offset = 0
        limit = 100

        while True:
            results = collection.query.fetch_objects(
                limit=limit,
                offset=offset,
                return_properties=return_props,
                include_vector=False,
            )

            if not results.objects:
                break

            for obj in results.objects:
                props = obj.properties
                current_doc_type = props.get("doc_type")
                file_path = props.get("file_path", "")
                title = props.get("title", "")
                content = props.get("content", "")[:500]  # Limit for classification

                # Track null before migration
                if not current_doc_type:
                    null_before += 1

                # Classify the document
                if collection_type == "adr":
                    result = classify_adr_document(file_path, title, content)
                else:
                    result = classify_principle_document(file_path, title, content)

                new_doc_type = result.doc_type
                type_counts[new_doc_type] += 1

                # Check if update is needed
                # Convert legacy values to canonical before comparison
                canonical_current = doc_type_from_legacy(current_doc_type) if current_doc_type else None

                if canonical_current == new_doc_type:
                    skipped += 1
                else:
                    # Need to update
                    if not dry_run:
                        updates_batch.append({
                            "uuid": obj.uuid,
                            "doc_type": new_doc_type,
                        })

                        # Flush batch when full
                        if len(updates_batch) >= UPDATE_BATCH_SIZE:
                            try:
                                _apply_updates(collection, updates_batch)
                                updated += len(updates_batch)
                                updates_batch = []
                            except Exception as e:
                                logger.error(f"Batch update failed: {e}")
                                errors += len(updates_batch)
                                updates_batch = []
                    else:
                        updated += 1  # Count as would-be-updated in dry run

                progress.advance(task)

            offset += limit

        # Flush remaining updates
        if updates_batch and not dry_run:
            try:
                _apply_updates(collection, updates_batch)
                updated += len(updates_batch)
            except Exception as e:
                logger.error(f"Final batch update failed: {e}")
                errors += len(updates_batch)

    # Count null after migration (only if not dry run)
    if not dry_run:
        # Re-query to verify
        null_after = _count_null_doc_type(collection)
    else:
        null_after = null_before - updated

    return MigrationStats(
        collection=collection_name,
        total_objects=total_count,
        null_before=null_before,
        null_after=null_after,
        updated=updated,
        skipped=skipped,
        errors=errors,
        type_counts=type_counts,
    )


def _apply_updates(collection, updates: list[dict]) -> None:
    """Apply batch updates to collection.

    Args:
        collection: Weaviate collection
        updates: List of dicts with uuid and doc_type
    """
    for update in updates:
        try:
            collection.data.update(
                uuid=update["uuid"],
                properties={"doc_type": update["doc_type"]},
            )
        except Exception as e:
            logger.error(f"Failed to update {update['uuid']}: {e}")
            raise


def _count_null_doc_type(collection) -> int:
    """Count objects with null/missing doc_type.

    Args:
        collection: Weaviate collection

    Returns:
        Count of objects without doc_type
    """
    # Query all and count manually since Weaviate filter on null is tricky
    count = 0
    offset = 0
    limit = 100

    while True:
        results = collection.query.fetch_objects(
            limit=limit,
            offset=offset,
            return_properties=["doc_type"],
        )

        if not results.objects:
            break

        for obj in results.objects:
            if not obj.properties.get("doc_type"):
                count += 1

        offset += limit

    return count


def print_summary(stats_list: list[MigrationStats], dry_run: bool) -> None:
    """Print migration summary table.

    Args:
        stats_list: List of MigrationStats from each collection
        dry_run: Whether this was a dry run
    """
    mode = "[yellow](DRY RUN)[/yellow]" if dry_run else ""
    console.print(Panel(f"[bold]Migration Summary {mode}[/bold]"))

    # Overall stats table
    table = Table(title="Collection Stats")
    table.add_column("Collection", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Null Before", justify="right")
    table.add_column("Null After", justify="right", style="green")
    table.add_column("Updated", justify="right", style="blue")
    table.add_column("Skipped", justify="right")
    table.add_column("Errors", justify="right", style="red")

    for stats in stats_list:
        table.add_row(
            stats.collection,
            str(stats.total_objects),
            str(stats.null_before),
            str(stats.null_after),
            str(stats.updated),
            str(stats.skipped),
            str(stats.errors),
        )

    console.print(table)

    # Type distribution tables
    for stats in stats_list:
        if stats.type_counts:
            type_table = Table(title=f"\n{stats.collection} - doc_type Distribution")
            type_table.add_column("doc_type", style="cyan")
            type_table.add_column("Count", justify="right")
            type_table.add_column("Percentage", justify="right")

            total = sum(stats.type_counts.values())
            for doc_type, count in sorted(stats.type_counts.items()):
                pct = (count / total * 100) if total > 0 else 0
                type_table.add_row(doc_type, str(count), f"{pct:.1f}%")

            console.print(type_table)

    # Validation checks
    console.print("\n[bold]Validation Checks:[/bold]")

    for stats in stats_list:
        if "ArchitecturalDecision" in stats.collection:
            adr_count = stats.type_counts.get(DocType.ADR, 0)

            # Check for expected ADR count (should be ~18)
            if 15 <= adr_count <= 25:
                console.print(f"  [green]✓[/green] {stats.collection}: {adr_count} ADRs (expected ~18)")
            else:
                console.print(f"  [yellow]![/yellow] {stats.collection}: {adr_count} ADRs (expected ~18)")

            # Check null count
            if stats.null_after == 0:
                console.print(f"  [green]✓[/green] {stats.collection}: No null doc_type remaining")
            else:
                console.print(f"  [red]✗[/red] {stats.collection}: {stats.null_after} null doc_type remaining")


def main():
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate doc_type in Weaviate collections"
    )
    parser.add_argument(
        "--collection",
        type=str,
        help="Collection name to migrate (e.g., ArchitecturalDecision, Principle)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Migrate all supported collections"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making updates"
    )
    parser.add_argument(
        "--include-openai",
        action="store_true",
        help="Also migrate OpenAI collections"
    )

    args = parser.parse_args()

    if not args.collection and not args.all:
        parser.error("Either --collection or --all must be specified")

    # Connect to Weaviate
    console.print(Panel("[bold]doc_type Migration Script[/bold]"))
    console.print(f"Weaviate URL: {settings.weaviate_url}")

    if args.dry_run:
        console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")

    try:
        client = get_weaviate_client()
        console.print("[green]✓[/green] Connected to Weaviate")
    except Exception as e:
        console.print(f"[red]Failed to connect to Weaviate: {e}[/red]")
        sys.exit(1)

    try:
        # Determine which collections to migrate
        collections = []
        if args.all:
            collections = ["ArchitecturalDecision", "Principle"]
            if args.include_openai:
                collections.extend([
                    "ArchitecturalDecision_OpenAI",
                    "Principle_OpenAI",
                ])
        else:
            collections = [args.collection]

        # Run migrations
        stats_list = []
        for collection_name in collections:
            stats = migrate_collection(
                client,
                collection_name,
                dry_run=args.dry_run,
            )
            stats_list.append(stats)

        # Print summary
        print_summary(stats_list, args.dry_run)

        # Exit with error if any errors occurred
        total_errors = sum(s.errors for s in stats_list)
        if total_errors > 0:
            console.print(f"\n[red]Migration completed with {total_errors} errors[/red]")
            sys.exit(1)
        else:
            console.print("\n[green]✓ Migration completed successfully[/green]")

    finally:
        client.close()


if __name__ == "__main__":
    main()
