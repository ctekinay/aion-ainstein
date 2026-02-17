"""Parser for esa_doc_registry.md — authoritative metadata source.

Extracts document ID, title, status, date, and owner from the registry's
markdown tables for use as a fallback enrichment source during ingestion.
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def parse_registry(registry_path: Path) -> dict[str, dict]:
    """Parse esa_doc_registry.md and return a lookup dict.

    Parses all markdown tables in the registry file, extracting metadata
    for each ADR and PCP entry.

    Args:
        registry_path: Path to esa_doc_registry.md

    Returns:
        Lookup dict keyed by document ID (e.g., "ADR.29", "PCP.10").
        Each value contains: {"status", "date", "owner", "title"}
    """
    if not registry_path.exists():
        logger.warning(f"Registry file not found: {registry_path}")
        return {}

    content = registry_path.read_text(encoding="utf-8")
    registry = {}

    # Match markdown table rows: | ID | [Title](link) | Status | Date | Owner |
    # The ID column contains "ADR.NN" or "PCP.NN"
    # The Title column may contain a markdown link [Title](path) or plain text
    row_pattern = re.compile(
        r"^\|\s*"
        r"(ADR|PCP)\.(\d+)"        # Group 1: type, Group 2: number
        r"\s*\|\s*"
        r"(?:\[([^\]]+)\]"         # Group 3: title (from markdown link)
        r"\([^)]*\)"               # link target (ignored)
        r"|([^|]+))"               # Group 4: title (plain text fallback)
        r"\s*\|\s*"
        r"([^|]*)"                 # Group 5: status
        r"\s*\|\s*"
        r"([^|]*)"                 # Group 6: date
        r"\s*\|\s*"
        r"([^|]*)"                 # Group 7: owner
        r"\s*\|",
        re.MULTILINE,
    )

    for match in row_pattern.finditer(content):
        doc_type = match.group(1)  # "ADR" or "PCP"
        number = match.group(2)    # "29", "10", etc.
        title = (match.group(3) or match.group(4) or "").strip()
        status = match.group(5).strip()
        date = match.group(6).strip()
        owner = match.group(7).strip()

        doc_id = f"{doc_type}.{number}"

        # Also store with zero-padded number for filename matching
        number_padded = number.zfill(4)

        entry = {
            "status": status,
            "date": date,
            "owner": owner,
            "title": title,
        }

        # Key by both formats for flexible lookup
        registry[doc_id] = entry                           # "ADR.29"
        registry[f"{doc_type}.{number_padded}"] = entry    # "ADR.0029"

    logger.info(f"Parsed {len(registry) // 2} registry entries from {registry_path.name}")
    return registry


def get_registry_lookup(base_path: Optional[Path] = None) -> dict[str, dict]:
    """Load the registry with default path resolution.

    Args:
        base_path: Optional base path. Defaults to data/esa-main-artifacts/doc/

    Returns:
        Registry lookup dict
    """
    if base_path is None:
        base_path = Path(__file__).parent.parent.parent / "data" / "esa-main-artifacts" / "doc"

    registry_path = base_path / "esa_doc_registry.md"
    return parse_registry(registry_path)
