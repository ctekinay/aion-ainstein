"""Skills framework for externalizing rules and thresholds.

This module provides the infrastructure for loading and managing
Agent Skills following the agentskills.io open standard format.

Usage:
    from src.skills import SkillLoader, SkillRegistry, DEFAULT_SKILL

    # Load a specific skill
    loader = SkillLoader()
    skill = loader.load_skill(DEFAULT_SKILL)
    content = skill.get_injectable_content()

    # Get thresholds
    thresholds = loader.get_thresholds(DEFAULT_SKILL)
    distance_threshold = thresholds["abstention"]["distance_threshold"]

    # Use registry for automatic skill activation
    registry = SkillRegistry()
    active_content = registry.get_all_skill_content(query="What ADRs exist?")
"""

from .loader import Skill, SkillLoader
from .registry import SkillRegistry, SkillRegistryEntry, get_skill_registry
from .filters import build_document_filter, build_intent_aware_filter

# Default skill name - single source of truth
DEFAULT_SKILL = "rag-quality-assurance"

__all__ = [
    "DEFAULT_SKILL",
    "Skill",
    "SkillLoader",
    "SkillRegistry",
    "SkillRegistryEntry",
    "get_skill_registry",
    "build_document_filter",
    "build_intent_aware_filter",
]
