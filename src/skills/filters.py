"""Skills-based document filtering for Weaviate queries.

This module provides dynamic filtering based on skill configuration,
replacing hardcoded filtering logic with externalized rules.
"""

import logging
from typing import Optional

from weaviate.classes.query import Filter

logger = logging.getLogger(__name__)


def build_document_filter(
    question: str,
    skill_registry,
    skill_name: str = "rag-quality-assurance",
    use_positive_filter: bool = True
) -> Optional[Filter]:
    """Build Weaviate filter based on skill configuration and query intent.

    This implements the skills-based approach to DAR filtering:
    - By default: Include only 'content' doc_type (actual ADRs, principles, etc.)
    - For approval queries: Also include 'decision_approval_record' to answer "who approved X?"

    Args:
        question: User's question
        skill_registry: SkillRegistry instance
        skill_name: Skill to load filter config from
        use_positive_filter: If True, use EQUAL filter for allowed types (more reliable).
                            If False, use NOT_EQUAL for excluded types (legacy behavior).

    Returns:
        Weaviate Filter object, or None if no filtering needed
    """
    # Load filter configuration from skill
    skill = skill_registry.loader.load_skill(skill_name)
    if skill is None:
        logger.warning(f"Skill '{skill_name}' not found, using default filters")
        filter_config = {}
    else:
        filter_config = skill.thresholds.get("filters", {})

    exclude_types = filter_config.get("exclude_doc_types", [
        "decision_approval_record",
        "index",
        "template"
    ])

    # Check if this query needs DAR data (approval/governance questions)
    include_dar_patterns = filter_config.get("include_dar_patterns", [])
    include_dar_keywords = filter_config.get("include_dar_keywords", [])

    question_lower = question.lower()

    # Check if query is about approvals/governance
    needs_dar = any(pattern.lower() in question_lower for pattern in include_dar_patterns)
    needs_dar = needs_dar or any(keyword.lower() in question_lower for keyword in include_dar_keywords)

    if needs_dar:
        # Include DARs for approval queries, but still exclude index/template
        exclude_types = [t for t in exclude_types if t != "decision_approval_record"]
        logger.info(f"Query detected as approval/governance - including DARs in retrieval")

    # Use positive filter approach: EQUAL for allowed types
    # This is more reliable because documents with null/missing doc_type are excluded
    if use_positive_filter:
        # Determine which doc_types to include
        all_types = ["content", "decision_approval_record", "index", "template"]
        include_types = [t for t in all_types if t not in exclude_types]

        if not include_types:
            # No types to include - shouldn't happen normally
            logger.warning("No doc_types to include after filtering - returning None")
            return None

        if len(include_types) == len(all_types):
            # All types included - no filtering needed
            return None

        # Build positive filter: doc_type IN [allowed types]
        # Using OR of EQUAL conditions
        logger.debug(f"Building positive filter for doc_types: {include_types}")
        filters = [Filter.by_property("doc_type").equal(t) for t in include_types]

        if len(filters) == 1:
            return filters[0]
        else:
            # Combine with OR logic (include if matches ANY allowed type)
            combined = filters[0]
            for f in filters[1:]:
                combined = combined | f
            return combined

    # Legacy behavior: NOT_EQUAL for excluded types
    # This has issues with null/missing doc_type values
    if not exclude_types:
        # No filtering - return all content
        return None

    # Build combined filter with NOT conditions
    logger.debug(f"Building negative filter excluding doc_types: {exclude_types}")
    filters = [Filter.by_property("doc_type").not_equal(t) for t in exclude_types]

    if len(filters) == 1:
        return filters[0]
    else:
        # Combine with AND logic
        combined = filters[0]
        for f in filters[1:]:
            combined = combined & f
        return combined
