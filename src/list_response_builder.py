"""Deterministic list response builder for enterprise-grade output.

This module provides:
- Deduplication of chunked items by identity key
- Stable sorting and deterministic formatting
- Contract-compliant StructuredResponse generation
- No LLM involvement for list endpoint serialization

Architecture:
    Tool output (raw rows) -> build_list_structured_json() -> JSON string

The list_response_builder enforces the response contract at the application
boundary without relying on LLM JSON formatting.
"""

import json
import logging
from typing import Optional

from .response_schema import StructuredResponse, CURRENT_SCHEMA_VERSION

logger = logging.getLogger(__name__)

# Marker for list result detection in Elysia tree responses
LIST_RESULT_MARKER = "__list_result__"


def build_list_structured_json(
    *,
    item_type_label: str,              # "ADR" / "Principle"
    items: list[dict],                 # tool output rows
    identity_key: str,                 # "adr_number" or "file_path" etc.
    title_key: str = "title",
    number_key: Optional[str] = None,  # "adr_number" or "principle_number"
    status_key: Optional[str] = "status",
    items_total: Optional[int] = None, # total unique docs (not chunks)
    count_qualifier: str = "exact",    # exact/at_least/approx
    max_items_in_answer: int = 50,     # keep UI sane
    source_type: str = "ADR",          # one of allowed types
) -> str:
    """Build deterministic JSON for list responses (no LLM involved).

    This function:
    1. Deduplicates items by identity key (handles chunked documents)
    2. Applies stable sorting (by number if present, else by file_path/title)
    3. Generates deterministic answer text
    4. Populates StructuredResponse fields exactly
    5. Returns valid JSON string

    Args:
        item_type_label: Display label for items (e.g., "ADR", "Principle")
        items: Raw rows from tool output
        identity_key: Property to dedupe by (e.g., "adr_number", "file_path")
        title_key: Property containing item title
        number_key: Optional property for item number (for prefixes like ADR.0031)
        status_key: Optional property for status display
        items_total: Total unique docs count (if known, overrides computed count)
        count_qualifier: "exact", "at_least", or "approx"
        max_items_in_answer: Maximum items to show in answer text
        source_type: Source type for schema (ADR, Principle, Policy, Vocabulary)

    Returns:
        JSON string containing valid StructuredResponse
    """
    # 1) Dedupe by identity (chunk-safe)
    seen = set()
    unique = []
    for it in items:
        ident = (it.get(identity_key) or "").strip()
        if not ident:
            # If identity is missing, use file_path as fallback identity
            ident = f"__missing__:{it.get('file_path', '')}"
        if ident in seen:
            continue
        seen.add(ident)
        unique.append(it)

    # 2) Stable sorting (by number if present else by file_path/title)
    def sort_key(x: dict):
        if number_key and x.get(number_key):
            # Zero-pad for proper numeric sorting
            num = str(x.get(number_key))
            return num.zfill(10) if num.isdigit() else num
        fp = x.get("file_path") or ""
        return fp or (x.get(title_key) or "")
    unique_sorted = sorted(unique, key=sort_key)

    # 3) Create deterministic answer text (not LLM)
    shown = unique_sorted[:max_items_in_answer]
    lines = []
    for it in shown:
        num = (it.get(number_key) if number_key else None)
        title = (it.get(title_key) or "").strip()
        status = (it.get(status_key) or "").strip() if status_key else ""

        # Format: "ADR.0031 - Title (status)"
        if num:
            # Pad number to 4 digits for display
            num_str = str(num)
            if num_str.isdigit():
                num_str = num_str.zfill(4)
            prefix = f"{item_type_label}.{num_str}"
        else:
            prefix = item_type_label

        suffix = f" ({status})" if status else ""
        # Keep deterministic formatting
        if title:
            lines.append(f"- {prefix} - {title}{suffix}")
        else:
            lines.append(f"- {prefix}{suffix}")

    if not lines:
        answer = f"No {item_type_label}s found."
    else:
        answer = "\n".join(lines)

    # 4) Fill schema fields
    total = items_total if items_total is not None else len(unique_sorted)
    items_shown_count = len(shown)

    sr = StructuredResponse(
        schema_version=CURRENT_SCHEMA_VERSION,
        answer=answer,
        items_shown=items_shown_count,
        items_total=total,
        count_qualifier=count_qualifier,
        sources=[{"title": f"{item_type_label} index", "type": source_type}],
    )

    # 5) Always set transparency statement with collection-specific label
    if total > items_shown_count:
        sr.transparency_statement = f"Showing {items_shown_count} of {total} total {item_type_label}s"
    elif total > 0:
        sr.transparency_statement = f"Showing all {total} {item_type_label}s"

    return json.dumps(sr.to_dict(), ensure_ascii=False)


def build_list_result_marker(
    *,
    collection: str,
    rows: list[dict],
    total_unique: int,
    fallback_triggered: bool = False,
) -> dict:
    """Build a marked list result for detection in response processing.

    This marker enables the response gateway to detect list tool output
    and route it through deterministic serialization instead of LLM parsing.

    Args:
        collection: Collection type ("adr", "principle", etc.)
        rows: Raw document rows from tool
        total_unique: Total unique document count (not chunk count)
        fallback_triggered: If True, indicates in-memory filtering was used
            because doc_type metadata was missing. Response will use
            count_qualifier="at_least" to indicate uncertainty.

    Returns:
        Dict with __list_result__ marker for detection
    """
    return {
        LIST_RESULT_MARKER: True,
        "collection": collection,
        "rows": rows,
        "total_unique": total_unique,
        "fallback_triggered": fallback_triggered,
    }


def is_list_result(result: any) -> bool:
    """Check if a result is a marked list result.

    Args:
        result: Tool output to check

    Returns:
        True if result is a list result marker
    """
    if isinstance(result, dict):
        return result.get(LIST_RESULT_MARKER, False)
    return False


def finalize_list_result(result: dict) -> str:
    """Finalize a marked list result into contract-compliant JSON.

    Routes list results to appropriate builder based on collection type.
    When fallback was triggered (doc_type missing), uses count_qualifier="at_least"
    to indicate that the count may not be complete.

    Args:
        result: Marked list result dict

    Returns:
        JSON string containing valid StructuredResponse
    """
    collection = result.get("collection", "").lower()
    rows = result.get("rows", [])
    total_unique = result.get("total_unique", len(rows))
    fallback_triggered = result.get("fallback_triggered", False)

    # When fallback is triggered, use "at_least" qualifier to indicate uncertainty
    # Also add a transparency note about the fallback
    count_qualifier = "at_least" if fallback_triggered else "exact"

    if collection == "adr":
        json_str = build_list_structured_json(
            item_type_label="ADR",
            items=rows,
            identity_key="adr_number",
            title_key="title",
            number_key="adr_number",
            status_key="status",
            items_total=total_unique,
            count_qualifier=count_qualifier,
            source_type="ADR",
        )
    elif collection == "principle":
        json_str = build_list_structured_json(
            item_type_label="PCP",
            items=rows,
            identity_key="principle_number",
            title_key="title",
            number_key="principle_number",
            status_key=None,  # Principles don't have status
            items_total=total_unique,
            count_qualifier=count_qualifier,
            source_type="Principle",
        )
    else:
        # Generic fallback
        json_str = build_list_structured_json(
            item_type_label=collection.upper(),
            items=rows,
            identity_key="file_path",
            title_key="title",
            items_total=total_unique,
            count_qualifier=count_qualifier,
            source_type=collection.title(),
        )

    # Add fallback transparency if needed
    if fallback_triggered:
        data = json.loads(json_str)
        existing_statement = data.get("transparency_statement", "")
        fallback_note = "Note: Document metadata may be incomplete. Please run migration for accurate counts."
        if existing_statement:
            data["transparency_statement"] = f"{existing_statement}. {fallback_note}"
        else:
            data["transparency_statement"] = fallback_note
        json_str = json.dumps(data, ensure_ascii=False)

    return json_str


def dedupe_by_identity(
    items: list[dict],
    identity_key: str,
    fallback_key: str = "file_path",
) -> list[dict]:
    """Deduplicate items by identity key.

    Utility function for deduplication that can be used by tools
    before returning raw rows.

    Args:
        items: List of item dicts
        identity_key: Primary key for deduplication
        fallback_key: Fallback key if identity_key is missing

    Returns:
        Deduplicated list maintaining original order
    """
    seen = set()
    unique = []
    for it in items:
        ident = (it.get(identity_key) or "").strip()
        if not ident:
            ident = f"__fallback__:{it.get(fallback_key, '')}"
        if ident in seen:
            continue
        seen.add(ident)
        unique.append(it)
    return unique
