"""Document type classification for ADRs and principles.

Canonical taxonomy for doc_type:
- adr: Actual Architectural Decision Records
- adr_approval: Decision Approval Records (DACI approval tracking, NNNND-*.md)
- template: Template files with placeholders
- index: Index/list files (index.md, readme.md, overview.md)
- unknown: Unclassified documents

This module provides deterministic classification based on:
1. Filename patterns (most reliable)
2. Title patterns
3. Content indicators (fallback)
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# =============================================================================
# Canonical Document Types
# =============================================================================

class DocType:
    """Canonical document type constants."""
    ADR = "adr"
    ADR_APPROVAL = "adr_approval"
    TEMPLATE = "template"
    INDEX = "index"
    UNKNOWN = "unknown"

    # For principles (using same taxonomy pattern)
    PRINCIPLE = "principle"
    PRINCIPLE_APPROVAL = "principle_approval"

    @classmethod
    def all_types(cls) -> list[str]:
        """Return all valid document types."""
        return [cls.ADR, cls.ADR_APPROVAL, cls.TEMPLATE, cls.INDEX, cls.UNKNOWN]

    @classmethod
    def content_types(cls) -> list[str]:
        """Return types that contain actual content (for querying)."""
        return [cls.ADR, cls.PRINCIPLE]

    @classmethod
    def excluded_types(cls) -> list[str]:
        """Return types typically excluded from list queries."""
        return [cls.ADR_APPROVAL, cls.TEMPLATE, cls.INDEX]


# =============================================================================
# Classification Patterns
# =============================================================================

# Decision Approval Record pattern: NNNND-*.md (e.g., 0021D-approval.md)
DAR_FILENAME_PATTERN = re.compile(r"^\d{4}[dD]-", re.IGNORECASE)

# Index file patterns
INDEX_FILENAMES = frozenset(["index.md", "readme.md", "overview.md", "_index.md"])

# Template indicators in content
TEMPLATE_CONTENT_INDICATORS = [
    "{short title",
    "{problem statement}",
    "{context}",
    "{decision outcome}",
    "[insert ",
    "{insert ",
    "{title}",
    "{description}",
    "{{",  # Jinja/mustache template
]

# Template indicators in filename
TEMPLATE_FILENAME_INDICATORS = ["template", "-template", "_template"]

# Index-like content indicators (titles that suggest index/list documents)
INDEX_TITLE_INDICATORS = [
    "decision approval record list",
    "energy system architecture - decision records",
    "list of decisions",
    "decision record list",
    "table of contents",
]


# =============================================================================
# Classifier Functions
# =============================================================================

@dataclass
class ClassificationResult:
    """Result of document classification."""
    doc_type: str
    confidence: str  # "filename", "title", "content", "default"
    reason: str


def classify_adr_document(
    file_path: str | Path,
    title: str = "",
    content: str = "",
) -> ClassificationResult:
    """Classify an ADR document based on filename, title, and content.

    Priority order:
    1. Filename pattern (most reliable)
    2. Title pattern
    3. Content indicators
    4. Default to 'adr'

    Args:
        file_path: Path to the document file
        title: Document title (optional, from first heading or frontmatter)
        content: Document content (optional, for template detection)

    Returns:
        ClassificationResult with doc_type, confidence level, and reason
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    file_name = file_path.name.lower()
    title_lower = title.lower() if title else ""
    content_lower = content.lower() if content else ""

    # 1. Check for Decision Approval Record (NNNND-*.md pattern)
    if DAR_FILENAME_PATTERN.match(file_name):
        return ClassificationResult(
            doc_type=DocType.ADR_APPROVAL,
            confidence="filename",
            reason=f"Filename matches DAR pattern: {file_name}"
        )

    # 2. Check for index files
    if file_name in INDEX_FILENAMES:
        return ClassificationResult(
            doc_type=DocType.INDEX,
            confidence="filename",
            reason=f"Filename is index file: {file_name}"
        )

    # 3. Check for template files (filename)
    if any(ind in file_name for ind in TEMPLATE_FILENAME_INDICATORS):
        return ClassificationResult(
            doc_type=DocType.TEMPLATE,
            confidence="filename",
            reason=f"Filename contains template indicator: {file_name}"
        )

    # 4. Check for template in title
    if "template" in title_lower:
        return ClassificationResult(
            doc_type=DocType.TEMPLATE,
            confidence="title",
            reason=f"Title contains 'template': {title}"
        )

    # 5. Check for index-like titles
    if any(ind in title_lower for ind in INDEX_TITLE_INDICATORS):
        return ClassificationResult(
            doc_type=DocType.INDEX,
            confidence="title",
            reason=f"Title indicates index document: {title}"
        )

    # 6. Check for template content indicators
    if content_lower:
        for indicator in TEMPLATE_CONTENT_INDICATORS:
            if indicator in content_lower:
                return ClassificationResult(
                    doc_type=DocType.TEMPLATE,
                    confidence="content",
                    reason=f"Content contains template indicator: {indicator}"
                )

    # 7. Default: actual ADR content
    return ClassificationResult(
        doc_type=DocType.ADR,
        confidence="default",
        reason="No special patterns detected, classified as ADR"
    )


def classify_principle_document(
    file_path: str | Path,
    title: str = "",
    content: str = "",
) -> ClassificationResult:
    """Classify a principle document based on filename, title, and content.

    Uses similar logic to ADR classification but with principle-specific types.

    Args:
        file_path: Path to the document file
        title: Document title (optional)
        content: Document content (optional)

    Returns:
        ClassificationResult with doc_type, confidence level, and reason
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    file_name = file_path.name.lower()
    title_lower = title.lower() if title else ""
    content_lower = content.lower() if content else ""

    # 1. Check for Decision Approval Record (NNNND-*.md pattern)
    # Principles can also have approval records
    if DAR_FILENAME_PATTERN.match(file_name):
        return ClassificationResult(
            doc_type=DocType.ADR_APPROVAL,  # Use same type for consistency
            confidence="filename",
            reason=f"Filename matches DAR pattern: {file_name}"
        )

    # 2. Check for index files
    if file_name in INDEX_FILENAMES:
        return ClassificationResult(
            doc_type=DocType.INDEX,
            confidence="filename",
            reason=f"Filename is index file: {file_name}"
        )

    # 3. Check for template files (filename)
    if any(ind in file_name for ind in TEMPLATE_FILENAME_INDICATORS):
        return ClassificationResult(
            doc_type=DocType.TEMPLATE,
            confidence="filename",
            reason=f"Filename contains template indicator: {file_name}"
        )

    # 4. Check for template in title
    if "template" in title_lower:
        return ClassificationResult(
            doc_type=DocType.TEMPLATE,
            confidence="title",
            reason=f"Title contains 'template': {title}"
        )

    # 5. Check for template content indicators
    if content_lower:
        for indicator in TEMPLATE_CONTENT_INDICATORS:
            if indicator in content_lower:
                return ClassificationResult(
                    doc_type=DocType.TEMPLATE,
                    confidence="content",
                    reason=f"Content contains template indicator: {indicator}"
                )

    # 6. Default: actual principle content
    return ClassificationResult(
        doc_type=DocType.PRINCIPLE,
        confidence="default",
        reason="No special patterns detected, classified as principle"
    )


def classify_document(
    file_path: str | Path,
    collection_type: str = "adr",
    title: str = "",
    content: str = "",
) -> ClassificationResult:
    """Unified classifier for any document type.

    Args:
        file_path: Path to the document file
        collection_type: "adr" or "principle"
        title: Document title (optional)
        content: Document content (optional)

    Returns:
        ClassificationResult with doc_type, confidence level, and reason
    """
    if collection_type.lower() in ("adr", "architecturaldecision"):
        return classify_adr_document(file_path, title, content)
    elif collection_type.lower() in ("principle", "principles"):
        return classify_principle_document(file_path, title, content)
    else:
        return ClassificationResult(
            doc_type=DocType.UNKNOWN,
            confidence="default",
            reason=f"Unknown collection type: {collection_type}"
        )


# =============================================================================
# Backward Compatibility
# =============================================================================

def doc_type_from_legacy(legacy_type: str) -> str:
    """Convert legacy doc_type values to canonical taxonomy.

    Legacy values from _classify_adr_document():
    - 'content' -> 'adr'
    - 'decision_approval_record' -> 'adr_approval'
    - 'template' -> 'template'
    - 'index' -> 'index'

    Args:
        legacy_type: Legacy doc_type value

    Returns:
        Canonical doc_type value
    """
    mapping = {
        "content": DocType.ADR,
        "decision_approval_record": DocType.ADR_APPROVAL,
        "template": DocType.TEMPLATE,
        "index": DocType.INDEX,
        # Pass-through for already canonical values
        "adr": DocType.ADR,
        "adr_approval": DocType.ADR_APPROVAL,
        "principle": DocType.PRINCIPLE,
    }
    return mapping.get(legacy_type, DocType.UNKNOWN)
