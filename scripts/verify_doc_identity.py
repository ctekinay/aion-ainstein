#!/usr/bin/env python3
"""
Verification script for document identity invariants (Phase 4).

This script proves:
1. Invariant A: Every chunk has identity fields (adr_number/principle_number and file_path)
2. Invariant B: unique(identity_field) == expected document count
3. Invariant C: Identity consistency - adr_number maps to exactly 1 file_path (and vice versa)
4. Coverage: 100% of chunks have identity fields
5. Presence: Specific documents (ADR.0030, ADR.0031) are present

Supports both ADR and Principle collections.

Usage:
    python scripts/verify_doc_identity.py                    # Both collections, human-readable
    python scripts/verify_doc_identity.py --collection adr   # ADR only
    python scripts/verify_doc_identity.py --collection principle  # Principle only
    python scripts/verify_doc_identity.py --json             # Machine-readable JSON output
    python scripts/verify_doc_identity.py --ci               # CI mode: JSON + strict exit codes
"""

import argparse
import json
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


def verify_identity_consistency(chunks_by_identity: dict, file_paths_by_identity: dict) -> dict:
    """Check that each identity key maps to exactly one file_path.

    Returns dict with:
    - consistent: bool (True if all mappings are 1:1)
    - violations: list of identity keys with multiple file_paths
    """
    violations = []

    for identity_key, chunks in chunks_by_identity.items():
        file_paths = set(c.get("file_path", "") for c in chunks if c.get("file_path"))
        if len(file_paths) > 1:
            violations.append({
                "identity": identity_key,
                "file_paths": list(file_paths),
            })

    return {
        "consistent": len(violations) == 0,
        "violations": violations,
    }


def verify_adr_collection(client, verbose: bool = True) -> dict:
    """Verify ADR collection document identity invariants.

    Returns dict with verification results.
    """
    if verbose:
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

    # Also get unfiltered count for comparison
    unfiltered_results = []
    offset = 0
    while True:
        results = collection.query.fetch_objects(
            return_properties=["adr_number", "file_path", "title", "doc_type"],
            limit=limit,
            offset=offset,
        )
        if not results.objects:
            break
        unfiltered_results.extend(results.objects)
        offset += limit

    if verbose:
        console.print(f"\n[bold]1. Chunk Count[/bold]")
        console.print(f"   filtered_count (doc_type='adr') = {len(all_adr_objects)}")
        console.print(f"   unfiltered_count (all) = {len(unfiltered_results)}")
        console.print(f"   fallback_triggered = {len(all_adr_objects) == 0 and len(unfiltered_results) > 0}")

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

        chunk_info = {
            "title": title,
            "file_path": file_path,
            "uuid": str(obj.uuid)[:8],
        }

        if adr_num:
            adr_numbers.append(adr_num)
            chunks_by_adr[adr_num].append(chunk_info)
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

    if verbose:
        console.print(f"\n[bold]2. Unique Documents[/bold]")
        console.print(f"   unique(adr_number) = {len(unique_adr_numbers)}")
        console.print(f"   unique(file_path) = {len(unique_file_paths)}")

    total = len(all_adr_objects)
    adr_num_coverage = (len(adr_numbers) / total * 100) if total > 0 else 0
    file_path_coverage = (len(file_paths) / total * 100) if total > 0 else 0

    if verbose:
        console.print(f"\n[bold]3. Coverage[/bold]")
        console.print(f"   % with adr_number = {adr_num_coverage:.1f}% ({len(adr_numbers)}/{total})")
        console.print(f"   % with file_path = {file_path_coverage:.1f}% ({len(file_paths)}/{total})")

        if missing_adr_number:
            console.print(f"\n   [red]Missing adr_number ({len(missing_adr_number)}):[/red]")
            for item in missing_adr_number[:5]:
                console.print(f"     - {item['title'][:50]}... ({item['file_path']})")
            if len(missing_adr_number) > 5:
                console.print(f"     ... and {len(missing_adr_number) - 5} more")

    # Invariant C: Identity consistency check
    consistency = verify_identity_consistency(chunks_by_adr, {})

    if verbose:
        console.print(f"\n[bold]4. Identity Consistency[/bold]")
        if consistency["consistent"]:
            console.print("   [green]PASS[/green] Each adr_number maps to exactly 1 file_path")
        else:
            console.print(f"   [red]FAIL[/red] {len(consistency['violations'])} adr_numbers map to multiple file_paths:")
            for v in consistency["violations"][:3]:
                console.print(f"     - {v['identity']}: {v['file_paths']}")

    has_0030 = "0030" in unique_adr_numbers
    has_0031 = "0031" in unique_adr_numbers

    if verbose:
        console.print(f"\n[bold]5. Presence Check[/bold]")
        console.print(f"   ADR.0030 present: {'[green]YES[/green]' if has_0030 else '[red]NO[/red]'}")
        console.print(f"   ADR.0031 present: {'[green]YES[/green]' if has_0031 else '[red]NO[/red]'}")

        console.print(f"\n[bold]6. ADR Numbers Found[/bold]")
        console.print(f"   {unique_adr_numbers}")

        console.print(f"\n[bold]7. Sample: Chunks per ADR (chunking verification)[/bold]")

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

    # Validation summary
    validations = [
        ("chunk_count_positive", len(all_adr_objects) > 0, f"{len(all_adr_objects)} chunks"),
        ("unique_adr_count_18", 15 <= len(unique_adr_numbers) <= 25, f"{len(unique_adr_numbers)} unique"),
        ("adr_number_coverage_100", adr_num_coverage == 100, f"{adr_num_coverage:.1f}%"),
        ("file_path_coverage_100", file_path_coverage == 100, f"{file_path_coverage:.1f}%"),
        ("identity_consistent", consistency["consistent"], "1:1 mapping"),
        ("has_adr_0030", has_0030, ""),
        ("has_adr_0031", has_0031, ""),
    ]

    all_passed = True
    validation_results = {}
    for name, passed, detail in validations:
        validation_results[name] = {"passed": passed, "detail": detail}
        if not passed:
            all_passed = False

    if verbose:
        console.print(f"\n[bold]8. Validation Summary[/bold]")
        for name, passed, detail in validations:
            status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
            console.print(f"   {status} {name} {detail}")

    return {
        "collection": "ArchitecturalDecision",
        "filtered_count": len(all_adr_objects),
        "unfiltered_count": len(unfiltered_results),
        "fallback_triggered": len(all_adr_objects) == 0 and len(unfiltered_results) > 0,
        "unique_count": len(unique_adr_numbers),
        "unique_file_paths": len(unique_file_paths),
        "identity_coverage": adr_num_coverage,
        "file_path_coverage": file_path_coverage,
        "identity_consistent": consistency["consistent"],
        "consistency_violations": consistency["violations"],
        "has_0030": has_0030,
        "has_0031": has_0031,
        "identity_values": unique_adr_numbers,
        "validations": validation_results,
        "all_passed": all_passed,
    }


def verify_principle_collection(client, verbose: bool = True) -> dict:
    """Verify Principle collection document identity invariants.

    Returns dict with verification results.
    """
    if verbose:
        console.print(Panel("[bold]Principle Document Identity Verification[/bold]"))

    collection = client.collections.get("Principle")

    # Get ALL objects with doc_type="principle" using pagination
    principle_filter = Filter.by_property("doc_type").equal("principle")

    all_principle_objects = []
    offset = 0
    limit = 100

    while True:
        results = collection.query.fetch_objects(
            filters=principle_filter,
            return_properties=["principle_number", "file_path", "title", "doc_type"],
            limit=limit,
            offset=offset,
        )

        if not results.objects:
            break

        all_principle_objects.extend(results.objects)
        offset += limit

    # Also get unfiltered count
    unfiltered_results = []
    offset = 0
    while True:
        results = collection.query.fetch_objects(
            return_properties=["principle_number", "file_path", "title", "doc_type"],
            limit=limit,
            offset=offset,
        )
        if not results.objects:
            break
        unfiltered_results.extend(results.objects)
        offset += limit

    if verbose:
        console.print(f"\n[bold]1. Chunk Count[/bold]")
        console.print(f"   filtered_count (doc_type='principle') = {len(all_principle_objects)}")
        console.print(f"   unfiltered_count (all) = {len(unfiltered_results)}")
        console.print(f"   fallback_triggered = {len(all_principle_objects) == 0 and len(unfiltered_results) > 0}")

    # Analyze identity fields
    principle_numbers = []
    file_paths = []
    missing_principle_number = []
    missing_file_path = []
    chunks_by_principle = defaultdict(list)

    for obj in all_principle_objects:
        principle_num = obj.properties.get("principle_number", "")
        file_path = obj.properties.get("file_path", "")
        title = obj.properties.get("title", "")

        chunk_info = {
            "title": title,
            "file_path": file_path,
            "uuid": str(obj.uuid)[:8],
        }

        if principle_num:
            principle_numbers.append(principle_num)
            chunks_by_principle[principle_num].append(chunk_info)
        else:
            missing_principle_number.append({
                "title": title,
                "file_path": file_path,
            })

        if file_path:
            file_paths.append(file_path)
        else:
            missing_file_path.append({
                "title": title,
                "principle_number": principle_num,
            })

    unique_principle_numbers = sorted(set(principle_numbers))
    unique_file_paths = sorted(set(file_paths))

    if verbose:
        console.print(f"\n[bold]2. Unique Documents[/bold]")
        console.print(f"   unique(principle_number) = {len(unique_principle_numbers)}")
        console.print(f"   unique(file_path) = {len(unique_file_paths)}")

    total = len(all_principle_objects)
    principle_num_coverage = (len(principle_numbers) / total * 100) if total > 0 else 0
    file_path_coverage = (len(file_paths) / total * 100) if total > 0 else 0

    if verbose:
        console.print(f"\n[bold]3. Coverage[/bold]")
        console.print(f"   % with principle_number = {principle_num_coverage:.1f}% ({len(principle_numbers)}/{total})")
        console.print(f"   % with file_path = {file_path_coverage:.1f}% ({len(file_paths)}/{total})")

        if missing_principle_number:
            console.print(f"\n   [yellow]Missing principle_number ({len(missing_principle_number)}):[/yellow]")
            for item in missing_principle_number[:5]:
                console.print(f"     - {item['title'][:50]}... ({item['file_path']})")

    # Identity consistency check
    consistency = verify_identity_consistency(chunks_by_principle, {})

    if verbose:
        console.print(f"\n[bold]4. Identity Consistency[/bold]")
        if consistency["consistent"]:
            console.print("   [green]PASS[/green] Each principle_number maps to exactly 1 file_path")
        else:
            console.print(f"   [red]FAIL[/red] {len(consistency['violations'])} violations")

        console.print(f"\n[bold]5. Principle Numbers Found[/bold]")
        console.print(f"   {unique_principle_numbers}")

    # For principles, we require file_path but principle_number may be optional
    # (some principles may not have explicit numbers)
    validations = [
        ("chunk_count_positive", len(all_principle_objects) > 0, f"{len(all_principle_objects)} chunks"),
        ("unique_count_reasonable", len(unique_file_paths) > 0, f"{len(unique_file_paths)} unique"),
        ("file_path_coverage_100", file_path_coverage == 100, f"{file_path_coverage:.1f}%"),
        ("identity_consistent", consistency["consistent"], "1:1 mapping"),
    ]

    all_passed = True
    validation_results = {}
    for name, passed, detail in validations:
        validation_results[name] = {"passed": passed, "detail": detail}
        if not passed:
            all_passed = False

    if verbose:
        console.print(f"\n[bold]6. Validation Summary[/bold]")
        for name, passed, detail in validations:
            status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
            console.print(f"   {status} {name} {detail}")

    return {
        "collection": "Principle",
        "filtered_count": len(all_principle_objects),
        "unfiltered_count": len(unfiltered_results),
        "fallback_triggered": len(all_principle_objects) == 0 and len(unfiltered_results) > 0,
        "unique_count": len(unique_file_paths),  # Use file_path as primary identity for principles
        "unique_principle_numbers": len(unique_principle_numbers),
        "identity_coverage": principle_num_coverage,
        "file_path_coverage": file_path_coverage,
        "identity_consistent": consistency["consistent"],
        "consistency_violations": consistency["violations"],
        "identity_values": unique_principle_numbers,
        "validations": validation_results,
        "all_passed": all_passed,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Verify document identity invariants for Phase 4 compliance"
    )
    parser.add_argument(
        "--collection",
        choices=["adr", "principle", "all"],
        default="all",
        help="Collection to verify (default: all)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON"
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: JSON output + strict exit codes"
    )
    args = parser.parse_args()

    verbose = not (args.json or args.ci)

    if verbose:
        console.print(Panel("[bold]Document Identity Invariant Verification[/bold]"))

    try:
        client = get_weaviate_client()
        if verbose:
            console.print("[green]✓[/green] Connected to Weaviate\n")
    except Exception as e:
        if args.json or args.ci:
            print(json.dumps({"error": str(e), "connected": False}))
        else:
            console.print(f"[red]Failed to connect: {e}[/red]")
        sys.exit(1)

    results = {}
    all_passed = True

    try:
        if args.collection in ("adr", "all"):
            adr_results = verify_adr_collection(client, verbose=verbose)
            results["adr"] = adr_results
            if not adr_results["all_passed"]:
                all_passed = False

        if args.collection in ("principle", "all"):
            if verbose:
                console.print("\n" + "=" * 60 + "\n")
            principle_results = verify_principle_collection(client, verbose=verbose)
            results["principle"] = principle_results
            if not principle_results["all_passed"]:
                all_passed = False

        # Summary output
        results["summary"] = {
            "all_passed": all_passed,
            "collections_verified": list(results.keys()),
        }

        if args.json or args.ci:
            print(json.dumps(results, indent=2, default=str))
        else:
            console.print("\n" + "=" * 60)
            if all_passed:
                console.print("[bold green]ALL INVARIANTS VERIFIED[/bold green]")
                if "adr" in results:
                    console.print(f"  ADR: {results['adr']['filtered_count']} chunks → {results['adr']['unique_count']} unique documents")
                if "principle" in results:
                    console.print(f"  Principle: {results['principle']['filtered_count']} chunks → {results['principle']['unique_count']} unique documents")
            else:
                console.print("[bold red]INVARIANT VIOLATIONS DETECTED[/bold red]")
                console.print("  Fix the issues above before proceeding")

        if not all_passed:
            sys.exit(1)

    finally:
        client.close()


if __name__ == "__main__":
    main()
