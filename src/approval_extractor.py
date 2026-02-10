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

from .weaviate.collections import get_collection_name

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

    # Must have approval intent (from config routing.markers.approval_intent)
    from .config import settings
    routing = settings.get_taxonomy_config().get("routing", {})
    approval_indicators = routing.get("markers", {}).get("approval_intent", [
        'who approved', 'approved by', 'approvers', 'approval',
        'who signed', 'signed off', 'reviewed by',
    ])
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
        collection_name = get_collection_name("adr")
        id_field = "adr_number"
        doc_id = f"ADR.{doc_number}"
    else:
        collection_name = get_collection_name("principle")
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


# =============================================================================
# Specific Document Content Retrieval (Non-Approval)
# =============================================================================

# Pattern to detect DAR-specific references (ADR.0025D or PCP.0010D)
DAR_REFERENCE_PATTERN = re.compile(r'(adr|pcp|principle)[.\s-]?(\d{1,4})[dD]', re.IGNORECASE)


@dataclass
class ContentRecord:
    """Content record for a document (ADR or Principle content, not DAR)."""
    document_id: str  # e.g., "ADR.0025" or "PCP.0010"
    document_title: str
    file_path: str
    content: str
    context: str = ""
    decision: str = ""
    consequences: str = ""
    status: str = ""

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "document_title": self.document_title,
            "file_path": self.file_path,
            "content": self.content,
            "context": self.context,
            "decision": self.decision,
            "consequences": self.consequences,
            "status": self.status,
        }

    def format_summary(self) -> str:
        """Format content as a human-readable summary."""
        lines = [f"**{self.document_id}**: {self.document_title}"]

        if self.status:
            lines.append(f"\n**Status:** {self.status}")

        if self.context:
            lines.append(f"\n**Context:**\n{self.context}")

        if self.decision:
            lines.append(f"\n**Decision:**\n{self.decision}")

        if self.consequences:
            lines.append(f"\n**Consequences:**\n{self.consequences}")

        # If no structured sections, use content as summary
        if not (self.context or self.decision or self.consequences):
            # Truncate content for summary (first 1000 chars)
            summary = self.content[:1000]
            if len(self.content) > 1000:
                summary += "..."
            lines.append(f"\n{summary}")

        return "\n".join(lines)


def extract_document_reference(question: str) -> tuple[Optional[str], Optional[str], bool]:
    """Extract document type, number, and whether it's a DAR reference.

    Args:
        question: User's question (e.g., "Tell me about ADR.0025D")

    Returns:
        Tuple of (doc_type, doc_number, is_dar_reference) or (None, None, False) if not found
        doc_type is "adr" or "principle"
        is_dar_reference is True if query explicitly asks for DAR (e.g., ADR.0025D)
    """
    question_lower = question.lower()

    # Check for explicit DAR reference first (ADR.0025D, PCP.0010D)
    dar_match = DAR_REFERENCE_PATTERN.search(question_lower)
    if dar_match:
        doc_prefix = dar_match.group(1).lower()
        number = dar_match.group(2).zfill(4)
        if doc_prefix == 'adr':
            return ('adr', number, True)
        else:  # pcp or principle
            return ('principle', number, True)

    # Otherwise check for regular document reference
    doc_type, doc_number = extract_document_number(question)
    return (doc_type, doc_number, False)


def is_specific_content_query(question: str) -> bool:
    """Check if this is a content query for a specific document (not approval).

    This detects queries like:
    - "Tell me about ADR.0025"
    - "What does ADR 25 say?"
    - "Explain ADR.0025"
    - "Details of PCP.0010"

    But NOT:
    - "Who approved ADR.0025?" (approval query)
    - "List all ADRs" (list query)
    - "Tell me about ADR.0025D" (explicit DAR query)

    Args:
        question: User's question

    Returns:
        True if this is a content query for a specific document
    """
    question_lower = question.lower()

    # Exclude approval queries
    if is_specific_approval_query(question):
        return False

    # Check for explicit DAR reference (e.g., ADR.0025D) - those go to DAR path
    dar_match = DAR_REFERENCE_PATTERN.search(question_lower)
    if dar_match:
        return False

    # Must reference a specific document
    doc_type, doc_number = extract_document_number(question)
    if doc_type is None or doc_number is None:
        return False

    # Must have content/detail intent (not just listing) - from config routing.markers.topical_intent
    from .config import settings
    routing = settings.get_taxonomy_config().get("routing", {})
    content_indicators = routing.get("markers", {}).get("topical_intent", [
        'about', 'status', 'consequences', 'decision drivers', 'context',
        'what does it say', 'explain', 'details', 'regarding', 'concerning',
    ])
    # Add additional content-specific indicators not in topical_intent
    content_indicators = list(content_indicators) + [
        'tell me', 'what is', 'what does', 'describe', 'show me',
        'what are the', 'decision', 'summary',
    ]
    has_content_intent = any(ind in question_lower for ind in content_indicators)

    # Also match patterns like "ADR.0025?" or just "ADR 25" as detail queries
    # (simple reference without list keywords) - from config routing.markers.list_intent
    list_keywords = routing.get("markers", {}).get("list_intent", [
        'list', 'all', 'how many', 'enumerate', 'exist',
    ])
    has_list_intent = any(kw in question_lower for kw in list_keywords)

    return has_content_intent or not has_list_intent


def is_specific_dar_query(question: str) -> bool:
    """Check if this is an explicit DAR (Decision Approval Record) query.

    This detects queries that explicitly reference the DAR document:
    - "Tell me about ADR.0025D"
    - "What's in PCP.0010D?"
    - "Show me ADR 25D"

    Args:
        question: User's question

    Returns:
        True if this explicitly asks for a DAR document
    """
    question_lower = question.lower()

    # Check for explicit DAR reference (e.g., ADR.0025D)
    dar_match = DAR_REFERENCE_PATTERN.search(question_lower)
    return dar_match is not None


def parse_adr_content(content: str) -> dict:
    """Parse ADR content to extract structured sections.

    Args:
        content: Full markdown content of the ADR file

    Returns:
        Dictionary with context, decision, consequences, status
    """
    sections = {
        "context": "",
        "decision": "",
        "consequences": "",
        "status": "",
    }

    lines = content.split('\n')
    current_section = None
    current_heading_level = 0
    section_content = []
    in_code_fence = False

    # Section header patterns
    section_patterns = {
        "context": re.compile(r'^#+\s*(context|background)', re.IGNORECASE),
        "decision": re.compile(r'^#+\s*(decision|the decision)', re.IGNORECASE),
        "consequences": re.compile(r'^#+\s*(consequences|implications)', re.IGNORECASE),
        "status": re.compile(r'^#+\s*status', re.IGNORECASE),
    }

    heading_pattern = re.compile(r'^(#+)\s+')

    for line in lines:
        # Track code fences to avoid treating # inside code as headings
        if line.strip().startswith('```'):
            in_code_fence = not in_code_fence
            if current_section:
                section_content.append(line)
            continue

        if in_code_fence:
            if current_section:
                section_content.append(line)
            continue

        # Check if this line is a heading
        heading_match = heading_pattern.match(line)

        if heading_match:
            new_level = len(heading_match.group(1))

            # Check if this heading starts a known section
            new_section = None
            for section_name, pattern in section_patterns.items():
                if pattern.match(line):
                    new_section = section_name
                    break

            if new_section:
                # Save previous section content
                if current_section:
                    sections[current_section] = '\n'.join(section_content).strip()
                current_section = new_section
                current_heading_level = new_level
                section_content = []
            elif current_section:
                # Only end the section if this heading is at the same or higher level
                if new_level <= current_heading_level:
                    sections[current_section] = '\n'.join(section_content).strip()
                    current_section = None
                    section_content = []
                else:
                    # Subsection — keep capturing
                    section_content.append(line)
        elif current_section:
            section_content.append(line)

    # Save last section
    if current_section:
        sections[current_section] = '\n'.join(section_content).strip()

    return sections


def get_content_record_from_weaviate(
    client,
    doc_type: str,
    doc_number: str,
) -> Optional[ContentRecord]:
    """Fetch a document's content (not DAR) from Weaviate.

    This explicitly excludes decision_approval_record documents to ensure
    we get the actual content document.

    Args:
        client: Weaviate client
        doc_type: "adr" or "principle"
        doc_number: 4-digit document number

    Returns:
        ContentRecord or None if not found
    """
    from weaviate.classes.query import Filter

    # Determine collection
    if doc_type == "adr":
        collection_name = get_collection_name("adr")
        id_field = "adr_number"
        doc_id = f"ADR.{doc_number}"
    else:
        collection_name = get_collection_name("principle")
        id_field = "principle_number"
        doc_id = f"PCP.{doc_number}"

    try:
        collection = client.collections.get(collection_name)

        # Build filter: number matches AND doc_type is content (not DAR)
        # Explicitly exclude decision_approval_record
        number_filter = Filter.by_property(id_field).equal(doc_number)
        content_type_filter = (
            Filter.by_property("doc_type").equal("content") |
            Filter.by_property("doc_type").equal("adr")  # Legacy type
        )
        exclude_dar_filter = Filter.by_property("doc_type").not_equal("decision_approval_record")
        exclude_dar_approval = Filter.by_property("doc_type").not_equal("adr_approval")

        combined_filter = number_filter & exclude_dar_filter & exclude_dar_approval

        # Fetch the content document
        results = collection.query.fetch_objects(
            filters=combined_filter,
            limit=10,  # Get a few to find the right one
            return_properties=["title", "content", "full_text", "file_path", "doc_type", id_field, "status"],
        )

        if not results.objects:
            logger.warning(f"No content document found for {doc_id}")
            return None

        # Find the best match - prefer content doc over DAR
        best_obj = None
        for obj in results.objects:
            file_path = obj.properties.get("file_path", "").lower()
            doc_type_prop = obj.properties.get("doc_type", "")

            # Skip DAR files (pattern NNND-*.md)
            if re.search(r'/\d{4}[dD]-', file_path):
                continue

            # Skip if doc_type is approval-related
            if doc_type_prop in ["decision_approval_record", "adr_approval"]:
                continue

            # Prefer files matching NNNN-*.md pattern (content files)
            if re.search(rf'/{doc_number}-', file_path):
                best_obj = obj
                break

            # Keep as fallback
            if best_obj is None:
                best_obj = obj

        if not best_obj:
            logger.warning(f"Content document found for {doc_id} but all are DARs")
            return None

        content = best_obj.properties.get("content") or best_obj.properties.get("full_text") or ""
        title = best_obj.properties.get("title", "")
        file_path = best_obj.properties.get("file_path", "")
        status = best_obj.properties.get("status", "")

        if not content:
            logger.warning(f"Content document found for {doc_id} but no content")
            return None

        # Parse structured sections
        parsed = parse_adr_content(content)

        return ContentRecord(
            document_id=doc_id,
            document_title=title,
            file_path=file_path,
            content=content,
            context=parsed.get("context", ""),
            decision=parsed.get("decision", ""),
            consequences=parsed.get("consequences", ""),
            status=status or parsed.get("status", ""),
        )

    except Exception as e:
        logger.error(f"Error fetching content for {doc_id}: {e}")
        return None


def get_dar_record_from_weaviate(
    client,
    doc_type: str,
    doc_number: str,
) -> Optional[ContentRecord]:
    """Fetch a DAR document explicitly from Weaviate.

    This is for queries that explicitly ask for the DAR (e.g., ADR.0025D).

    Args:
        client: Weaviate client
        doc_type: "adr" or "principle"
        doc_number: 4-digit document number

    Returns:
        ContentRecord for the DAR or None if not found
    """
    from weaviate.classes.query import Filter

    # Determine collection
    if doc_type == "adr":
        collection_name = get_collection_name("adr")
        id_field = "adr_number"
        doc_id = f"ADR.{doc_number}D"
    else:
        collection_name = get_collection_name("principle")
        id_field = "principle_number"
        doc_id = f"PCP.{doc_number}D"

    try:
        collection = client.collections.get(collection_name)

        # Build filter: number matches AND doc_type is approval
        number_filter = Filter.by_property(id_field).equal(doc_number)
        dar_type_filter = (
            Filter.by_property("doc_type").equal("decision_approval_record") |
            Filter.by_property("doc_type").equal("adr_approval")
        )
        combined_filter = number_filter & dar_type_filter

        # Fetch the DAR
        results = collection.query.fetch_objects(
            filters=combined_filter,
            limit=1,
            return_properties=["title", "content", "full_text", "file_path", "doc_type", id_field],
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

        return ContentRecord(
            document_id=doc_id,
            document_title=title,
            file_path=file_path,
            content=content,
        )

    except Exception as e:
        logger.error(f"Error fetching DAR for {doc_id}: {e}")
        return None


def build_content_response(record: ContentRecord, max_chars: int = 12000) -> dict:
    """Build a structured response for a content query.

    Args:
        record: Parsed ContentRecord
        max_chars: Maximum characters for full_text field (direct_doc_max_chars)

    Returns:
        Dictionary with schema-compliant response including summary and full_text
    """
    full_text = record.content[:max_chars]
    if len(record.content) > max_chars:
        full_text += "..."

    return {
        "schema_version": "1.0",
        "answer": record.format_summary(),
        "full_text": full_text,
        "items_shown": 1,
        "items_total": 1,
        "count_qualifier": "exact",
        "transparency_statement": f"Retrieved from {record.file_path}",
        "sources": [
            {
                "title": record.document_title or record.document_id,
                "type": "Architectural Decision Record" if "ADR" in record.document_id else "Principle",
                "path": record.file_path,
            }
        ],
        "content_record": record.to_dict(),
    }


def build_dar_content_response(record: ContentRecord, max_chars: int = 12000) -> dict:
    """Build a structured response for a DAR content query.

    Args:
        record: ContentRecord for the DAR
        max_chars: Maximum characters for full_text field (direct_doc_max_chars)

    Returns:
        Dictionary with schema-compliant response
    """
    # Parse DAR to get approval info
    dar_record = parse_dar_content(record.content, record.document_id, record.document_title, record.file_path)

    answer_parts = [f"**{record.document_id}** (Decision Approval Record)"]

    if record.document_title:
        answer_parts[0] = f"**{record.document_id}**: {record.document_title}"

    # Add approval summary if available
    if dar_record.sections:
        for section in dar_record.sections:
            if section.decision_date:
                answer_parts.append(f"\n**Decision Date:** {section.decision_date}")
            if section.decision:
                answer_parts.append(f"\n**Decision:** {section.decision}")
            if section.approvers:
                approver_names = [a.name for a in section.approvers]
                answer_parts.append(f"\n**Approvers:** {', '.join(approver_names)}")

    # Add content summary
    if record.content:
        content_preview = record.content[:500]
        if len(record.content) > 500:
            content_preview += "..."
        answer_parts.append(f"\n\n**Content Preview:**\n{content_preview}")

    full_text = record.content[:max_chars]
    if len(record.content) > max_chars:
        full_text += "..."

    return {
        "schema_version": "1.0",
        "answer": "\n".join(answer_parts),
        "full_text": full_text,
        "items_shown": 1,
        "items_total": 1,
        "count_qualifier": "exact",
        "transparency_statement": f"Retrieved from {record.file_path}",
        "sources": [
            {
                "title": record.document_title or record.document_id,
                "type": "Decision Approval Record",
                "path": record.file_path,
            }
        ],
    }
