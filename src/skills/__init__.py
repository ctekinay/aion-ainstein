"""Skills framework for externalizing rules and thresholds.

This module provides the infrastructure for loading and managing
Agent Skills following the agentskills.io open standard format.

Usage:
    from src.skills import SkillLoader, SkillRegistry

    # Load a specific skill
    loader = SkillLoader()
    skill = loader.load_skill("rag-quality-assurance")
    content = skill.get_injectable_content()

    # Get thresholds
    thresholds = loader.get_thresholds("rag-quality-assurance")
    distance_threshold = thresholds["abstention"]["distance_threshold"]

    # Use registry for automatic skill activation
    registry = SkillRegistry()
    active_content = registry.get_all_skill_content(query="What ADRs exist?")
"""

from .loader import Skill, SkillLoader
from .registry import SkillRegistry, SkillRegistryEntry

__all__ = [
    "Skill",
    "SkillLoader",
    "SkillRegistry",
    "SkillRegistryEntry",
]
