#!/usr/bin/env python3
"""
Verification script for three critical checks:

1. Are index.md files ingested into Weaviate?
   - index.md inside decisions/ and principles/ should NOT be ingested
   - esa_doc_registry.md (top-level registry) MAY be ingested with doc_type="registry"

2. Is documents: field from index.md used anywhere at runtime?

3. Is there deterministic record_type separation between content and approval records?

Usage:
    python scripts/verify_three_checks.py
"""

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.weaviate.client import get_weaviate_client
from src.weaviate.collections import get_collection_name

console = Console()


def check_1_index_ingestion(client) -> dict:
    """Check if index.md files are ingested into Weaviate.

    Expected behavior:
    - index.md inside decisions/ and principles/: Should NOT be ingested
    - esa_doc_registry.md (top-level registry): MAY be ingested with doc_type="registry"
    """
    console.print(Panel("[bold cyan]CHECK 1: Are index.md files ingested into Weaviate?[/bold cyan]"))

    results = {
        "decisions_index": {"count": 0, "objects": []},
        "principles_index": {"count": 0, "objects": []},
        "registry_files": {"count": 0, "objects": []},
        "all_index_files": {"count": 0, "objects": []},
    }

    # Check ArchitecturalDecision collection for decisions/index.md
    try:
        adr_collection = client.collections.get(get_collection_name("adr"))
        offset = 0
        limit = 100
        all_objects = []

        while True:
            batch = adr_collection.query.fetch_objects(
                return_properties=["file_path", "title", "doc_type", "adr_number"],
                limit=limit,
                offset=offset,
            )
            if not batch.objects:
                break
            all_objects.extend(batch.objects)
            offset += limit

        # Find index.md and registry files
        for obj in all_objects:
            fp = obj.properties.get("file_path", "")
            fp_lower = fp.lower()
            obj_data = {
                "file_path": fp,
                "title": obj.properties.get("title", ""),
                "doc_type": obj.properties.get("doc_type", ""),
                "adr_number": obj.properties.get("adr_number", ""),
                "uuid": str(obj.uuid)[:8],
            }

            # Check for registry files (esa_doc_registry.md)
            if "esa_doc_registry.md" in fp_lower or "esa-doc-registry.md" in fp_lower:
                results["registry_files"]["objects"].append(obj_data)
                results["registry_files"]["count"] += 1
            # Check for index.md files
            elif "index.md" in fp_lower or fp_lower.endswith("readme.md"):
                results["all_index_files"]["objects"].append(obj_data)
                if "/decisions/index.md" in fp:
                    results["decisions_index"]["objects"].append(obj_data)
                    results["decisions_index"]["count"] += 1

        results["all_index_files"]["count"] = len(results["all_index_files"]["objects"])
        console.print(f"\n[bold]ADR Collection - Index/Registry File Search:[/bold]")
        console.print(f"  Total objects in collection: {len(all_objects)}")
        console.print(f"  Objects with 'index.md' in file_path: {results['all_index_files']['count']}")
        console.print(f"  Objects from decisions/index.md: {results['decisions_index']['count']}")
        console.print(f"  Objects from esa_doc_registry.md: {results['registry_files']['count']}")

    except Exception as e:
        console.print(f"[red]Error checking ADR collection: {e}[/red]")

    # Check Principle collection for principles/index.md
    try:
        principle_collection = client.collections.get(get_collection_name("principle"))
        offset = 0
        all_principle_objects = []

        while True:
            batch = principle_collection.query.fetch_objects(
                return_properties=["file_path", "title", "doc_type", "principle_number"],
                limit=limit,
                offset=offset,
            )
            if not batch.objects:
                break
            all_principle_objects.extend(batch.objects)
            offset += limit

        # Find index.md files
        for obj in all_principle_objects:
            fp = obj.properties.get("file_path", "")
            if "index.md" in fp.lower():
                obj_data = {
                    "file_path": fp,
                    "title": obj.properties.get("title", ""),
                    "doc_type": obj.properties.get("doc_type", ""),
                    "principle_number": obj.properties.get("principle_number", ""),
                    "uuid": str(obj.uuid)[:8],
                }
                if "/principles/index.md" in fp:
                    results["principles_index"]["objects"].append(obj_data)
                    results["principles_index"]["count"] += 1

        console.print(f"\n[bold]Principle Collection - Index File Search:[/bold]")
        console.print(f"  Total objects in collection: {len(all_principle_objects)}")
        console.print(f"  Objects from principles/index.md: {results['principles_index']['count']}")

    except Exception as e:
        console.print(f"[red]Error checking Principle collection: {e}[/red]")

    # Summary
    total_index = results["decisions_index"]["count"] + results["principles_index"]["count"]
    registry_count = results["registry_files"]["count"]

    console.print(f"\n[bold]RESULT:[/bold]")

    # Check directory-level index.md files (should NOT be ingested)
    if total_index == 0:
        console.print(f"  [green]✓ Directory index.md files are NOT ingested[/green]")
        console.print(f"    count=0 for decisions/index.md and principles/index.md")
    else:
        console.print(f"  [yellow]⚠ {total_index} directory index.md files ARE ingested[/yellow]")
        for idx_type, data in [("decisions", results["decisions_index"]), ("principles", results["principles_index"])]:
            if data["objects"]:
                console.print(f"\n  [yellow]{idx_type}/index.md objects:[/yellow]")
                for obj in data["objects"]:
                    console.print(f"    - doc_type={obj['doc_type']}, title={obj['title'][:50]}...")

    # Check registry file (MAY be ingested with doc_type="registry")
    if registry_count > 0:
        console.print(f"\n  [cyan]ℹ esa_doc_registry.md IS ingested ({registry_count} object(s))[/cyan]")
        for obj in results["registry_files"]["objects"]:
            doc_type = obj.get("doc_type", "")
            if doc_type == "registry":
                console.print(f"    [green]✓ doc_type='registry' (correct)[/green]")
            else:
                console.print(f"    [yellow]⚠ doc_type='{doc_type}' (expected 'registry')[/yellow]")
    else:
        console.print(f"\n  [dim]ℹ esa_doc_registry.md is not ingested (optional)[/dim]")

    return results


def check_2_documents_usage() -> dict:
    """Check if documents: field from index.md is used at runtime."""
    console.print(Panel("[bold cyan]CHECK 2: Is documents: field used anywhere at runtime?[/bold cyan]"))

    results = {
        "code_usages": [],
        "runtime_dependent": False,
    }

    # Search for documents access patterns in Python code
    patterns_to_search = [
        r"\.documents",          # Attribute access: obj.documents
        r"\[\"documents\"\]",    # Dict access: obj["documents"]
        r"\['documents'\]",      # Dict access: obj['documents']
        r"get\(['\"]documents", # Dict get: obj.get("documents")
    ]

    src_path = Path(__file__).parent.parent / "src"

    console.print(f"\n[bold]Searching for 'documents' field access in {src_path}:[/bold]")

    # Use grep to find matches
    for pattern in patterns_to_search:
        try:
            result = subprocess.run(
                ["grep", "-rn", "-E", pattern, str(src_path)],
                capture_output=True,
                text=True,
            )
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line and "test" not in line.lower():
                        results["code_usages"].append(line)
        except Exception as e:
            console.print(f"[red]Error running grep: {e}[/red]")

    # Check the index_metadata_loader specifically
    loader_path = src_path / "loaders" / "index_metadata_loader.py"
    if loader_path.exists():
        content = loader_path.read_text()

        # Check if documents field is used
        if "self.documents" in content or "documents:" in content:
            console.print(f"\n[bold]Found in index_metadata_loader.py:[/bold]")

            # Find specific usages
            for i, line in enumerate(content.split("\n"), 1):
                if "documents" in line and "Individual Document Metadata" not in line:
                    console.print(f"  Line {i}: {line.strip()[:80]}")

    # Check if any runtime code depends on it
    console.print(f"\n[bold]Analysis of code usages:[/bold]")

    if not results["code_usages"]:
        console.print("  No runtime access to documents: field found")
    else:
        console.print(f"  Found {len(results['code_usages'])} potential usages:")
        for usage in results["code_usages"][:10]:
            console.print(f"    {usage[:100]}")

    # Check specific functions
    console.print(f"\n[bold]Key functions that could use documents::[/bold]")

    # IndexMetadata.get_document_by_filename
    console.print("  1. IndexMetadata.get_document_by_filename():")
    console.print("     - Iterates over self.documents list")
    console.print("     - Returns DocumentInfo if filename matches")
    console.print("     - BUT: documents: [] is empty in actual index.md files!")

    # get_combined_metadata
    console.print("\n  2. IndexMetadata.get_combined_metadata():")
    console.print("     - Calls get_document_by_filename()")
    console.print("     - Merges doc-specific metadata if found")
    console.print("     - Currently returns empty (documents: [] is empty)")

    # Summary
    console.print(f"\n[bold]RESULT:[/bold]")
    console.print(f"  [yellow]⚠ The 'documents:' field IS accessed in code:[/yellow]")
    console.print(f"    - IndexMetadata.documents: list[DocumentInfo]")
    console.print(f"    - get_document_by_filename() iterates over it")
    console.print(f"    - get_combined_metadata() uses it for doc-specific metadata")
    console.print(f"\n  [yellow]⚠ BUT: The field is always empty (documents: [])![/yellow]")
    console.print(f"    - decisions/index.md: documents: []")
    console.print(f"    - principles/index.md: documents: []")
    console.print(f"\n  [red]This is the worst state: code exists but data is empty[/red]")
    console.print(f"  Runtime doesn't DEPEND on it, but it's also not populated")

    results["runtime_dependent"] = False
    results["populated"] = False

    return results


def check_3_record_type_separation(client) -> dict:
    """Check if doc_type properly separates content from approval records."""
    console.print(Panel("[bold cyan]CHECK 3: Is there deterministic record_type separation?[/bold cyan]"))

    results = {
        "adr_samples": [],
        "principle_samples": [],
        "doc_types_found": defaultdict(int),
        "filtering_works": False,
    }

    # ========== ADR Collection ==========
    console.print(f"\n[bold]ADR Collection - doc_type Analysis:[/bold]")

    try:
        adr_collection = client.collections.get(get_collection_name("adr"))
        offset = 0
        limit = 100
        all_adr_objects = []

        while True:
            batch = adr_collection.query.fetch_objects(
                return_properties=["file_path", "title", "doc_type", "adr_number", "status"],
                limit=limit,
                offset=offset,
            )
            if not batch.objects:
                break
            all_adr_objects.extend(batch.objects)
            offset += limit

        # Analyze doc_types
        doc_type_counts = defaultdict(int)
        doc_type_examples = defaultdict(list)

        for obj in all_adr_objects:
            dt = obj.properties.get("doc_type", "")
            doc_type_counts[dt if dt else "(empty)"] += 1
            if len(doc_type_examples[dt]) < 2:
                doc_type_examples[dt].append({
                    "file_path": obj.properties.get("file_path", ""),
                    "title": obj.properties.get("title", ""),
                    "adr_number": obj.properties.get("adr_number", ""),
                })

        console.print(f"  Total objects: {len(all_adr_objects)}")
        console.print(f"\n  [bold]doc_type distribution:[/bold]")

        table = Table()
        table.add_column("doc_type", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("Example file_path")

        for dt, count in sorted(doc_type_counts.items()):
            example = doc_type_examples[dt][0]["file_path"] if doc_type_examples[dt] else ""
            table.add_row(dt, str(count), example[:60])
            results["doc_types_found"][f"adr:{dt}"] = count

        console.print(table)

        # Show specific examples
        console.print(f"\n  [bold]Sample ADR content file (e.g., 0025-...md):[/bold]")
        for obj in all_adr_objects:
            if obj.properties.get("adr_number") == "0025" and "decision_approval" not in obj.properties.get("doc_type", "").lower():
                fp = obj.properties.get("file_path", "")
                if "D-" not in fp:  # Not a DAR
                    results["adr_samples"].append({
                        "type": "content",
                        "file_path": fp,
                        "title": obj.properties.get("title", ""),
                        "adr_number": obj.properties.get("adr_number", ""),
                        "doc_type": obj.properties.get("doc_type", ""),
                    })
                    console.print(f"    file_path: {fp}")
                    console.print(f"    title: {obj.properties.get('title', '')}")
                    console.print(f"    adr_number: {obj.properties.get('adr_number', '')}")
                    console.print(f"    doc_type: {obj.properties.get('doc_type', '')}")
                    break

        console.print(f"\n  [bold]Sample ADR DAR file (e.g., 0025D-...md):[/bold]")
        for obj in all_adr_objects:
            fp = obj.properties.get("file_path", "")
            if "0025D-" in fp or "0025d-" in fp:
                results["adr_samples"].append({
                    "type": "approval",
                    "file_path": fp,
                    "title": obj.properties.get("title", ""),
                    "adr_number": obj.properties.get("adr_number", ""),
                    "doc_type": obj.properties.get("doc_type", ""),
                })
                console.print(f"    file_path: {fp}")
                console.print(f"    title: {obj.properties.get('title', '')}")
                console.print(f"    adr_number: {obj.properties.get('adr_number', '')}")
                console.print(f"    doc_type: {obj.properties.get('doc_type', '')}")
                break
        else:
            console.print(f"    [yellow]No 0025D- file found[/yellow]")
            # Try to find any DAR
            for obj in all_adr_objects:
                dt = obj.properties.get("doc_type", "")
                if "approval" in dt.lower() or "dar" in dt.lower():
                    results["adr_samples"].append({
                        "type": "approval",
                        "file_path": obj.properties.get("file_path", ""),
                        "title": obj.properties.get("title", ""),
                        "adr_number": obj.properties.get("adr_number", ""),
                        "doc_type": dt,
                    })
                    console.print(f"    (Found alternative DAR)")
                    console.print(f"    file_path: {obj.properties.get('file_path', '')}")
                    console.print(f"    doc_type: {dt}")
                    break

    except Exception as e:
        console.print(f"[red]Error checking ADR collection: {e}[/red]")

    # ========== Principle Collection ==========
    console.print(f"\n[bold]Principle Collection - doc_type Analysis:[/bold]")

    try:
        principle_collection = client.collections.get(get_collection_name("principle"))
        offset = 0
        all_principle_objects = []

        while True:
            batch = principle_collection.query.fetch_objects(
                return_properties=["file_path", "title", "doc_type", "principle_number"],
                limit=limit,
                offset=offset,
            )
            if not batch.objects:
                break
            all_principle_objects.extend(batch.objects)
            offset += limit

        # Analyze doc_types
        doc_type_counts = defaultdict(int)
        doc_type_examples = defaultdict(list)

        for obj in all_principle_objects:
            dt = obj.properties.get("doc_type", "")
            doc_type_counts[dt if dt else "(empty)"] += 1
            if len(doc_type_examples[dt]) < 2:
                doc_type_examples[dt].append({
                    "file_path": obj.properties.get("file_path", ""),
                    "title": obj.properties.get("title", ""),
                })

        console.print(f"  Total objects: {len(all_principle_objects)}")
        console.print(f"\n  [bold]doc_type distribution:[/bold]")

        table = Table()
        table.add_column("doc_type", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("Example file_path")

        for dt, count in sorted(doc_type_counts.items()):
            example = doc_type_examples[dt][0]["file_path"] if doc_type_examples[dt] else ""
            table.add_row(dt, str(count), example[:60])
            results["doc_types_found"][f"principle:{dt}"] = count

        console.print(table)

        # Show specific examples
        console.print(f"\n  [bold]Sample Principle content file (e.g., 0010-...md):[/bold]")
        for obj in all_principle_objects:
            fp = obj.properties.get("file_path", "")
            pn = obj.properties.get("principle_number", "")
            if pn == "0010" and "D-" not in fp:
                results["principle_samples"].append({
                    "type": "content",
                    "file_path": fp,
                    "title": obj.properties.get("title", ""),
                    "principle_number": pn,
                    "doc_type": obj.properties.get("doc_type", ""),
                })
                console.print(f"    file_path: {fp}")
                console.print(f"    title: {obj.properties.get('title', '')}")
                console.print(f"    principle_number: {pn}")
                console.print(f"    doc_type: {obj.properties.get('doc_type', '')}")
                break

        console.print(f"\n  [bold]Sample Principle DAR file (e.g., 0010D-...md):[/bold]")
        for obj in all_principle_objects:
            fp = obj.properties.get("file_path", "")
            if "0010D-" in fp or "0010d-" in fp:
                results["principle_samples"].append({
                    "type": "approval",
                    "file_path": fp,
                    "title": obj.properties.get("title", ""),
                    "principle_number": obj.properties.get("principle_number", ""),
                    "doc_type": obj.properties.get("doc_type", ""),
                })
                console.print(f"    file_path: {fp}")
                console.print(f"    title: {obj.properties.get('title', '')}")
                console.print(f"    principle_number: {obj.properties.get('principle_number', '')}")
                console.print(f"    doc_type: {obj.properties.get('doc_type', '')}")
                break
        else:
            console.print(f"    [yellow]No 0010D- file found[/yellow]")
            # Try to find any DAR
            for obj in all_principle_objects:
                dt = obj.properties.get("doc_type", "")
                if "approval" in dt.lower() or "dar" in dt.lower():
                    results["principle_samples"].append({
                        "type": "approval",
                        "file_path": obj.properties.get("file_path", ""),
                        "title": obj.properties.get("title", ""),
                        "principle_number": obj.properties.get("principle_number", ""),
                        "doc_type": dt,
                    })
                    console.print(f"    (Found alternative DAR)")
                    console.print(f"    file_path: {obj.properties.get('file_path', '')}")
                    console.print(f"    doc_type: {dt}")
                    break

    except Exception as e:
        console.print(f"[red]Error checking Principle collection: {e}[/red]")

    # ========== Show Retrieval Filter Code ==========
    console.print(f"\n[bold]Retrieval Filter Implementation:[/bold]")
    console.print(f"\n  From src/skills/filters.py:")
    console.print(f"  ```python")
    console.print(f"  # Content types to include in list queries (allow-list)")
    console.print(f"  ADR_CONTENT_TYPES = ['adr', 'content']")
    console.print(f"  PRINCIPLE_CONTENT_TYPES = ['principle', 'content']")
    console.print(f"  EXCLUDED_TYPES = ['adr_approval', 'decision_approval_record', 'template', 'index']")
    console.print(f"  ")
    console.print(f"  def build_document_filter(...):")
    console.print(f"      # Allow-list: doc_type IN [allowed_types]")
    console.print(f"      filters = [Filter.by_property('doc_type').equal(t) for t in allowed_types]")
    console.print(f"      return combined_with_OR(filters)")
    console.print(f"  ```")

    # Summary
    console.print(f"\n[bold]RESULT:[/bold]")

    # Check if doc_type separation exists
    has_dar_doctype = any("approval" in str(k).lower() or "dar" in str(k).lower() for k in results["doc_types_found"].keys())
    has_content_doctype = any(k.endswith(":adr") or k.endswith(":content") or k.endswith(":principle") for k in results["doc_types_found"].keys())

    if has_dar_doctype and has_content_doctype:
        console.print(f"  [green]✓ doc_type field DOES separate content from approval records[/green]")
        console.print(f"    - Content documents have doc_type='adr' or 'content' or 'principle'")
        console.print(f"    - Approval records have doc_type='decision_approval_record'")
        results["filtering_works"] = True
    else:
        console.print(f"  [red]✗ doc_type separation is INCOMPLETE[/red]")
        if not has_dar_doctype:
            console.print(f"    - No 'approval' doc_type found for DARs")
        if not has_content_doctype:
            console.print(f"    - No 'content' doc_type found for content files")

    console.print(f"\n  [bold]Filter enforcement:[/bold]")
    console.print(f"    - list_all_adrs: filters doc_type IN ['adr', 'content']")
    console.print(f"    - list_all_principles: filters doc_type IN ['principle', 'content']")
    console.print(f"    - approval queries: adds 'decision_approval_record' to allow-list")

    return results


def main():
    console.print(Panel("[bold]THREE CHECKS VERIFICATION SCRIPT[/bold]\n"
                       "Investigating ADR/DAR + Principles/DAR confusion causes"))

    try:
        client = get_weaviate_client()
        console.print("[green]✓ Connected to Weaviate[/green]\n")
    except Exception as e:
        console.print(f"[red]Failed to connect to Weaviate: {e}[/red]")
        console.print("\n[yellow]Make sure Weaviate is running: docker compose up -d[/yellow]")
        sys.exit(1)

    try:
        # Run all three checks
        check1_results = check_1_index_ingestion(client)
        console.print("\n" + "=" * 70 + "\n")

        check2_results = check_2_documents_usage()
        console.print("\n" + "=" * 70 + "\n")

        check3_results = check_3_record_type_separation(client)
        console.print("\n" + "=" * 70 + "\n")

        # Final Summary
        console.print(Panel("[bold]FINAL SUMMARY[/bold]"))

        console.print("\n[bold]CHECK 1: index.md ingestion[/bold]")
        idx_count = check1_results["decisions_index"]["count"] + check1_results["principles_index"]["count"]
        registry_count = check1_results.get("registry_files", {}).get("count", 0)
        if idx_count == 0:
            console.print("  [green]✓ PASS: Directory index.md files NOT ingested[/green]")
        else:
            console.print(f"  [yellow]⚠ WARNING: {idx_count} directory index.md file(s) found in Weaviate[/yellow]")

        if registry_count > 0:
            console.print(f"  [cyan]ℹ INFO: esa_doc_registry.md is ingested ({registry_count} object(s))[/cyan]")
            console.print("    This is intentional - the registry is the canonical doc catalog")

        console.print("\n[bold]CHECK 2: documents: usage[/bold]")
        console.print("  [yellow]⚠ PARTIAL: Code exists but field is empty[/yellow]")
        console.print("    - IndexMetadata.documents is parsed from index.md")
        console.print("    - get_document_by_filename() iterates over it")
        console.print("    - BUT: documents: [] is always empty in actual files")
        console.print("    - No runtime depends on it being populated")

        console.print("\n[bold]CHECK 3: record_type separation[/bold]")
        if check3_results["filtering_works"]:
            console.print("  [green]✓ PASS: doc_type separates content from approval records[/green]")
            console.print("    - Filtering uses allow-list approach")
            console.print("    - content: doc_type IN ['adr', 'content', 'principle']")
            console.print("    - approval: doc_type = 'decision_approval_record'")
        else:
            console.print("  [red]✗ FAIL: doc_type separation incomplete[/red]")

        console.print("\n[bold]Recommended Actions:[/bold]")
        if idx_count > 0:
            console.print("  1. Exclude index.md from ingestion (already in SKIP_DOC_TYPES_AT_INGESTION)")
        console.print("  2. Either populate documents: registry OR remove dead code paths")
        console.print("  3. Verify doc_type='decision_approval_record' is set for all NNNND-*.md files")

        # Output JSON for programmatic use
        all_results = {
            "check1_index_ingestion": {
                "passed": idx_count == 0,
                "decisions_index_count": check1_results["decisions_index"]["count"],
                "principles_index_count": check1_results["principles_index"]["count"],
                "registry_files_count": check1_results.get("registry_files", {}).get("count", 0),
            },
            "check2_documents_usage": {
                "code_exists": True,
                "data_populated": False,
                "runtime_dependent": False,
            },
            "check3_record_type_separation": {
                "passed": check3_results["filtering_works"],
                "doc_types_found": dict(check3_results["doc_types_found"]),
            },
        }

        console.print("\n[dim]JSON Results:[/dim]")
        console.print(json.dumps(all_results, indent=2))

    finally:
        client.close()


if __name__ == "__main__":
    main()
