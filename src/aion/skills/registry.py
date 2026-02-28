"""Skill registry for managing skill activation.

This module handles reading the skills-registry.yaml file and determining
which skills should be activated for a given query.
"""

import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

import yaml

from src.aion.skills.loader import SkillLoader, Skill, DEFAULT_SKILLS_DIR

logger = logging.getLogger(__name__)


@dataclass
class SkillRegistryEntry:
    """Entry in the skill registry."""

    name: str
    path: str
    description: str
    enabled: bool = True
    inject_into_tree: bool = True
    inject_mode: str = "always"  # "always" or "on_demand"
    tags: list[str] = field(default_factory=list)
    execution: str = "tree"  # "tree" or "generation"
    validation_tool: str = ""  # function name for post-generation validation


class SkillRegistry:
    """Manages skill registration and activation."""

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        loader: Optional[SkillLoader] = None
    ):
        self.skills_dir = skills_dir or DEFAULT_SKILLS_DIR
        self.loader = loader or SkillLoader(self.skills_dir)
        self._entries: dict[str, SkillRegistryEntry] = {}
        self._loaded = False

    def load_registry(self) -> bool:
        """Load the skill registry from skills-registry.yaml."""
        registry_path = self.skills_dir / "skills-registry.yaml"

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
                inject_into_tree=skill_data.get("inject_into_tree", True),
                inject_mode=skill_data.get("inject_mode", "always"),
                tags=skill_data.get("tags", []),
                execution=skill_data.get("execution", "tree"),
                validation_tool=skill_data.get("validation_tool", ""),
            )

            if entry.name:
                self._entries[entry.name] = entry
                logger.debug(f"Registered skill: {entry.name} (enabled={entry.enabled})")

        self._loaded = True
        logger.info(f"Loaded {len(self._entries)} skills from registry")
        return True

    def get_active_skills(self) -> list[Skill]:
        """Get all enabled skills."""
        if not self._loaded:
            self.load_registry()

        active_skills = []
        for name, entry in self._entries.items():
            if not entry.enabled:
                continue
            skill = self.loader.load_skill(name)
            if skill:
                active_skills.append(skill)

        return active_skills

    def is_skill_active(self, skill_name: str) -> bool:
        """Check if a specific skill is enabled."""
        if not self._loaded:
            self.load_registry()

        entry = self._entries.get(skill_name)
        return entry is not None and entry.enabled

    def get_all_skill_content(self) -> str:
        """Get combined content from all enabled skills for Tree prompt injection.

        Only includes skills where inject_into_tree is True (the default).
        Skills like persona-orchestrator set inject_into_tree: false because
        their content is consumed by a different component, not the Tree.

        Backward-compatible: returns only "always" skills (no on_demand).
        Use get_skill_content(active_tags) for conditional injection.
        """
        return self.get_skill_content(active_tags=None)

    def get_skill_content(self, active_tags: Sequence[str] | None = None) -> str:
        """Get skill content with conditional on-demand injection.

        Returns all inject_mode="always" skills. Additionally returns
        inject_mode="on_demand" skills whose tags overlap with active_tags.

        Args:
            active_tags: Tags from the Persona's skill_tags output.
                When None or empty, only "always" skills are returned.
        """
        if not self._loaded:
            self.load_registry()

        active_set = set(active_tags) if active_tags else set()
        parts = []

        for name, entry in self._entries.items():
            if not entry.enabled or not entry.inject_into_tree:
                continue

            if entry.inject_mode == "on_demand":
                # Only inject if tags overlap with active_tags
                if not active_set or not active_set.intersection(entry.tags):
                    continue

            skill = self.loader.load_skill(name)
            if skill:
                parts.append(skill.get_injectable_content())

        return "\n\n---\n\n".join(parts)

    def get_skill_entry(self, skill_name: str) -> Optional[SkillRegistryEntry]:
        """Get a registry entry by skill name."""
        if not self._loaded:
            self.load_registry()

        return self._entries.get(skill_name)

    def get_execution_model(self, skill_tags: Sequence[str]) -> str:
        """Determine execution model from active skill tags.

        Returns "generation" if any enabled on-demand skill whose tags match
        declares execution="generation". Otherwise returns "tree".
        """
        if not self._loaded:
            self.load_registry()

        if not skill_tags:
            return "tree"

        tag_set = set(skill_tags)
        for entry in self._entries.values():
            if not entry.enabled:
                continue
            if entry.execution != "generation":
                continue
            if tag_set.intersection(entry.tags):
                return "generation"

        return "tree"

    def get_generation_skill(self, skill_tags: Sequence[str]) -> Optional[SkillRegistryEntry]:
        """Find the generation skill entry matching the given tags.

        Returns the first enabled skill with execution="generation" whose
        tags overlap with skill_tags. Used by the generation pipeline to
        look up the validation_tool for the active skill.
        """
        if not self._loaded:
            self.load_registry()

        if not skill_tags:
            return None

        tag_set = set(skill_tags)
        for entry in self._entries.values():
            if not entry.enabled or entry.execution != "generation":
                continue
            if tag_set.intersection(entry.tags):
                return entry
        return None

    def list_skills(self) -> list[SkillRegistryEntry]:
        """List all registered skills."""
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
        """Update the enabled status of a skill in skills-registry.yaml.

        Uses targeted line editing to preserve comments and formatting.
        Creates a backup before making changes.
        """
        registry_path = self.skills_dir / "skills-registry.yaml"

        if not registry_path.exists():
            raise ValueError(f"Registry not found: {registry_path}")

        lines = registry_path.read_text(encoding="utf-8").splitlines(keepends=True)

        skill_found = False
        skill_name_line_idx = None
        enabled_line_indices = []
        in_target_skill = False

        for i, line in enumerate(lines):
            name_match = re.match(r'^(\s*)-\s*name:\s*["\']?([^"\'#\n]+)["\']?', line)
            if name_match:
                name = name_match.group(2).strip()
                if name == skill_name:
                    skill_found = True
                    in_target_skill = True
                    skill_name_line_idx = i
                elif in_target_skill:
                    break
                else:
                    in_target_skill = False

            if in_target_skill and i != skill_name_line_idx:
                enabled_match = re.match(
                    r'^(\s*)enabled:\s*(true|false)\s*(#.*)?$', line, re.IGNORECASE
                )
                if enabled_match:
                    enabled_line_indices.append(i)

        if not skill_found:
            raise ValueError(f"Skill not found in registry: {skill_name}")

        self._backup_registry(registry_path)

        enabled_value = "true" if enabled else "false"

        for idx in reversed(enabled_line_indices):
            del lines[idx]

        # Find correct insertion point
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
                    insert_idx = i
                    break

            if in_target_skill:
                if re.match(r'^\s*description:', line):
                    insert_idx = i + 1

        if insert_idx is None:
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

        registry_path.write_text("".join(lines), encoding="utf-8")

        if skill_name in self._entries:
            self._entries[skill_name].enabled = enabled

        logger.info(f"Set skill '{skill_name}' enabled={enabled}")
        return True

    def _backup_registry(self, registry_path: Path) -> str:
        """Create a backup of skills-registry.yaml before modifying."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = registry_path.with_suffix(f".yaml.bak.{timestamp}")
        simple_backup = registry_path.with_suffix(".yaml.bak")

        shutil.copy(registry_path, backup_path)
        shutil.copy(registry_path, simple_backup)

        self._cleanup_registry_backups(registry_path.parent)

        logger.debug(f"Created registry backup: {simple_backup}")
        return str(simple_backup)

    def _cleanup_registry_backups(self, directory: Path, keep_count: int = 5) -> None:
        """Remove old registry backup files, keeping only the most recent ones."""
        backups = []

        for backup_file in directory.glob("skills-registry.yaml.bak.*"):
            if backup_file.suffix == ".bak":
                continue
            backups.append(backup_file)

        backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for old_backup in backups[keep_count:]:
            try:
                old_backup.unlink()
            except OSError:
                pass


# Singleton instance
_global_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Get the global singleton SkillRegistry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry
