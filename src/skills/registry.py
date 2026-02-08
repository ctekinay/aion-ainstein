"""Skill registry for managing skill activation.

This module handles reading the registry.yaml file and determining
which skills should be activated for a given query.
"""

import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from .loader import SkillLoader, Skill, DEFAULT_SKILLS_DIR

logger = logging.getLogger(__name__)

# Global singleton instance for sharing registry state across modules
_global_registry: Optional["SkillRegistry"] = None


def get_skill_registry() -> "SkillRegistry":
    """Get the global SkillRegistry singleton instance.

    This ensures all modules share the same registry state,
    so changes (like enable/disable) propagate everywhere.

    Returns:
        The shared SkillRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry


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

    def is_skill_active(self, skill_name: str, query: str = "") -> bool:
        """Check if a specific skill is active for a given query.

        This is used to determine mode switches (e.g., structured_mode when
        response-contract is active) without loading all skill content.

        Args:
            skill_name: Name of the skill to check
            query: The user's query (used for trigger matching)

        Returns:
            True if the skill would be activated for this query
        """
        if not self._loaded:
            self.load_registry()

        entry = self._entries.get(skill_name)
        if not entry or not entry.enabled:
            return False

        # Auto-activate skills always activate
        if entry.auto_activate:
            return True

        # Check triggers
        query_lower = query.lower()
        for trigger in entry.triggers:
            if trigger.lower() in query_lower:
                logger.debug(f"Skill {skill_name} would activate via trigger: {trigger}")
                return True

        return False

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

        Uses targeted line editing to preserve comments and formatting.
        Creates a backup before making changes.

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

        # Read file as lines to preserve comments and formatting
        lines = registry_path.read_text(encoding="utf-8").splitlines(keepends=True)

        # Find the skill section and collect ALL enabled lines for this skill
        skill_found = False
        skill_name_line_idx = None
        enabled_line_indices = []  # Collect ALL enabled lines for this skill
        in_target_skill = False
        skill_indent = None

        for i, line in enumerate(lines):
            # Check for skill name entry (e.g., "  - name: skill-name")
            name_match = re.match(r'^(\s*)-\s*name:\s*["\']?([^"\'#\n]+)["\']?', line)
            if name_match:
                indent = name_match.group(1)
                name = name_match.group(2).strip()
                if name == skill_name:
                    skill_found = True
                    in_target_skill = True
                    skill_indent = len(indent)
                    skill_name_line_idx = i
                elif in_target_skill:
                    # We've moved to a different skill, stop looking
                    break
                else:
                    in_target_skill = False

            # If we're in the target skill, collect ALL enabled lines
            if in_target_skill and i != skill_name_line_idx:
                enabled_match = re.match(r'^(\s*)enabled:\s*(true|false)\s*(#.*)?$', line, re.IGNORECASE)
                if enabled_match:
                    enabled_line_indices.append(i)

        if not skill_found:
            raise ValueError(f"Skill not found in registry: {skill_name}")

        # Create backup before modifying
        self._backup_registry(registry_path)

        enabled_value = "true" if enabled else "false"

        # Remove ALL existing enabled lines for this skill (in reverse order to preserve indices)
        for idx in reversed(enabled_line_indices):
            del lines[idx]

        # Now insert a single enabled line after the "enabled:" field position
        # Find the correct position: after description or path, before auto_activate or triggers
        insert_idx = None
        in_target_skill = False

        for i, line in enumerate(lines):
            name_match = re.match(r'^(\s*)-\s*name:\s*["\']?([^"\'#\n]+)["\']?', line)
            if name_match:
                name = name_match.group(2).strip()
                if name == skill_name:
                    in_target_skill = True
                    continue
                elif in_target_skill:
                    # Next skill started, insert before this line
                    insert_idx = i
                    break

            if in_target_skill:
                # Look for auto_activate or triggers to insert before them
                if re.match(r'^\s*auto_activate:', line) or re.match(r'^\s*triggers:', line):
                    insert_idx = i
                    break
                # Track position after description
                if re.match(r'^\s*description:', line):
                    insert_idx = i + 1

        # If we didn't find a good position, insert after description
        if insert_idx is None:
            # Find description line and insert after it
            in_target_skill = False
            for i, line in enumerate(lines):
                name_match = re.match(r'^(\s*)-\s*name:\s*["\']?([^"\'#\n]+)["\']?', line)
                if name_match and name_match.group(2).strip() == skill_name:
                    in_target_skill = True
                    continue
                if in_target_skill and re.match(r'^\s*description:', line):
                    insert_idx = i + 1
                    break

        if insert_idx is not None:
            lines.insert(insert_idx, f"    enabled: {enabled_value}\n")

        # Write back to file
        registry_path.write_text("".join(lines), encoding="utf-8")

        # Update in-memory entry
        if skill_name in self._entries:
            self._entries[skill_name].enabled = enabled

        logger.info(f"Set skill '{skill_name}' enabled={enabled}")
        return True

    def _backup_registry(self, registry_path: Path) -> str:
        """Create a backup of registry.yaml before modifying.

        Args:
            registry_path: Path to registry.yaml

        Returns:
            Path to the backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = registry_path.with_suffix(f".yaml.bak.{timestamp}")
        simple_backup = registry_path.with_suffix(".yaml.bak")

        shutil.copy(registry_path, backup_path)
        shutil.copy(registry_path, simple_backup)

        # Clean up old timestamped backups (keep last 5)
        self._cleanup_registry_backups(registry_path.parent)

        logger.debug(f"Created registry backup: {simple_backup}")
        return str(simple_backup)

    def _cleanup_registry_backups(self, directory: Path, keep_count: int = 5) -> None:
        """Remove old registry backup files, keeping only the most recent ones.

        Args:
            directory: Directory containing backup files
            keep_count: Number of backups to keep
        """
        backup_pattern = "registry.yaml.bak.*"
        backups = []

        for backup_file in directory.glob(backup_pattern):
            # Skip the simple .bak file
            if backup_file.suffix == ".bak":
                continue
            backups.append(backup_file)

        # Sort by modification time (newest first)
        backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # Remove old backups beyond keep_count
        for old_backup in backups[keep_count:]:
            try:
                old_backup.unlink()
            except OSError:
                pass


# Singleton instance - import this instead of creating new instances
_global_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Get the global singleton SkillRegistry instance.

    This ensures all parts of the application share the same registry state,
    fixing the bug where toggling enabled/disabled in the UI didn't affect the RAG system.

    Returns:
        The global SkillRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry
