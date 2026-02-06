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
    skill_name: str = "rag-quality-assurance"
) -> Optional[Filter]:
    """Build Weaviate filter based on skill configuration and query intent.

    This implements the skills-based approach to DAR filtering:
    - By default: Exclude DARs, index files, templates
    - For approval queries: Include DARs to answer "who approved X?" questions

    Args:
        question: User's question
        skill_registry: SkillRegistry instance
        skill_name: Skill to load filter config from

    Returns:
        Weaviate Filter object, or None if no filtering needed
    """
    # Load filter configuration from skill
    skill = skill_registry.loader.load_skill(skill_name)
    filter_config = skill.config.get("filters", {})

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

    # Build filter: NOT in exclude list
    if not exclude_types:
        # No filtering - return all content
        return None

    # Build combined filter with NOT conditions
    filters = [Filter.by_property("doc_type").not_equal(t) for t in exclude_types]

    if len(filters) == 1:
        return filters[0]
    else:
        # Combine with AND logic
        combined = filters[0]
        for f in filters[1:]:
            combined = combined & f
        return combined
