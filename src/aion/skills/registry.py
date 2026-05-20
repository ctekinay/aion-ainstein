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

from aion.skills.loader import Skill, SkillLoader

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
    content_type: str = ""  # MIME type for artifact save (e.g. "text/html"); defaults to skill-name heuristic
    mcp_servers: list[str] = field(default_factory=list)
    """Names of MCP servers (from the plugin's .mcp.json) this skill needs.

    The MultiPluginRegistry uses this list to route plugin-supplied MCP tools
    to the right Pydantic AI agent at agent-build time. Skills routing to
    different execution models receive disjoint MCP tool sets — preventing
    tool-schema bloat across plugins.
    """

    conflicts_with: list[str] = field(default_factory=list)
    """Skill-scoped conflict declarations, shorthand ``<plugin>/<skill>``.

    When the MultiPluginRegistry loads and finds the exact target pair
    declared here is also loaded AND enabled, THIS entry is auto-disabled
    in-memory (the registry YAML is not modified). Tie-breaker: auto-disable
    applies only to the declaring side — a hypothetical reciprocal
    ``conflicts_with`` on the peer would self-disable the peer, never this
    entry. Surfaces in the UI as "disabled by conflicts_with".

    Phase-2 reframe: ``conflicts_with`` is a *legacy migration input* to
    the capability-scoped provider-precedence resolver, not the resolver
    itself. When this entry declares no explicit ``capability``, a peer in
    ``conflicts_with`` is read as "we provide the same implicit capability
    ``legacy:<skill-name>``" and resolved by the precedence rules below.
    """

    capability: str = ""
    """Provider-precedence: the capability-scoped key this skill provides.

    Empty ⇒ no explicit capability ⇒ legacy ``conflicts_with`` path (the
    resolver synthesizes ``legacy:<name>`` so behavior is unchanged until
    a skill opts in — keeps Phase-0 goldens byte-identical). Non-empty ⇒
    this skill competes for ``capability`` across all loaded plugins;
    the winner is chosen by ``provider_precedence`` (capability-scoped,
    NOT plugin-scoped; NOT discovery-order). Example:
    ``architecture.archimate.generation``.
    """

    provider_precedence: int = 0
    """Higher wins among enabled providers of the same ``capability``.

    Deterministic tie-break when equal: ``(provider_precedence desc,
    plugin_name asc, skill_name asc)`` — explicit, never filesystem/
    discovery order. An equal-precedence tie is a config smell and is
    logged WARNING naming both providers (visible, not silent).
    Kernel-role plugins do NOT participate in domain-provider precedence.
    """

    lifecycle: str = "default-provided"
    """``default-provided`` | ``deprecated-superseded`` | ``removed``.

    Drives the Phase-6 deprecation lifecycle. ``removed`` providers are
    excluded from resolution; ``deprecated-superseded`` still participates
    but logs INFO when selected.
    """

    yaml_pipeline: bool = False
    """Gates the YAML→XML conversion pipeline in ``generation.py``.

    A generation skill whose LLM output is structured YAML that must be
    converted to OXC (Open Exchange) XML before persisting opts in by
    setting ``yaml_pipeline: true``. Skills whose LLM output is the final
    artifact (HTML, views, prose) leave this False.

    Replaces a hardcoded skill-name match (ISS-002) that silently went
    False when the originating skill was renamed to
    ``archimate-oxc-generator``. Same declarative-capability shape as
    ``capability`` above. The 0c stale-skill-ref validator now catches
    the same class of regression at startup.
    """


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
        skills_dir: Path,
        loader: SkillLoader | None = None,
        registry_path: Path | None = None,
        thresholds_path: Path | None = None,
        shared_refs_dir: Path | None = None,
    ):
        """Construct a per-plugin skill registry.

        Args:
            skills_dir: Where the plugin's skill folders live. Required —
                the MultiPluginRegistry passes ``plugin.skills_dir``.
            loader: Optional pre-built SkillLoader. If omitted, one is constructed
                with this registry's skills_dir and thresholds_path.
            registry_path: Path to the plugin's ``skills-registry.yaml``. Defaults
                to ``skills_dir / "skills-registry.yaml"``. The
                MultiPluginRegistry passes ``plugin.registry_path``
                (``<plugin>/.ainstein-plugin/skills-registry.yaml``).
            thresholds_path: Path to the plugin's ``thresholds.yaml``. Same
                fallback semantics; forwarded to the loader.
            shared_refs_dir: Path to the plugin's top-level
                ``shared-references/`` directory. ``_merge_shared_references``
                reads ``<shared_refs_dir>/<group.shared_references>/*.md`` to
                augment member skills. If ``None``, shared references are
                not merged.
        """
        self.skills_dir = skills_dir
        self._registry_path = registry_path or (self.skills_dir / "skills-registry.yaml")
        self._thresholds_path = thresholds_path or (self.skills_dir / "thresholds.yaml")
        self._shared_refs_dir = shared_refs_dir
        self.loader = loader or SkillLoader(self.skills_dir, thresholds_path=self._thresholds_path)
        self._entries: dict[str, SkillRegistryEntry] = {}
        self._groups: dict[str, SkillGroupEntry] = {}
        self._loaded = False

    def load_registry(self) -> bool:
        """Load the skill registry from the configured skills-registry.yaml."""
        registry_path = self._registry_path

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
                    content_type=skill_data.get("content_type", ""),
                    mcp_servers=list(skill_data.get("mcp_servers", []) or []),
                    conflicts_with=list(skill_data.get("conflicts_with", []) or []),
                    capability=skill_data.get("capability", ""),
                    provider_precedence=int(skill_data.get("provider_precedence", 0) or 0),
                    lifecycle=skill_data.get("lifecycle", "default-provided"),
                    yaml_pipeline=bool(skill_data.get("yaml_pipeline", False)),
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
                content_type=skill_data.get("content_type", ""),
                mcp_servers=list(skill_data.get("mcp_servers", []) or []),
                conflicts_with=list(skill_data.get("conflicts_with", []) or []),
                capability=skill_data.get("capability", ""),
                provider_precedence=int(skill_data.get("provider_precedence", 0) or 0),
                lifecycle=skill_data.get("lifecycle", "default-provided"),
                yaml_pipeline=bool(skill_data.get("yaml_pipeline", False)),
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
        """Merge top-level ``shared-references/<group>/*.md`` into a member skill.

        If the skill belongs to a group whose ``shared_references`` field names
        a subdirectory under the plugin's ``shared-references/``, each ``.md``
        file there is added to the skill's references (skill-local refs win
        on name collision). No-op when ``shared_refs_dir`` is not configured
        (legacy layout, pre-commit-4) or the named subdirectory doesn't exist.
        """
        if not entry.group:
            return

        group = self._groups.get(entry.group)
        if not group or not group.shared_references:
            return

        if self._shared_refs_dir is None:
            return

        shared_dir = self._shared_refs_dir / group.shared_references
        if not shared_dir.is_dir():
            return

        for f in sorted(shared_dir.glob("*.md")):
            ref_name = f.stem
            if ref_name in skill.references:
                continue
            try:
                skill.references[ref_name] = f.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning("Failed to read shared ref %s: %s", f, e)

    def get_skill_entry(self, skill_name: str) -> SkillRegistryEntry | None:
        """Get a registry entry by skill name."""
        if not self._loaded:
            self.load_registry()

        return self._entries.get(skill_name)

    def get_skill_tuning(
        self, skill_name: str, getter_name: str, default
    ):
        """Read a plugin-tuning value via the loader, gated by skill activation.

        Replaces direct access to ``registry.loader.<getter>`` at call sites
        so the multi-plugin registry (commit 3) can route the lookup to the
        plugin owning ``skill_name`` without breaking the caller API.

        Returns ``default`` if the skill is missing, disabled, or if the
        loader raises.
        """
        if not self._loaded:
            self.load_registry()

        entry = self._entries.get(skill_name)
        if entry is None or not entry.enabled:
            return default
        try:
            return getattr(self.loader, getter_name)(skill_name)
        except Exception:
            logger.warning(
                "Failed to read skill tuning '%s' for '%s', using default",
                getter_name, skill_name,
            )
            return default

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
        for execution_type in ("generation", "vocabulary", "archimate", "principle", "repo_analysis"):
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
        registry_path = self._registry_path

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
        registry_path = self._registry_path

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


def get_skill_registry():
    """Get the process-wide registry singleton.

    Backward-compat alias for ``aion.skills.multi_registry.get_multi_registry``.
    Returns a ``MultiPluginRegistry`` whose API surface matches the historical
    ``SkillRegistry`` (list_skills, get_skill_content, get_execution_model,
    set_skill_enabled, …) so existing callers in chat_ui, routing, agents,
    and tools continue to work without modification.
    """
    from aion.skills.multi_registry import get_multi_registry
    return get_multi_registry()
