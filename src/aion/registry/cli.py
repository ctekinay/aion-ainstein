"""Registry CLI commands.

Provides list, merge, stats, and near-duplicate detection for the Element
Registry. Wired into src/aion/cli.py as the `registry` subcommand.
"""

import typer
from rich.console import Console
from rich.table import Table

from src.aion.registry.element_registry import (
    _DB_PATH,
    backfill_dct_identifiers,
    find_near_duplicates,
    get_stats,
    init_registry_table,
    list_all,
    merge_elements,
)

app = typer.Typer(
    name="registry",
    help="Manage AInstein element registry (stable element identities).",
    add_completion=False,
)
console = Console()


def _get_db_path():
    """Return the database path, initializing tables if needed."""
    init_registry_table(_DB_PATH)
    return _DB_PATH


@app.command(name="list")
def list_elements(
    element_type: str = typer.Option(
        None, "--type", "-t", help="Filter by ArchiMate element type",
    ),
    near_dupes: bool = typer.Option(
        False, "--near-dupes", help="Show near-duplicate pairs instead",
    ),
    workspace: str = typer.Option("default", "--workspace", "-w"),
):
    """List registry entries, or near-duplicate pairs."""
    db = _get_db_path()

    if near_dupes:
        pairs = find_near_duplicates(workspace, db)
        if not pairs:
            console.print("[dim]No near-duplicates found.[/dim]")
            return
        table = Table(title=f"Near-Duplicate Pairs ({len(pairs)})")
        table.add_column("Element A", style="cyan")
        table.add_column("Element B", style="yellow")
        table.add_column("Type", style="green")
        table.add_column("Distance", style="red", justify="right")
        for a, b, dist in pairs:
            table.add_row(
                a["display_name"], b["display_name"],
                a["element_type"], str(dist),
            )
        console.print(table)
        return

    entries = list_all(element_type, workspace, db)
    if not entries:
        console.print("[dim]No registry entries found.[/dim]")
        return

    table = Table(title=f"Element Registry ({len(entries)} entries)")
    table.add_column("ID", style="cyan", max_width=20)
    table.add_column("Type", style="green")
    table.add_column("Name", style="white")
    table.add_column("Sources", style="yellow")
    table.add_column("Gen#", justify="right", style="magenta")
    table.add_column("Last Used", style="dim")

    for e in entries:
        short_id = e["canonical_id"][:16] + "..."
        refs = ", ".join(e.get("source_doc_refs", []))
        table.add_row(
            short_id, e["element_type"], e["display_name"],
            refs or "-", str(e["generation_count"]),
            e["last_used_at"][:10],
        )

    console.print(table)


@app.command()
def merge(
    survivor_id: str = typer.Argument(..., help="Canonical ID of the element to keep"),
    absorbed_id: str = typer.Argument(..., help="Canonical ID of the element to merge in"),
):
    """Merge absorbed element into survivor (union refs, delete absorbed)."""
    db = _get_db_path()
    try:
        merge_elements(survivor_id, absorbed_id, db)
        console.print(f"[green]Merged {absorbed_id} into {survivor_id}[/green]")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def stats(
    workspace: str = typer.Option("default", "--workspace", "-w"),
):
    """Show registry statistics: total, by-type, near-duplicates."""
    db = _get_db_path()
    s = get_stats(workspace, db)

    console.print("\n[bold]Element Registry Stats[/bold]")
    console.print(f"  Total elements: {s['total']}")
    console.print(f"  Near-duplicates: {s['near_duplicates']}")

    if s["by_type"]:
        table = Table(title="By Type")
        table.add_column("Type", style="green")
        table.add_column("Count", justify="right", style="cyan")
        for t, c in sorted(s["by_type"].items()):
            table.add_row(t, str(c))
        console.print(table)


@app.command()
def backfill(
    workspace: str = typer.Option("default", "--workspace", "-w"),
):
    """Backfill dct_identifier for registry entries using current Weaviate data.

    One-time operation after re-ingestion. Matches registry entries by
    source_doc_refs overlap with Weaviate source documents.
    """
    db = _get_db_path()

    console.print("[dim]Building source metadata from Weaviate...[/dim]")
    try:
        from src.aion.generation import GenerationPipeline

        pipeline = GenerationPipeline.__new__(GenerationPipeline)
        sources = pipeline._fetch_pcps(list(range(10, 50)))
        sources.extend(pipeline._fetch_adrs(list(range(0, 40))))
        source_metadata = GenerationPipeline._build_source_metadata(sources)
    except Exception as e:
        console.print(f"[red]Failed to build source metadata: {e}[/red]")
        raise typer.Exit(code=1)

    count = backfill_dct_identifiers(source_metadata, workspace, db)
    console.print(f"[green]Backfilled {count} registry entries.[/green]")
