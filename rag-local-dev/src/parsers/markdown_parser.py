"""
Markdown parser for ADRs and Architectural Principles.
Handles YAML frontmatter and section-aware chunking.

Supports two formats:
1. ESA ADRs/Principles: YAML frontmatter with status, date, approvers
2. Data Office Principles: Simple markdown (Dutch) without frontmatter
"""

import re
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

import frontmatter


@dataclass
class MarkdownChunk:
    """Represents a parsed chunk from a markdown document."""

    content: str  # The actual chunk text (with contextual prefix)
    document_id: str  # e.g., "ADR-0001", "PRINCIPLE-0010"
    document_title: str
    document_type: str  # 'adr', 'principle', 'governance_principle'
    document_status: Optional[str]  # For ADRs: proposed, accepted, deprecated
    section_header: Optional[str]
    chunk_index: int
    source_file: str
    owner_team: Optional[str] = None
    owner_team_abbr: Optional[str] = None
    owner_department: Optional[str] = None
    owner_organization: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class OwnershipInfo:
    """Ownership metadata from index.md files."""

    team: Optional[str] = None
    team_abbr: Optional[str] = None
    department: Optional[str] = None
    organization: Optional[str] = None


def parse_index_metadata(index_path: Path) -> OwnershipInfo:
    """Parse ownership information from index.md file."""
    if not index_path.exists():
        return OwnershipInfo()

    try:
        content = index_path.read_text(encoding="utf-8")
        post = frontmatter.loads(content)
        fm = post.metadata

        ownership = fm.get("ownership", {})

        # Extract with language preference (English first)
        def get_value(d: dict, key: str) -> Optional[str]:
            if key not in d:
                return None
            val = d[key]
            if isinstance(val, dict):
                return val.get("en") or val.get("nl") or str(val)
            return str(val) if val else None

        return OwnershipInfo(
            team=get_value(ownership, "team"),
            team_abbr=get_value(ownership, "team_abbr"),
            department=get_value(ownership, "department"),
            organization=get_value(ownership, "organization"),
        )
    except Exception:
        return OwnershipInfo()


def split_by_headers(markdown: str, min_level: int = 2) -> List[Tuple[str, str]]:
    """
    Split markdown by headers, keeping content with its header.

    Args:
        markdown: The markdown content
        min_level: Minimum header level to split on (2 = ##, 3 = ###)

    Returns:
        List of (header, content) tuples
    """
    pattern = rf"^(#{{{min_level},3}})\s+(.+)$"

    sections = []
    current_header = "Introduction"
    current_content = []

    for line in markdown.split("\n"):
        match = re.match(pattern, line)
        if match:
            if current_content:
                sections.append((current_header, "\n".join(current_content).strip()))
            current_header = match.group(2).strip()
            current_content = []
        else:
            current_content.append(line)

    if current_content:
        sections.append((current_header, "\n".join(current_content).strip()))

    return sections


def extract_document_id_from_filename(filepath: Path) -> str:
    """Extract document ID from filename (e.g., '0001-use-conventions.md' -> '0001')."""
    stem = filepath.stem
    match = re.match(r"^(\d{4})", stem)
    if match:
        return match.group(1)
    return stem


def parse_adr(filepath: Path, ownership: Optional[OwnershipInfo] = None) -> List[MarkdownChunk]:
    """
    Parse ADR with frontmatter and section awareness.

    Expected frontmatter fields:
    - status: accepted, proposed, deprecated, superseded
    - date: YYYY-MM-DD
    - approvers: string
    """
    content = filepath.read_text(encoding="utf-8")

    try:
        post = frontmatter.loads(content)
        fm = post.metadata
        body = post.content
    except Exception:
        fm = {}
        body = content

    # Extract document ID and title
    doc_num = extract_document_id_from_filename(filepath)
    doc_id = f"ADR-{doc_num}"

    # Try to get title from frontmatter or first heading
    doc_title = fm.get("title")
    if not doc_title:
        # Look for first # heading
        title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        if title_match:
            doc_title = title_match.group(1).strip()
        else:
            doc_title = filepath.stem.replace("-", " ").title()

    doc_status = fm.get("status", "unknown")

    sections = split_by_headers(body)

    chunks = []
    ownership = ownership or OwnershipInfo()

    for idx, (header, section_content) in enumerate(sections):
        if not section_content.strip():
            continue

        # Contextual prefix for embedding
        context = f"ADR: {doc_title} (ID: {doc_id}, Status: {doc_status})\nSection: {header}\n\n"

        chunks.append(
            MarkdownChunk(
                content=context + section_content,
                document_id=doc_id,
                document_title=doc_title,
                document_type="adr",
                document_status=doc_status,
                section_header=header,
                chunk_index=idx,
                source_file=str(filepath.name),
                owner_team=ownership.team,
                owner_team_abbr=ownership.team_abbr,
                owner_department=ownership.department,
                owner_organization=ownership.organization,
                metadata={
                    k: v
                    for k, v in fm.items()
                    if k not in ["id", "title", "status"] and isinstance(v, (str, int, float, bool))
                },
            )
        )

    return chunks


def parse_principle(
    filepath: Path, ownership: Optional[OwnershipInfo] = None, doc_type: str = "principle"
) -> List[MarkdownChunk]:
    """
    Parse Architectural Principle with frontmatter and section awareness.

    Expected sections:
    - Statement
    - Rationale
    - Implications
    - More Information
    """
    content = filepath.read_text(encoding="utf-8")

    try:
        post = frontmatter.loads(content)
        fm = post.metadata
        body = post.content
    except Exception:
        fm = {}
        body = content

    # Extract document ID
    doc_num = extract_document_id_from_filename(filepath)
    doc_id = f"PRINCIPLE-{doc_num}"

    # Get title from frontmatter or first heading
    doc_title = fm.get("title")
    if not doc_title:
        title_match = re.search(r"^#\s+(?:Principle:\s*)?(.+)$", body, re.MULTILINE)
        if title_match:
            doc_title = title_match.group(1).strip()
        else:
            doc_title = filepath.stem.replace("-", " ").title()

    doc_status = fm.get("status")

    sections = split_by_headers(body)

    chunks = []
    ownership = ownership or OwnershipInfo()

    for idx, (header, section_content) in enumerate(sections):
        if not section_content.strip():
            continue

        context = f"Architectural Principle: {doc_title} (ID: {doc_id})"
        if doc_status:
            context += f" (Status: {doc_status})"
        context += f"\nSection: {header}\n\n"

        chunks.append(
            MarkdownChunk(
                content=context + section_content,
                document_id=doc_id,
                document_title=doc_title,
                document_type=doc_type,
                document_status=doc_status,
                section_header=header,
                chunk_index=idx,
                source_file=str(filepath.name),
                owner_team=ownership.team,
                owner_team_abbr=ownership.team_abbr,
                owner_department=ownership.department,
                owner_organization=ownership.organization,
                metadata={
                    k: v
                    for k, v in fm.items()
                    if k not in ["id", "title", "status"] and isinstance(v, (str, int, float, bool))
                },
            )
        )

    return chunks


def parse_governance_principle(
    filepath: Path, ownership: Optional[OwnershipInfo] = None
) -> List[MarkdownChunk]:
    """
    Parse Data Office governance principles (Dutch, no frontmatter).

    These have a simpler structure:
    - # Main Title
    - ## Sub-principle
    - ### Omschrijving (Description)
    - ### Rationale
    """
    content = filepath.read_text(encoding="utf-8")

    # Extract document ID
    doc_num = extract_document_id_from_filename(filepath)
    doc_id = f"GOV-PRINCIPLE-{doc_num}"

    # Get title from first # heading
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    doc_title = title_match.group(1).strip() if title_match else filepath.stem.replace("-", " ").title()

    # Split by ## headers (sub-principles)
    sections = split_by_headers(content, min_level=2)

    chunks = []
    ownership = ownership or OwnershipInfo()

    for idx, (header, section_content) in enumerate(sections):
        if not section_content.strip():
            continue

        # Add context prefix (in Dutch since these are Dutch documents)
        context = f"Data Governance Principe: {doc_title} (ID: {doc_id})\nSectie: {header}\n\n"

        chunks.append(
            MarkdownChunk(
                content=context + section_content,
                document_id=doc_id,
                document_title=doc_title,
                document_type="governance_principle",
                document_status=None,
                section_header=header,
                chunk_index=idx,
                source_file=str(filepath.name),
                owner_team=ownership.team,
                owner_team_abbr=ownership.team_abbr,
                owner_department=ownership.department,
                owner_organization=ownership.organization,
                metadata={},
            )
        )

    return chunks


def parse_markdown_directory(
    directory: Path, doc_type: str = "adr"
) -> Tuple[List[MarkdownChunk], OwnershipInfo]:
    """
    Parse all markdown files in a directory.

    Args:
        directory: Path to the directory containing markdown files
        doc_type: Type of documents ('adr', 'principle', 'governance_principle')

    Returns:
        Tuple of (list of chunks, ownership info)
    """
    if not directory.exists():
        return [], OwnershipInfo()

    # Load ownership info from index.md if present
    index_path = directory / "index.md"
    ownership = parse_index_metadata(index_path)

    chunks = []
    files = list(directory.glob("*.md"))

    for filepath in files:
        # Skip index.md and template files
        if filepath.name in ["index.md", "adr-template.md", "template.md"]:
            continue

        try:
            if doc_type == "adr":
                file_chunks = parse_adr(filepath, ownership)
            elif doc_type == "governance_principle":
                file_chunks = parse_governance_principle(filepath, ownership)
            else:
                file_chunks = parse_principle(filepath, ownership, doc_type)

            chunks.extend(file_chunks)
        except Exception as e:
            print(f"Warning: Failed to parse {filepath}: {e}")

    return chunks, ownership
