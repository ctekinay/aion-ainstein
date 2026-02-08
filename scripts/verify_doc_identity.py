#!/usr/bin/env python3
"""
Verification script for document identity invariants.

This script proves:
1. Invariant A: Every chunk has adr_number and source_path
2. Invariant B: unique(adr_number) == expected document count
3. Coverage: 100% of chunks have identity fields
4. Presence: Specific ADRs (0030, 0031) are present

Usage:
    python scripts/verify_doc_identity.py
"""

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.weaviate.client import get_weaviate_client
from weaviate.classes.query import Filter

console = Console()


def verify_adr_collection(client) -> dict:
    """Verify ADR collection document identity invariants.

    Returns dict with verification results.
    """
    console.print(Panel("[bold]ADR Document Identity Verification[/bold]"))

    collection = client.collections.get("ArchitecturalDecision")

    # Get ALL objects with doc_type="adr" using pagination
    adr_filter = Filter.by_property("doc_type").equal("adr")

    all_adr_objects = []
    offset = 0
    limit = 100

    while True:
        results = collection.query.fetch_objects(
            filters=adr_filter,
            return_properties=["adr_number", "file_path", "title", "doc_type"],
            limit=limit,
            offset=offset,
        )

        if not results.objects:
            break

        all_adr_objects.extend(results.objects)
        offset += limit

    console.print(f"\n[bold]1. Chunk Count[/bold]")
    console.print(f"   count(doc_type='adr') = {len(all_adr_objects)}")

    # Analyze identity fields
    adr_numbers = []
    file_paths = []
    missing_adr_number = []
    missing_file_path = []
    chunks_by_adr = defaultdict(list)

    for obj in all_adr_objects:
        adr_num = obj.properties.get("adr_number", "")
        file_path = obj.properties.get("file_path", "")
        title = obj.properties.get("title", "")

        if adr_num:
            adr_numbers.append(adr_num)
            chunks_by_adr[adr_num].append({
                "title": title,
                "file_path": file_path,
                "uuid": str(obj.uuid)[:8],
            })
        else:
            missing_adr_number.append({
                "title": title,
                "file_path": file_path,
            })

        if file_path:
            file_paths.append(file_path)
        else:
            missing_file_path.append({
                "title": title,
                "adr_number": adr_num,
            })

    unique_adr_numbers = sorted(set(adr_numbers))
    unique_file_paths = sorted(set(file_paths))

    console.print(f"\n[bold]2. Unique Documents[/bold]")
    console.print(f"   unique(adr_number) = {len(unique_adr_numbers)}")
    console.print(f"   unique(file_path) = {len(unique_file_paths)}")

    console.print(f"\n[bold]3. Coverage[/bold]")
    total = len(all_adr_objects)
    adr_num_coverage = (len(adr_numbers) / total * 100) if total > 0 else 0
    file_path_coverage = (len(file_paths) / total * 100) if total > 0 else 0
    console.print(f"   % with adr_number = {adr_num_coverage:.1f}% ({len(adr_numbers)}/{total})")
    console.print(f"   % with file_path = {file_path_coverage:.1f}% ({len(file_paths)}/{total})")

    if missing_adr_number:
        console.print(f"\n   [red]Missing adr_number ({len(missing_adr_number)}):[/red]")
        for item in missing_adr_number[:5]:
            console.print(f"     - {item['title'][:50]}... ({item['file_path']})")
        if len(missing_adr_number) > 5:
            console.print(f"     ... and {len(missing_adr_number) - 5} more")

    console.print(f"\n[bold]4. Presence Check[/bold]")
    has_0030 = "0030" in unique_adr_numbers
    has_0031 = "0031" in unique_adr_numbers
    console.print(f"   ADR.0030 present: {'[green]YES[/green]' if has_0030 else '[red]NO[/red]'}")
    console.print(f"   ADR.0031 present: {'[green]YES[/green]' if has_0031 else '[red]NO[/red]'}")

    console.print(f"\n[bold]5. ADR Numbers Found[/bold]")
    console.print(f"   {unique_adr_numbers}")

    console.print(f"\n[bold]6. Sample: Chunks per ADR (chunking verification)[/bold]")

    chunk_table = Table(title="Chunks per ADR Number")
    chunk_table.add_column("ADR Number", style="cyan")
    chunk_table.add_column("Chunk Count", justify="right")
    chunk_table.add_column("Sample Titles")

    for adr_num in sorted(chunks_by_adr.keys())[:10]:
        chunks = chunks_by_adr[adr_num]
        titles = ", ".join([c["title"][:30] for c in chunks[:3]])
        if len(chunks) > 3:
            titles += f" (+{len(chunks)-3} more)"
        chunk_table.add_row(adr_num, str(len(chunks)), titles)

    if len(chunks_by_adr) > 10:
        chunk_table.add_row("...", f"({len(chunks_by_adr)} total)", "")

    console.print(chunk_table)

    # Summary validation
    console.print(f"\n[bold]7. Validation Summary[/bold]")

    validations = [
        ("Chunk count", len(all_adr_objects) > 0, f"{len(all_adr_objects)} chunks"),
        ("Unique ADR count ~18", 15 <= len(unique_adr_numbers) <= 25, f"{len(unique_adr_numbers)} unique"),
        ("100% adr_number coverage", adr_num_coverage == 100, f"{adr_num_coverage:.1f}%"),
        ("100% file_path coverage", file_path_coverage == 100, f"{file_path_coverage:.1f}%"),
        ("ADR.0030 present", has_0030, ""),
        ("ADR.0031 present", has_0031, ""),
    ]

    all_passed = True
    for name, passed, detail in validations:
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        console.print(f"   {status} {name} {detail}")
        if not passed:
            all_passed = False

    return {
        "chunk_count": len(all_adr_objects),
        "unique_adr_count": len(unique_adr_numbers),
        "unique_file_paths": len(unique_file_paths),
        "adr_number_coverage": adr_num_coverage,
        "file_path_coverage": file_path_coverage,
        "has_0030": has_0030,
        "has_0031": has_0031,
        "adr_numbers": unique_adr_numbers,
        "chunks_by_adr": dict(chunks_by_adr),
        "all_passed": all_passed,
    }


def main():
    console.print(Panel("[bold]Document Identity Invariant Verification[/bold]"))

    try:
        client = get_weaviate_client()
        console.print("[green]✓[/green] Connected to Weaviate\n")
    except Exception as e:
        console.print(f"[red]Failed to connect: {e}[/red]")
        sys.exit(1)

    try:
        results = verify_adr_collection(client)

        console.print("\n" + "="*60)
        if results["all_passed"]:
            console.print("[bold green]ALL INVARIANTS VERIFIED[/bold green]")
            console.print(f"  {results['chunk_count']} chunks represent {results['unique_adr_count']} unique ADR documents")
        else:
            console.print("[bold red]INVARIANT VIOLATIONS DETECTED[/bold red]")
            console.print("  Fix the issues above before proceeding")
            sys.exit(1)

    finally:
        client.close()


if __name__ == "__main__":
    main()
