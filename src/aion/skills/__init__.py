"""Skills framework for externalizing rules and thresholds.

This module provides the infrastructure for loading and managing
Agent Skills following the agentskills.io open standard format.

Usage:
    from aion.skills import DEFAULT_SKILL, get_skill_registry

    # The multi-plugin registry is the entry point. Per-plugin
    # SkillLoader/SkillRegistry instances are constructed internally from
    # each discovered plugin's paths — they are no longer instantiated
    # directly (both now require an explicit plugin skills_dir).
    registry = get_skill_registry()

    # All enabled skills across all plugins inject into every query
    active_content = registry.get_all_skill_content()

    # Resolve the owning plugin's loader for a single skill
    loader = registry.get_loader_for_skill(DEFAULT_SKILL)
    skill = loader.load_skill(DEFAULT_SKILL) if loader else None
"""

from aion.skills.loader import Skill, SkillLoader
from aion.skills.registry import (
    SkillRegistry,
    SkillRegistryEntry,
    get_skill_registry,
)

# Default skill name - single source of truth
DEFAULT_SKILL = "rag-quality-assurance"

__all__ = [
    "DEFAULT_SKILL",
    "Skill",
    "SkillLoader",
    "SkillRegistry",
    "SkillRegistryEntry",
    "get_skill_registry",
]
