"""Document type classification for ADRs and principles.

Canonical taxonomy for doc_type:
- adr: Actual Architectural Decision Records (NNNN-*.md)
- adr_approval: Decision Approval Records (DACI approval tracking, NNNND-*.md)
- principle: Actual Architecture Principles (NNNN-*.md)
- principle_approval: Principle Approval Records (NNNND-*.md)
- template: Template files with placeholders
- index: Index/list files INSIDE decisions/ and principles/ directories (index.md, readme.md)
- registry: Top-level doc registry (esa_doc_registry.md) - human-authored, canonical
- unknown: Unclassified documents

=============================================================================
DETERMINISTIC INGESTION RULES
=============================================================================

ALWAYS SKIP at ingestion (doc_type in SKIP_DOC_TYPES_AT_INGESTION):
  - template: adr-template.md, adr-decision-template.md, principle-template.md, etc.
  - index: any index.md inside .../decisions/ or .../principles/

ALWAYS INGEST (embedded in vector store):
  - adr: Content files matching NNNN-*.md (e.g., 0025-use-oauth.md)
  - adr_approval: DAR files matching NNNND-*.md (e.g., 0025D-approval.md)
  - principle: Content files matching NNNN-*.md (e.g., 0010-eventual-consistency.md)
  - principle_approval: Principle DAR files matching NNNND-*.md
  - registry: esa_doc_registry.md (doc_type="registry", intentionally ingested for
    reference but can be excluded at query time)

REGISTRY HANDLING:
  - The file esa_doc_registry.md is the renamed /doc/index.md
  - It is NOT matched as "index" (to avoid skip logic)
  - It CAN be ingested (doc_type="registry") for system reference
  - Query-time filtering can exclude it if not relevant to user queries

This module provides deterministic classification based on:
1. Filename patterns (most reliable)
2. Title patterns
3. Content indicators (fallback)
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Canonical Document Types
# =============================================================================

class DocType:
    """Canonical document type constants."""
    ADR = "adr"
    ADR_APPROVAL = "adr_approval"
    TEMPLATE = "template"
    INDEX = "index"
    REGISTRY = "registry"  # Top-level doc registry (esa_doc_registry.md)
    UNKNOWN = "unknown"

    # For principles (using same taxonomy pattern)
    PRINCIPLE = "principle"
    PRINCIPLE_APPROVAL = "principle_approval"

    @classmethod
    def all_types(cls) -> list[str]:
        """Return all valid document types."""
        return [cls.ADR, cls.ADR_APPROVAL, cls.TEMPLATE, cls.INDEX, cls.REGISTRY, cls.UNKNOWN]

    @classmethod
    def content_types(cls) -> list[str]:
        """Return types that contain actual content (for querying)."""
        return [cls.ADR, cls.PRINCIPLE]

    @classmethod
    def skip_at_ingestion_types(cls) -> list[str]:
        """Return types that should be skipped at ingestion time.

        These are NOT embedded in the vector store:
        - template: Placeholder files, not actual content
        - index: Directory indexes inside decisions/ and principles/

        Note: registry (esa_doc_registry.md) is NOT skipped - it's the canonical
        doc registry and may be intentionally ingested for reference.
        """
        return [cls.TEMPLATE, cls.INDEX]

    @classmethod
    def excluded_types(cls) -> list[str]:
        """Return types typically excluded from list queries at query time.

        These may be ingested but excluded from most user queries:
        - adr_approval: DARs are only shown for approval-related queries
        - template: Should not be in store, but filter as fallback
        - index: Should not be in store, but filter as fallback
        - registry: May be excluded from content queries
        """
        return [cls.ADR_APPROVAL, cls.TEMPLATE, cls.INDEX, cls.REGISTRY]


# =============================================================================
# Classification Patterns (loaded from config with hardcoded fallbacks)
# =============================================================================

def _get_identity_config() -> dict:
    """Load identity configuration from taxonomy config."""
    try:
        from .config import settings
        return settings.get_taxonomy_config().get("identity", {})
    except Exception:
        return {}


def _get_dar_filename_pattern() -> re.Pattern:
    """Get DAR filename pattern from config."""
    identity = _get_identity_config()
    pattern = identity.get("patterns", {}).get("dar_filename", r"^\d{4}[dD]-")
    return re.compile(pattern, re.IGNORECASE)


def _get_index_filenames() -> frozenset:
    """Get index filenames from config."""
    identity = _get_identity_config()
    defaults = ["index.md", "_index.md", "readme.md", "overview.md"]
    return frozenset(identity.get("index_filenames", defaults))


def _get_registry_filenames() -> frozenset:
    """Get registry filenames from config."""
    identity = _get_identity_config()
    defaults = ["esa_doc_registry.md", "esa-doc-registry.md"]
    return frozenset(identity.get("registry_filenames", defaults))


def _get_template_filename_indicators() -> list:
    """Get template filename indicators from config."""
    identity = _get_identity_config()
    defaults = ["template", "-template", "_template"]
    return identity.get("template_filename_indicators", defaults)


def _get_template_content_indicators() -> list:
    """Get template content indicators from config."""
    identity = _get_identity_config()
    defaults = [
        "{short title", "{problem statement}", "{context}",
        "{decision outcome}", "[insert ", "{insert ",
        "{title}", "{description}", "{{",
    ]
    return identity.get("template_content_indicators", defaults)


def _get_index_title_indicators() -> list:
    """Get index title indicators from config."""
    identity = _get_identity_config()
    defaults = [
        "decision approval record list",
        "energy system architecture - decision records",
        "list of decisions",
        "decision record list",
        "table of contents",
    ]
    return identity.get("index_title_indicators", defaults)


# Module-level constants (initialized from config, importable by other modules)
DAR_FILENAME_PATTERN = _get_dar_filename_pattern()
INDEX_FILENAMES = _get_index_filenames()
REGISTRY_FILENAMES = _get_registry_filenames()
TEMPLATE_CONTENT_INDICATORS = _get_template_content_indicators()
TEMPLATE_FILENAME_INDICATORS = _get_template_filename_indicators()
INDEX_TITLE_INDICATORS = _get_index_title_indicators()


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

    # 2. Check for registry files (NOT skipped - canonical doc registry)
    if file_name in REGISTRY_FILENAMES:
        return ClassificationResult(
            doc_type=DocType.REGISTRY,
            confidence="filename",
            reason=f"Filename is registry file: {file_name}"
        )

    # 3. Check for index files (SKIPPED at ingestion)
    if file_name in INDEX_FILENAMES:
        return ClassificationResult(
            doc_type=DocType.INDEX,
            confidence="filename",
            reason=f"Filename is index file: {file_name}"
        )

    # 4. Check for template files (filename)
    if any(ind in file_name for ind in TEMPLATE_FILENAME_INDICATORS):
        return ClassificationResult(
            doc_type=DocType.TEMPLATE,
            confidence="filename",
            reason=f"Filename contains template indicator: {file_name}"
        )

    # 5. Check for template in title
    if "template" in title_lower:
        return ClassificationResult(
            doc_type=DocType.TEMPLATE,
            confidence="title",
            reason=f"Title contains 'template': {title}"
        )

    # 6. Check for index-like titles
    if any(ind in title_lower for ind in INDEX_TITLE_INDICATORS):
        return ClassificationResult(
            doc_type=DocType.INDEX,
            confidence="title",
            reason=f"Title indicates index document: {title}"
        )

    # 7. Check for template content indicators
    if content_lower:
        for indicator in TEMPLATE_CONTENT_INDICATORS:
            if indicator in content_lower:
                return ClassificationResult(
                    doc_type=DocType.TEMPLATE,
                    confidence="content",
                    reason=f"Content contains template indicator: {indicator}"
                )

    # 8. Default: actual ADR content
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

    # 2. Check for registry files (NOT skipped - canonical doc registry)
    if file_name in REGISTRY_FILENAMES:
        return ClassificationResult(
            doc_type=DocType.REGISTRY,
            confidence="filename",
            reason=f"Filename is registry file: {file_name}"
        )

    # 3. Check for index files (SKIPPED at ingestion)
    if file_name in INDEX_FILENAMES:
        return ClassificationResult(
            doc_type=DocType.INDEX,
            confidence="filename",
            reason=f"Filename is index file: {file_name}"
        )

    # 4. Check for template files (filename)
    if any(ind in file_name for ind in TEMPLATE_FILENAME_INDICATORS):
        return ClassificationResult(
            doc_type=DocType.TEMPLATE,
            confidence="filename",
            reason=f"Filename contains template indicator: {file_name}"
        )

    # 5. Check for template in title
    if "template" in title_lower:
        return ClassificationResult(
            doc_type=DocType.TEMPLATE,
            confidence="title",
            reason=f"Title contains 'template': {title}"
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

    # 7. Default: actual principle content
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
        "registry": DocType.REGISTRY,
        # Pass-through for already canonical values
        "adr": DocType.ADR,
        "adr_approval": DocType.ADR_APPROVAL,
        "principle": DocType.PRINCIPLE,
    }
    return mapping.get(legacy_type, DocType.UNKNOWN)


def resolve_legacy_doc_type(legacy_type: str, collection_type: str) -> str:
    """Context-aware resolution of legacy doc_type values.

    Handles `decision_approval_record` differently based on collection_type:
    - In ADR collection → `adr_approval`
    - In Principle collection → `principle_approval`

    All resolutions are logged for observability. In `esa_strict` mode,
    unknown types raise ValueError; in `portable` mode, they resolve to `unknown`.

    Args:
        legacy_type: The raw doc_type value from data.
        collection_type: Explicit collection context ('adr' or 'principle').

    Returns:
        Canonical doc_type string.
    """
    from .config import settings

    # Canonical values pass through
    canonical = {
        "adr", "adr_approval", "principle", "principle_approval",
        "content", "template", "index", "registry", "unknown",
    }
    if legacy_type in canonical:
        return legacy_type

    # Context-aware alias resolution
    if legacy_type == "decision_approval_record":
        if collection_type.lower() in ("adr", "architecturaldecision"):
            resolved = "adr_approval"
        elif collection_type.lower() in ("principle", "principles"):
            resolved = "principle_approval"
        else:
            resolved = "adr_approval"  # default context
        logger.info(
            "Legacy doc_type '%s' resolved to '%s' (collection: %s)",
            legacy_type, resolved, collection_type,
        )
        return resolved

    # Load aliases from config for extensibility
    taxonomy = settings.get_taxonomy_config()
    aliases = taxonomy.get("doc_types", {}).get("aliases", {})
    if legacy_type in aliases:
        alias_map = aliases[legacy_type]
        if isinstance(alias_map, dict):
            resolved = alias_map.get(collection_type.lower(), list(alias_map.values())[0])
        else:
            resolved = alias_map
        logger.info(
            "Legacy doc_type '%s' resolved to '%s' (collection: %s)",
            legacy_type, resolved, collection_type,
        )
        return resolved

    # Unknown type handling
    if settings.mode == "esa_strict":
        raise ValueError(
            f"Unknown doc_type '{legacy_type}' in esa_strict mode "
            f"(collection: {collection_type})"
        )

    logger.warning(
        "Unknown doc_type '%s' resolved to 'unknown' in portable mode (collection: %s)",
        legacy_type, collection_type,
    )
    return DocType.UNKNOWN


def get_allowed_types_by_route(route_name: str) -> List[str]:
    """Get allowed doc_types for a route from config.

    Falls back to hardcoded defaults if config is unavailable.

    Args:
        route_name: Route key (e.g., 'adr_content', 'principle_content',
                    'excluded_from_list').

    Returns:
        List of canonical doc_type strings.
    """
    from .config import settings

    # Hardcoded defaults matching current behavior
    defaults: Dict[str, List[str]] = {
        "adr_content": ["adr", "content"],
        "principle_content": ["principle", "content"],
        "adr_approval": ["adr_approval"],
        "principle_approval": ["principle_approval"],
        "excluded_from_list": [
            "adr_approval", "principle_approval", "template",
            "index", "registry", "unknown",
        ],
    }

    taxonomy = settings.get_taxonomy_config()
    config_routes = taxonomy.get("doc_types", {}).get("allowed_types_by_route", {})

    return config_routes.get(route_name, defaults.get(route_name, []))
