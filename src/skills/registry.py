"""Skill registry for managing skill activation.

This module handles reading the registry.yaml file and determining
which skills should be activated for a given query.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .loader import SkillLoader, Skill, DEFAULT_SKILLS_DIR

logger = logging.getLogger(__name__)


@dataclass
class SkillRegistryEntry:
    """Entry in the skill registry."""

    name: str
    path: str
    description: str
    enabled: bool = True
    auto_activate: bool = False
    triggers: list[str] = field(default_factory=list)


class SkillRegistry:
    """Manages skill registration and activation."""

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        loader: Optional[SkillLoader] = None
    ):
        """Initialize the skill registry.

        Args:
            skills_dir: Path to skills directory
            loader: Optional SkillLoader instance (creates one if not provided)
        """
        self.skills_dir = skills_dir or DEFAULT_SKILLS_DIR
        self.loader = loader or SkillLoader(self.skills_dir)
        self._entries: dict[str, SkillRegistryEntry] = {}
        self._loaded = False

    def load_registry(self) -> bool:
        """Load the skill registry from registry.yaml.

        Loads ALL skills (enabled and disabled) for listing purposes.
        Use get_active_skills() to get only enabled skills that should activate.

        Returns:
            True if loaded successfully, False otherwise
        """
        registry_path = self.skills_dir / "registry.yaml"

        if not registry_path.exists():
            logger.warning(f"Registry not found: {registry_path}")
            return False

        try:
            content = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to parse registry: {e}")
            return False

        if not content or "skills" not in content:
            logger.warning("Empty or invalid registry format")
            return False

        self._entries.clear()

        for skill_data in content.get("skills", []):
            entry = SkillRegistryEntry(
                name=skill_data.get("name", ""),
                path=skill_data.get("path", ""),
                description=skill_data.get("description", ""),
                enabled=skill_data.get("enabled", True),
                auto_activate=skill_data.get("auto_activate", False),
                triggers=skill_data.get("triggers", []),
            )

            # Load ALL skills (enabled and disabled) for listing
            if entry.name:
                self._entries[entry.name] = entry
                logger.debug(f"Registered skill: {entry.name} (enabled={entry.enabled})")

        self._loaded = True
        logger.info(f"Loaded {len(self._entries)} skills from registry")
        return True

    def get_active_skills(self, query: str = "") -> list[Skill]:
        """Get skills that should be active for a query.

        Only returns enabled skills that match activation criteria.

        Args:
            query: The user's query (used for trigger matching)

        Returns:
            List of Skill objects that should be activated
        """
        if not self._loaded:
            self.load_registry()

        active_skills = []
        query_lower = query.lower()

        for name, entry in self._entries.items():
            # Skip disabled skills
            if not entry.enabled:
                continue

            should_activate = False

            # Auto-activate skills always activate
            if entry.auto_activate:
                should_activate = True

            # Check triggers if not auto-activated
            if not should_activate and entry.triggers:
                for trigger in entry.triggers:
                    if trigger.lower() in query_lower:
                        should_activate = True
                        logger.debug(f"Skill {name} triggered by: {trigger}")
                        break

            if should_activate:
                skill = self.loader.load_skill(name)
                if skill:
                    active_skills.append(skill)

        return active_skills

    def get_all_skill_content(self, query: str = "") -> str:
        """Get combined content from all active skills.

        Args:
            query: The user's query (used for trigger matching)

        Returns:
            Combined skill content for prompt injection
        """
        skills = self.get_active_skills(query)

        if not skills:
            return ""

        parts = []
        for skill in skills:
            parts.append(skill.get_injectable_content())

        return "\n\n---\n\n".join(parts)

    def get_skill_entry(self, skill_name: str) -> Optional[SkillRegistryEntry]:
        """Get a registry entry by skill name.

        Args:
            skill_name: Name of the skill

        Returns:
            SkillRegistryEntry or None
        """
        if not self._loaded:
            self.load_registry()

        return self._entries.get(skill_name)

    def list_skills(self) -> list[SkillRegistryEntry]:
        """List all registered skills.

        Returns:
            List of all SkillRegistryEntry objects
        """
        if not self._loaded:
            self.load_registry()

        return list(self._entries.values())

    def reload(self):
        """Reload the registry and clear caches."""
        self._loaded = False
        self._entries.clear()
        self.loader.clear_cache()
        self.load_registry()

    def set_skill_enabled(self, skill_name: str, enabled: bool) -> bool:
        """Update the enabled status of a skill in registry.yaml.

        Args:
            skill_name: Name of the skill to update
            enabled: New enabled status

        Returns:
            True if updated successfully, False otherwise

        Raises:
            ValueError: If skill not found
        """
        registry_path = self.skills_dir / "registry.yaml"

        if not registry_path.exists():
            raise ValueError(f"Registry not found: {registry_path}")

        try:
            content = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(f"Failed to parse registry: {e}")

        if not content or "skills" not in content:
            raise ValueError("Empty or invalid registry format")

        # Find and update the skill
        skill_found = False
        for skill_data in content.get("skills", []):
            if skill_data.get("name") == skill_name:
                skill_data["enabled"] = enabled
                skill_found = True
                break

        if not skill_found:
            raise ValueError(f"Skill not found in registry: {skill_name}")

        # Write back to file
        registry_path.write_text(
            yaml.dump(content, default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8"
        )

        # Update in-memory entry
        if skill_name in self._entries:
            self._entries[skill_name].enabled = enabled

        logger.info(f"Set skill '{skill_name}' enabled={enabled}")
        return True
