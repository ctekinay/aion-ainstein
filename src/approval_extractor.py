"""Deterministic approval extraction from DAR (Decision Approval Record) documents.

This module parses markdown tables in DAR files to extract approver information
without relying on LLM interpretation. This ensures reliable, accurate responses
to approval queries like "Who approved ADR.0025?"

Key features:
- Regex-based markdown table parsing
- Extracts approvers with name, email, role, comments
- Handles multiple approval sections (e.g., original + amendments)
- Returns structured JSON for contract-compliant responses
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Approver:
    """Represents an approver from a DAR."""
    name: str
    email: str = ""
    role: str = ""
    comments: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "comments": self.comments,
        }


@dataclass
class ApprovalSection:
    """Represents an approval section from a DAR."""
    section_title: str
    version: str = ""
    decision: str = ""
    decision_date: str = ""
    driver: str = ""
    remarks: str = ""
    approvers: list[Approver] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "section_title": self.section_title,
            "version": self.version,
            "decision": self.decision,
            "decision_date": self.decision_date,
            "driver": self.driver,
            "remarks": self.remarks,
            "approvers": [a.to_dict() for a in self.approvers],
        }


@dataclass
class ApprovalRecord:
    """Complete approval record for a document."""
    document_id: str  # e.g., "ADR.0025" or "PCP.0010"
    document_title: str
    file_path: str
    sections: list[ApprovalSection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "document_title": self.document_title,
            "file_path": self.file_path,
            "sections": [s.to_dict() for s in self.sections],
        }

    def get_all_approvers(self) -> list[Approver]:
        """Get all unique approvers across all sections."""
        seen = set()
        result = []
        for section in self.sections:
            for approver in section.approvers:
                key = (approver.name.lower(), approver.email.lower())
                if key not in seen:
                    seen.add(key)
                    result.append(approver)
        return result

    def format_approvers_answer(self) -> str:
        """Format approvers as a human-readable answer."""
        all_approvers = self.get_all_approvers()
        if not all_approvers:
            return f"No approvers found in the approval record for {self.document_id}."

        lines = [f"**{self.document_id}** was approved by:"]
        for approver in all_approvers:
            parts = [f"- **{approver.name}**"]
            if approver.role:
                parts.append(f" ({approver.role})")
            if approver.email:
                parts.append(f" - {approver.email}")
            lines.append("".join(parts))

        # Add section details if multiple
        if len(self.sections) > 1:
            lines.append("")
            lines.append("*Approval history:*")
            for section in self.sections:
                if section.decision_date:
                    lines.append(f"- {section.section_title}: {section.decision} on {section.decision_date}")

        return "\n".join(lines)


# =============================================================================
# Markdown Table Parsing
# =============================================================================

# Pattern to match markdown table rows: | cell | cell | cell |
TABLE_ROW_PATTERN = re.compile(r'^\s*\|(.+)\|\s*$')
# Pattern to match table separator row: |---|---|---|
TABLE_SEPARATOR_PATTERN = re.compile(r'^\s*\|[\s\-:|]+\|\s*$')


def parse_markdown_table(lines: list[str], start_idx: int) -> tuple[list[dict], int]:
    """Parse a markdown table starting at the given line index.

    Args:
        lines: All lines of the document
        start_idx: Index of the header row

    Returns:
        Tuple of (list of row dicts, end index)
    """
    if start_idx >= len(lines):
        return [], start_idx

    # Parse header row
    header_match = TABLE_ROW_PATTERN.match(lines[start_idx])
    if not header_match:
        return [], start_idx

    headers = [h.strip().lower() for h in header_match.group(1).split('|')]

    # Skip separator row
    next_idx = start_idx + 1
    if next_idx < len(lines) and TABLE_SEPARATOR_PATTERN.match(lines[next_idx]):
        next_idx += 1

    # Parse data rows
    rows = []
    while next_idx < len(lines):
        row_match = TABLE_ROW_PATTERN.match(lines[next_idx])
        if not row_match:
            break

        cells = [c.strip() for c in row_match.group(1).split('|')]
        row_dict = {}
        for i, header in enumerate(headers):
            if i < len(cells):
                row_dict[header] = cells[i]
        rows.append(row_dict)
        next_idx += 1

    return rows, next_idx


def extract_approvers_from_table(table_rows: list[dict]) -> list[Approver]:
    """Extract Approver objects from parsed table rows."""
    approvers = []
    for row in table_rows:
        name = row.get('name', '').strip()
        if not name:
            continue

        approvers.append(Approver(
            name=name,
            email=row.get('email', '').strip(),
            role=row.get('role', '').strip(),
            comments=row.get('comments', '').strip(),
        ))

    return approvers


def extract_metadata_from_table(table_rows: list[dict]) -> dict:
    """Extract key-value metadata from a Name/Value table."""
    metadata = {}
    for row in table_rows:
        name = row.get('name', '').strip().lower()
        value = row.get('value', '').strip()

        if 'version' in name:
            metadata['version'] = value
        elif 'decision date' in name:
            metadata['decision_date'] = value
        elif name == 'decision':
            metadata['decision'] = value
        elif 'driver' in name or 'owner' in name:
            metadata['driver'] = value
        elif 'remark' in name:
            metadata['remarks'] = value

    return metadata


# =============================================================================
# DAR Document Parsing
# =============================================================================

def parse_dar_content(content: str, doc_id: str = "", title: str = "", file_path: str = "") -> ApprovalRecord:
    """Parse a DAR document content and extract all approval sections.

    Args:
        content: Full markdown content of the DAR file
        doc_id: Document identifier (e.g., "ADR.0025")
        title: Document title
        file_path: Path to the DAR file

    Returns:
        ApprovalRecord with all parsed sections
    """
    lines = content.split('\n')
    sections = []
    current_section_title = "Approval Record"
    i = 0

    while i < len(lines):
        line = lines[i]

        # Detect section headers (## 1. Section Title or ## 2. Section Title)
        section_match = re.match(r'^##\s*\d*\.?\s*(.+)$', line)
        if section_match:
            current_section_title = section_match.group(1).strip()
            i += 1
            continue

        # Detect **Approvers** marker
        if '**approvers**' in line.lower() or line.strip().lower() == 'approvers':
            # Look for table in next few lines
            j = i + 1
            while j < len(lines) and j < i + 5:
                if TABLE_ROW_PATTERN.match(lines[j]):
                    table_rows, end_idx = parse_markdown_table(lines, j)
                    approvers = extract_approvers_from_table(table_rows)

                    if approvers:
                        # Find or create section
                        section = None
                        for s in sections:
                            if s.section_title == current_section_title:
                                section = s
                                break

                        if section is None:
                            section = ApprovalSection(section_title=current_section_title)
                            sections.append(section)

                        section.approvers.extend(approvers)

                    i = end_idx
                    break
                j += 1
            else:
                i += 1
            continue

        # Detect metadata tables (Name/Value format)
        if TABLE_ROW_PATTERN.match(line):
            # Check if this is a metadata table (has "Name" and "Value" headers)
            header_cells = [c.strip().lower() for c in line.split('|')[1:-1]]
            if 'name' in header_cells and 'value' in header_cells:
                table_rows, end_idx = parse_markdown_table(lines, i)
                metadata = extract_metadata_from_table(table_rows)

                if metadata:
                    # Find or create section
                    section = None
                    for s in sections:
                        if s.section_title == current_section_title:
                            section = s
                            break

                    if section is None:
                        section = ApprovalSection(section_title=current_section_title)
                        sections.append(section)

                    section.version = metadata.get('version', section.version)
                    section.decision = metadata.get('decision', section.decision)
                    section.decision_date = metadata.get('decision_date', section.decision_date)
                    section.driver = metadata.get('driver', section.driver)
                    section.remarks = metadata.get('remarks', section.remarks)

                i = end_idx
                continue

        i += 1

    return ApprovalRecord(
        document_id=doc_id,
        document_title=title,
        file_path=file_path,
        sections=sections,
    )


# =============================================================================
# Query Handling
# =============================================================================

# Pattern to extract document number from queries like "Who approved ADR.0025?"
DOC_NUMBER_PATTERNS = [
    re.compile(r'adr[.\s-]?(\d{1,4})', re.IGNORECASE),
    re.compile(r'pcp[.\s-]?(\d{1,4})', re.IGNORECASE),
    re.compile(r'principle[.\s-]?(\d{1,4})', re.IGNORECASE),
]


def extract_document_number(question: str) -> tuple[Optional[str], Optional[str]]:
    """Extract document type and number from a question.

    Args:
        question: User's question (e.g., "Who approved ADR.0025?")

    Returns:
        Tuple of (doc_type, doc_number) or (None, None) if not found
        doc_type is "adr" or "principle"
    """
    question_lower = question.lower()

    for pattern in DOC_NUMBER_PATTERNS:
        match = pattern.search(question_lower)
        if match:
            number = match.group(1).zfill(4)  # Normalize to 4 digits
            if 'adr' in question_lower:
                return ('adr', number)
            elif 'pcp' in question_lower or 'principle' in question_lower:
                return ('principle', number)

    return (None, None)


def is_specific_approval_query(question: str) -> bool:
    """Check if this is an approval query for a specific document.

    Args:
        question: User's question

    Returns:
        True if this is a "who approved ADR.XXXX" type query
    """
    question_lower = question.lower()

    # Must have approval intent
    approval_indicators = [
        'who approved', 'approved by', 'approvers', 'approval',
        'who signed', 'signed off', 'reviewed by',
    ]
    has_approval_intent = any(ind in question_lower for ind in approval_indicators)

    if not has_approval_intent:
        return False

    # Must reference a specific document
    doc_type, doc_number = extract_document_number(question)
    return doc_type is not None and doc_number is not None


def find_dar_file(doc_type: str, doc_number: str, base_path: Path) -> Optional[Path]:
    """Find the DAR file for a given document.

    Args:
        doc_type: "adr" or "principle"
        doc_number: 4-digit document number (e.g., "0025")
        base_path: Base path to the data directory

    Returns:
        Path to the DAR file or None if not found
    """
    # Determine search directory
    if doc_type == "adr":
        search_dir = base_path / "doc" / "decisions"
    else:
        search_dir = base_path / "doc" / "principles"

    if not search_dir.exists():
        return None

    # DAR files have pattern NNNND-*.md
    pattern = f"{doc_number}D-*.md"
    matching_files = list(search_dir.glob(pattern))

    # Also try lowercase 'd'
    if not matching_files:
        pattern = f"{doc_number}d-*.md"
        matching_files = list(search_dir.glob(pattern))

    if matching_files:
        return matching_files[0]

    return None


def get_approval_record_from_weaviate(
    client,
    doc_type: str,
    doc_number: str,
) -> Optional[ApprovalRecord]:
    """Fetch and parse a DAR from Weaviate.

    Args:
        client: Weaviate client
        doc_type: "adr" or "principle"
        doc_number: 4-digit document number

    Returns:
        ApprovalRecord or None if not found
    """
    from weaviate.classes.query import Filter

    # Determine collection
    if doc_type == "adr":
        collection_name = "ArchitecturalDecision"
        id_field = "adr_number"
        doc_id = f"ADR.{doc_number}"
    else:
        collection_name = "Principle"
        id_field = "principle_number"
        doc_id = f"PCP.{doc_number}"

    try:
        collection = client.collections.get(collection_name)

        # Build filter: doc_type is approval AND number matches
        number_filter = Filter.by_property(id_field).equal(doc_number)
        type_filter = (
            Filter.by_property("doc_type").equal("adr_approval") |
            Filter.by_property("doc_type").equal("decision_approval_record")
        )
        combined_filter = number_filter & type_filter

        # Fetch the DAR
        results = collection.query.fetch_objects(
            filters=combined_filter,
            limit=1,
            return_properties=["title", "content", "full_text", "file_path", id_field],
        )

        if not results.objects:
            logger.warning(f"No DAR found for {doc_id}")
            return None

        obj = results.objects[0]
        content = obj.properties.get("content") or obj.properties.get("full_text") or ""
        title = obj.properties.get("title", "")
        file_path = obj.properties.get("file_path", "")

        if not content:
            logger.warning(f"DAR found for {doc_id} but no content")
            return None

        return parse_dar_content(content, doc_id, title, file_path)

    except Exception as e:
        logger.error(f"Error fetching DAR for {doc_id}: {e}")
        return None


def build_approval_response(record: ApprovalRecord) -> dict:
    """Build a structured response for an approval query.

    Args:
        record: Parsed ApprovalRecord

    Returns:
        Dictionary with schema-compliant response
    """
    approvers = record.get_all_approvers()

    return {
        "schema_version": "1.0",
        "answer": record.format_approvers_answer(),
        "items_shown": len(approvers),
        "items_total": len(approvers),
        "count_qualifier": "exact",
        "transparency_statement": f"Extracted from {record.file_path}",
        "sources": [
            {
                "title": record.document_title or record.document_id,
                "type": "Decision Approval Record",
                "path": record.file_path,
            }
        ],
        "approval_record": record.to_dict(),
    }
