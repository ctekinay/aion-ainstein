"""Skills-based document filtering for Weaviate queries.

This module provides dynamic filtering based on skill configuration,
replacing hardcoded filtering logic with externalized rules.

Canonical doc_type taxonomy (from Phase 2):
- adr: Architectural Decision Records
- adr_approval: ADR Decision Approval Records (NNNND-*.md in decisions/)
- principle: Principles
- principle_approval: Principle Decision Approval Records (NNNND-*.md in principles/)
- template: Template files
- index: Index/list files
- unknown: Unclassified
"""

import logging
from typing import List, Optional

from weaviate.classes.query import Filter

from ..doc_type_classifier import get_allowed_types_by_route

logger = logging.getLogger(__name__)


# =============================================================================
# Config-Driven Doc Type Constants
# =============================================================================

def _get_content_types(collection_type: str) -> List[str]:
    """Get allowed content types for a collection from config.

    Args:
        collection_type: 'adr' or 'principle'.

    Returns:
        List of allowed doc_type strings.
    """
    route = f"{collection_type}_content"
    return get_allowed_types_by_route(route)


# Backward-compatible module-level constants (resolved from config)
ADR_CONTENT_TYPES = ["adr", "content"]  # Fallback; prefer _get_content_types("adr")
PRINCIPLE_CONTENT_TYPES = ["principle", "content"]

# Types to exclude (for reference, loaded from config when available)
EXCLUDED_TYPES = ["adr_approval", "principle_approval", "template", "index"]


def build_document_filter(
    question: str,
    skill_registry,
    skill_name: str = "rag-quality-assurance",
    collection_type: str = "adr",
) -> Optional[Filter]:
    """Build Weaviate filter using allow-list approach with canonical doc_types.

    Uses positive filtering (doc_type == allowed_type) which:
    - Is more reliable than NOT_EQUAL (excludes null/missing values)
    - Works with both canonical (adr) and legacy (content) doc_type values
    - Supports approval/governance queries that need adr_approval data

    Args:
        question: User's question
        skill_registry: SkillRegistry instance
        skill_name: Skill to load filter config from
        collection_type: "adr" or "principle" (determines which types to include)

    Returns:
        Weaviate Filter object for allow-list filtering
    """
    # Determine base allowed types based on collection (loaded from config)
    if collection_type.lower() in ("adr", "architecturaldecision"):
        allowed_types = list(_get_content_types("adr"))
    elif collection_type.lower() in ("principle", "principles"):
        allowed_types = list(_get_content_types("principle"))
    else:
        # Generic: allow both
        allowed_types = list(set(_get_content_types("adr") + _get_content_types("principle")))

    # Load filter configuration from skill for approval query detection
    skill = skill_registry.loader.load_skill(skill_name)
    if skill is not None:
        filter_config = skill.thresholds.get("filters", {})
        include_dar_patterns = filter_config.get("include_dar_patterns", [])
        include_dar_keywords = filter_config.get("include_dar_keywords", [])

        question_lower = question.lower()

        # Check if query is about approvals/governance
        needs_dar = any(pattern.lower() in question_lower for pattern in include_dar_patterns)
        needs_dar = needs_dar or any(keyword.lower() in question_lower for keyword in include_dar_keywords)

        if needs_dar:
            # Include approval records for approval/governance queries
            allowed_types.append("adr_approval")
            allowed_types.append("principle_approval")
            logger.info("Query detected as approval/governance - including approval records")

    # Build allow-list filter: doc_type IN [allowed_types]
    logger.debug(f"Building allow-list filter for doc_types: {allowed_types}")

    filters = [Filter.by_property("doc_type").equal(t) for t in allowed_types]

    if len(filters) == 1:
        return filters[0]

    # Combine with OR logic (include if matches ANY allowed type)
    combined = filters[0]
    for f in filters[1:]:
        combined = combined | f

    return combined


# =============================================================================
# Intent-Aware Filtering (P5)
# =============================================================================

# Intent action → intent bucket mapping (uses canonical Intent enum values)
_INTENT_TO_BUCKET = {
    "semantic_answer": "direct_doc_summary",
    "lookup_doc": "direct_doc_summary",
    "lookup_approval": "approval_lookup",
    "list": "list_all",
    "meta": "meta_overview",
    "compare_concepts": "direct_doc_summary",
    "compare_counts": "direct_doc_summary",
    "count": "direct_doc_summary",
}


def _load_intent_filter_config() -> dict:
    """Load allowed_types_by_intent from taxonomy config.

    Returns:
        Dict mapping bucket name to {allow: [...], secondary: [...], deny: [...]}
    """
    try:
        from ..config import Settings
        config = Settings().get_taxonomy_config()
        return config.get("doc_types", {}).get("allowed_types_by_intent", {})
    except Exception:
        logger.debug("Could not load intent filter config from taxonomy")
        return {}


def build_intent_aware_filter(
    intent_action: str,
    collection_type: str = "adr",
    include_secondary: bool = False,
) -> Optional[Filter]:
    """Build Weaviate filter using intent-aware allow/deny rules.

    Reads allowed_types_by_intent from taxonomy config and builds
    a positive filter (doc_type IN allowed_types).

    Primary pass: only 'allow' types. Secondary pass (include_secondary=True):
    also includes 'secondary' types (e.g., registry for disambiguation).

    Args:
        intent_action: The classified intent (e.g., "semantic_answer", "list", "lookup_doc")
        collection_type: "adr" or "principle"
        include_secondary: If True, include secondary types (for disambiguation fallback)

    Returns:
        Weaviate Filter or None if no rules configured for this intent
    """
    config = _load_intent_filter_config()
    if not config:
        return None

    bucket = _INTENT_TO_BUCKET.get(intent_action)
    if not bucket or bucket not in config:
        return None

    bucket_config = config[bucket]
    allowed = list(bucket_config.get("allow", []))
    if include_secondary:
        allowed.extend(bucket_config.get("secondary", []))

    if not allowed:
        return None

    logger.debug(f"Intent-aware filter: intent={intent_action} bucket={bucket} types={allowed} secondary={include_secondary}")

    filters = [Filter.by_property("doc_type").equal(t) for t in allowed]
    if len(filters) == 1:
        return filters[0]

    combined = filters[0]
    for f in filters[1:]:
        combined = combined | f
    return combined


def build_adr_filter(
    question: str = "",
    skill_registry = None,
    skill_name: str = "rag-quality-assurance",
) -> Filter:
    """Build filter specifically for ADR queries.

    Convenience function for ADR listing that uses allow-list filtering.

    Args:
        question: Optional question for approval query detection
        skill_registry: Optional skill registry for config
        skill_name: Skill to load config from

    Returns:
        Filter for doc_type == "adr" OR doc_type == "content"
    """
    if skill_registry:
        return build_document_filter(
            question=question,
            skill_registry=skill_registry,
            skill_name=skill_name,
            collection_type="adr",
        )

    # Fallback: simple allow-list without skill config
    return (
        Filter.by_property("doc_type").equal("adr") |
        Filter.by_property("doc_type").equal("content")
    )


def build_principle_filter(
    question: str = "",
    skill_registry = None,
    skill_name: str = "rag-quality-assurance",
) -> Filter:
    """Build filter specifically for Principle queries.

    Convenience function for principle listing that uses allow-list filtering.

    Args:
        question: Optional question for approval query detection
        skill_registry: Optional skill registry for config
        skill_name: Skill to load config from

    Returns:
        Filter for doc_type == "principle" OR doc_type == "content"
    """
    if skill_registry:
        return build_document_filter(
            question=question,
            skill_registry=skill_registry,
            skill_name=skill_name,
            collection_type="principle",
        )

    # Fallback: simple allow-list without skill config
    return (
        Filter.by_property("doc_type").equal("principle") |
        Filter.by_property("doc_type").equal("content")
    )
