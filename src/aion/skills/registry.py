"""Skill registry for managing skill activation.

This module handles reading the skills-registry.yaml file and determining
which skills should be activated for a given query.
"""

from __future__ import annotations

import logging
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from aion.skills.loader import DEFAULT_SKILLS_DIR, Skill, SkillLoader

if TYPE_CHECKING:
    from aion.routing import ExecutionModel

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
    execution: str = "tree"  # "tree", "generation", "vocabulary", or "archimate"
    validation_tool: str = ""  # function name for post-generation validation
    group: str = ""  # group name, or "" if ungrouped
    type: str = "skill"  # "skill" (has SKILL.md) or "references" (references/ dir only)
    load_order: int = 0  # sort order within group (lower = loaded first into context)


@dataclass
class SkillGroupEntry:
    """A skill group — display/loading concept only.

    Groups are a registry/UI concept: related skills declared as a unit,
    enabled/disabled together. Internally, members are flattened into
    _entries with inherited group properties. The injection path
    (get_skill_content) does not know about groups.
    """

    name: str
    description: str
    enabled: bool = True
    skills: list[str] = field(default_factory=list)
    shared_references: str = ""  # skill folder name whose references/ are merged into members


class SkillRegistry:
    """Manages skill registration and activation."""

    def __init__(
        self,
        skills_dir: Path | None = None,
        loader: SkillLoader | None = None
    ):
        self.skills_dir = skills_dir or DEFAULT_SKILLS_DIR
        self.loader = loader or SkillLoader(self.skills_dir)
        self._entries: dict[str, SkillRegistryEntry] = {}
        self._groups: dict[str, SkillGroupEntry] = {}
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

        if not content or ("skills" not in content and "groups" not in content):
            logger.warning("Empty or invalid registry format")
            return False

        self._entries.clear()
        self._groups.clear()

        # Process groups first — members inherit group-level properties
        for group_data in content.get("groups", []):
            group_name = group_data.get("name", "")
            if not group_name:
                continue

            group = SkillGroupEntry(
                name=group_name,
                description=group_data.get("description", ""),
                enabled=group_data.get("enabled", True),
                skills=[],
                shared_references=group_data.get("shared_references", ""),
            )

            # Group-level defaults inherited by members
            group_defaults = {
                "enabled": group_data.get("enabled", True),
                "inject_into_tree": group_data.get("inject_into_tree", True),
                "inject_mode": group_data.get("inject_mode", "always"),
                "tags": group_data.get("tags", []),
            }

            for skill_data in group_data.get("skills", []):
                entry = SkillRegistryEntry(
                    name=skill_data.get("name", ""),
                    path=skill_data.get("path", ""),
                    description=skill_data.get("description", ""),
                    enabled=skill_data.get("enabled", group_defaults["enabled"]),
                    inject_into_tree=skill_data.get(
                        "inject_into_tree", group_defaults["inject_into_tree"]
                    ),
                    inject_mode=skill_data.get(
                        "inject_mode", group_defaults["inject_mode"]
                    ),
                    tags=skill_data.get("tags", group_defaults["tags"]),
                    execution=skill_data.get("execution", "tree"),
                    validation_tool=skill_data.get("validation_tool", ""),
                    group=group_name,
                    type=skill_data.get("type", "skill"),
                    load_order=skill_data.get("load_order", 0),
                )
                if entry.name:
                    self._entries[entry.name] = entry
                    group.skills.append(entry.name)
                    logger.debug(
                        f"Registered skill: {entry.name} "
                        f"(group={group_name}, enabled={entry.enabled})"
                    )

            self._groups[group_name] = group

        # Process ungrouped skills (backward compatible)
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
                type=skill_data.get("type", "skill"),
                load_order=skill_data.get("load_order", 0),
            )

            if entry.name:
                self._entries[entry.name] = entry
                logger.debug(f"Registered skill: {entry.name} (enabled={entry.enabled})")

        self._loaded = True
        logger.info(
            f"Loaded {len(self._entries)} skills "
            f"({len(self._groups)} groups) from registry"
        )
        return True

    def get_active_skills(self) -> list[Skill]:
        """Get all enabled skills."""
        if not self._loaded:
            self.load_registry()

        active_skills = []
        for name, entry in self._entries.items():
            if not entry.enabled:
                continue
            skill = self.loader.load_skill(name, skill_type=entry.type)
            if skill:
                self._merge_shared_references(skill, entry)
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

        # Sort by load_order so instructions appear before reference material
        sorted_entries = sorted(
            self._entries.items(), key=lambda x: x[1].load_order
        )

        for name, entry in sorted_entries:
            if not entry.enabled or not entry.inject_into_tree:
                continue

            if entry.inject_mode == "on_demand":
                # Only inject if tags overlap with active_tags
                if not active_set or not active_set.intersection(entry.tags):
                    continue

            skill = self.loader.load_skill(name, skill_type=entry.type)
            if skill:
                self._merge_shared_references(skill, entry)
                parts.append(skill.get_injectable_content())

        return "\n\n---\n\n".join(parts)

    def _merge_shared_references(self, skill: Skill, entry: SkillRegistryEntry) -> None:
        """Merge shared group references into a member skill.

        If the skill belongs to a group with shared_references, load those
        references and add any that the skill doesn't already have.
        """
        if not entry.group:
            return

        group = self._groups.get(entry.group)
        if not group or not group.shared_references:
            return

        shared_skill = self.loader.load_skill(
            group.shared_references, skill_type="references"
        )
        if not shared_skill:
            return

        for ref_name, ref_content in shared_skill.references.items():
            if ref_name not in skill.references:
                skill.references[ref_name] = ref_content

    def get_skill_entry(self, skill_name: str) -> SkillRegistryEntry | None:
        """Get a registry entry by skill name."""
        if not self._loaded:
            self.load_registry()

        return self._entries.get(skill_name)

    def get_execution_model(self, skill_tags: Sequence[str]) -> ExecutionModel:
        """Determine execution model from active skill tags.

        Returns "generation", "vocabulary", or "archimate" if any enabled
        on-demand skill whose tags match declares that execution type.
        Otherwise returns "tree".
        """
        if not self._loaded:
            self.load_registry()

        if not skill_tags:
            return "tree"  # type: ignore[return-value]  # StrEnum accepts str

        tag_set = set(skill_tags)
        for execution_type in ("generation", "vocabulary", "archimate", "principle"):
            for entry in self._entries.values():
                if not entry.enabled:
                    continue
                if entry.execution != execution_type:
                    continue
                if tag_set.intersection(entry.tags):
                    return execution_type  # type: ignore[return-value]  # StrEnum accepts str

        return "tree"  # type: ignore[return-value]  # StrEnum accepts str

    def get_generation_skill(self, skill_tags: Sequence[str]) -> SkillRegistryEntry | None:
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

    def list_groups(self) -> list[SkillGroupEntry]:
        """List all registered skill groups."""
        if not self._loaded:
            self.load_registry()

        return list(self._groups.values())

    def reload(self):
        """Reload the registry and clear caches."""
        self._loaded = False
        self._entries.clear()
        self._groups.clear()
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

        # Find correct insertion point and detect indent from the - name: line
        insert_idx = None
        name_indent = 4  # default fallback
        in_target_skill = False

        for i, line in enumerate(lines):
            name_match = re.match(r'^(\s*)-\s*name:\s*["\']?([^"\'#\n]+)["\']?', line)
            if name_match:
                name = name_match.group(2).strip()
                if name == skill_name:
                    in_target_skill = True
                    name_indent = len(name_match.group(1)) + 2
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
                    name_indent = len(name_match.group(1)) + 2
                    continue
                if in_target_skill and re.match(r'^\s*description:', line):
                    insert_idx = i + 1
                    break

        if insert_idx is not None:
            prop_indent = " " * name_indent
            lines.insert(insert_idx, f"{prop_indent}enabled: {enabled_value}\n")

        registry_path.write_text("".join(lines), encoding="utf-8")

        if skill_name in self._entries:
            self._entries[skill_name].enabled = enabled

        logger.info(f"Set skill '{skill_name}' enabled={enabled}")
        return True

    def set_group_enabled(self, group_name: str, enabled: bool) -> bool:
        """Update the enabled status of a group in skills-registry.yaml.

        Modifies only the group-level enabled: line. Members inherit the
        group's enabled state on reload. For immediate effect, also updates
        in-memory entries.
        """
        registry_path = self.skills_dir / "skills-registry.yaml"

        if not registry_path.exists():
            raise ValueError(f"Registry not found: {registry_path}")

        if group_name not in self._groups:
            raise ValueError(f"Group not found: {group_name}")

        lines = registry_path.read_text(encoding="utf-8").splitlines(keepends=True)

        # Locate the groups: section and find - name: <group_name>
        in_groups_section = False
        group_found = False
        group_name_line_idx = None
        enabled_line_indices = []
        in_target_group = False
        name_indent = 4

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Detect top-level section boundaries
            if re.match(r'^(groups|skills):', line):
                in_groups_section = stripped.startswith("groups:")
                if in_target_group:
                    break
                continue

            if not in_groups_section:
                continue

            name_match = re.match(
                r'^(\s*)-\s*name:\s*["\']?([^"\'#\n]+)["\']?', line
            )
            if name_match:
                name = name_match.group(2).strip()
                if name == group_name:
                    group_found = True
                    in_target_group = True
                    group_name_line_idx = i
                    name_indent = len(name_match.group(1)) + 2
                elif in_target_group:
                    # Hit the next group or skill entry — stop
                    break
                continue

            if in_target_group and i != group_name_line_idx:
                # Only match enabled: at group property indent level
                enabled_match = re.match(
                    r'^(\s*)enabled:\s*(true|false)\s*(#.*)?$', line, re.IGNORECASE
                )
                if enabled_match:
                    enabled_line_indices.append(i)
                # Stop at nested skills: list
                if re.match(r'^\s*skills:', line):
                    break

        if not group_found:
            raise ValueError(f"Group not found in registry file: {group_name}")

        self._backup_registry(registry_path)

        enabled_value = "true" if enabled else "false"

        # Remove existing enabled: lines
        for idx in reversed(enabled_line_indices):
            del lines[idx]

        # Find insertion point after description:
        insert_idx = None
        in_target_group = False

        for i, line in enumerate(lines):
            name_match = re.match(
                r'^(\s*)-\s*name:\s*["\']?([^"\'#\n]+)["\']?', line
            )
            if name_match and name_match.group(2).strip() == group_name:
                in_target_group = True
                continue
            if in_target_group:
                if re.match(r'^\s*description:', line):
                    insert_idx = i + 1
                    break
                # If next entry or section before description, insert right after name
                if name_match or re.match(r'^(groups|skills):', line):
                    insert_idx = i
                    break

        if insert_idx is not None:
            prop_indent = " " * name_indent
            lines.insert(insert_idx, f"{prop_indent}enabled: {enabled_value}\n")

        registry_path.write_text("".join(lines), encoding="utf-8")

        # Update in-memory state
        group = self._groups[group_name]
        group.enabled = enabled
        for skill_name in group.skills:
            if skill_name in self._entries:
                self._entries[skill_name].enabled = enabled

        logger.info(f"Set group '{group_name}' enabled={enabled}")
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
_global_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """Get the global singleton SkillRegistry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry
