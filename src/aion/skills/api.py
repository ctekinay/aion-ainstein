"""Skills API logic for the Skills Management UI.

Provides functions for listing, configuring, and editing skills.
Used by the FastAPI endpoints in chat_ui.py.
"""

import logging
import shutil
from typing import Any

import yaml

from aion.skills import DEFAULT_SKILL
from aion.skills.registry import get_skill_registry
from aion.tools.rag_search import DEFAULT_DISTANCE_THRESHOLD

logger = logging.getLogger(__name__)


# ============================================================================
# Default values — centralized for consistency with UI
# ============================================================================

DEFAULT_LIMIT_ADR = 8
DEFAULT_LIMIT_PRINCIPLE = 6
DEFAULT_LIMIT_POLICY = 4
DEFAULT_LIMIT_VOCABULARY = 4

DEFAULT_CONTENT_MAX_CHARS = 800
DEFAULT_TOOL_CONTENT_CHARS = 500
DEFAULT_TOOL_SUMMARY_CHARS = 300
DEFAULT_CONSEQUENCES_MAX_CHARS = 4000
DEFAULT_DIRECT_DOC_MAX_CHARS = 12000
DEFAULT_MAX_CONTEXT_RESULTS = 10

def _loader_for(skill_name: str):
    """Resolve the SkillLoader of the plugin that defines this skill.

    Routes through the multi-registry so content/thresholds resolve from
    the owning plugin's directory. Replaces the legacy module-level
    ``SkillLoader()`` + hardcoded ``SKILLS_DIR`` (both assumed a single
    in-tree ``skills/`` dir, gone after the plugins/ restructure).
    """
    loader = _get_registry().get_loader_for_skill(skill_name)
    if loader is None:
        raise ValueError(f"Skill not found in any plugin: {skill_name}")
    return loader


def _get_registry():
    """Fetch the current multi-plugin registry singleton at call time.

    Module-level caching (``_registry = get_skill_registry()``) doesn't work
    here because the conftest autouse fixture resets ``_global_multi`` between
    tests — a stale module-level reference would point at the singleton from
    when this module was first imported, not the one the test installed.
    The per-call lookup is cheap (one global-variable read after the first
    initialization).
    """
    return get_skill_registry()


# ============================================================================
# Core API functions
# ============================================================================


def get_defaults() -> dict[str, Any]:
    """Get all default configuration values.

    Exposes defaults via API so frontend doesn't need to duplicate them.
    """
    return {
        "abstention": {
            "distance_threshold": DEFAULT_DISTANCE_THRESHOLD,
        },
        "retrieval_limits": {
            "adr": DEFAULT_LIMIT_ADR,
            "principle": DEFAULT_LIMIT_PRINCIPLE,
            "policy": DEFAULT_LIMIT_POLICY,
            "vocabulary": DEFAULT_LIMIT_VOCABULARY,
        },
        "truncation": {
            "content_max_chars": DEFAULT_CONTENT_MAX_CHARS,
            "tool_content_chars": DEFAULT_TOOL_CONTENT_CHARS,
            "tool_summary_chars": DEFAULT_TOOL_SUMMARY_CHARS,
            "consequences_max_chars": DEFAULT_CONSEQUENCES_MAX_CHARS,
            "direct_doc_max_chars": DEFAULT_DIRECT_DOC_MAX_CHARS,
            "max_context_results": DEFAULT_MAX_CONTEXT_RESULTS,
        },
    }


def list_skills() -> list[dict[str, Any]]:
    """List all registered skills with their metadata.

    Each skill entry includes a ``plugin`` field carrying its owning
    plugin name. Attribution comes from the per-plugin iteration context
    (``iter_plugin_skills``), NOT from name-based lookup — so name
    collisions (two plugins declaring the same skill) attribute each
    entry to the correct plugin instead of both attributing to whichever
    plugin loads first.
    """
    skills = []
    for plugin_name, entry in _get_registry().iter_plugin_skills():
        # Real, per-skill metadata. The old code stamped a universal
        # `distance_threshold` (defaulting to 0.6) onto EVERY skill — a
        # plugin-scoped RAG value that is meaningless as per-skill info
        # (it now lives in the per-plugin Plugin Settings panel). Replaced
        # with fields that are genuinely per-skill: inject mode, execution
        # routing, and classification tags.
        skill_info = {
            "name": entry.name,
            "description": entry.description,
            "enabled": entry.enabled,
            "is_default": entry.name == DEFAULT_SKILL,
            "group": entry.group,
            "type": entry.type,
            "plugin": plugin_name,
            "inject_mode": getattr(entry, "inject_mode", "") or "",
            "execution": getattr(entry, "execution", "") or "",
            "tags": list(getattr(entry, "tags", []) or []),
        }
        skills.append(skill_info)

    return skills


def list_plugins() -> list[dict[str, Any]]:
    """Return manifest metadata + skill counts for each loaded plugin.

    Used by the plugin-grouped skills UI to render the outer accordion's
    header. Skill counts use the per-plugin iteration (``iter_plugin_skills``)
    so collisions report each plugin's actual contribution — both copies of
    a shadowed skill counted against their owning plugin.
    """
    # Per-plugin grouping built from iter_plugin_skills (collision-safe).
    per_plugin_entries: dict[str, list] = {}
    for plugin_name, entry in _get_registry().iter_plugin_skills():
        per_plugin_entries.setdefault(plugin_name, []).append(entry)

    out: list[dict[str, Any]] = []
    for plugin_name in _get_registry().list_plugins():
        plugin = _get_registry().get_plugin(plugin_name)
        owned = per_plugin_entries.get(plugin_name, [])
        enabled = sum(1 for e in owned if e.enabled)

        if plugin is None:
            # Legacy synthesized plugin (no .ainstein-plugin/plugin.json on disk).
            # Pre-commit-4 transition state — should not be reachable in production
            # after the bundled-skills migration.
            out.append({
                "name": plugin_name,
                "version": "0.0.0",
                "description": "(legacy in-tree fallback — no manifest)",
                "author": {},
                "skill_count": len(owned),
                "enabled_count": enabled,
                "is_legacy": True,
            })
        else:
            out.append({
                "name": plugin.name,
                "version": plugin.version,
                "description": plugin.manifest.description,
                "author": plugin.manifest.author,
                "skill_count": len(owned),
                "enabled_count": enabled,
                "is_legacy": False,
            })
    return out


def toggle_skill_enabled_in_plugin(
    plugin_name: str, skill_name: str, enabled: bool,
) -> dict[str, Any]:
    """Enable/disable a skill within a specific plugin, with HTTP 409 preflight.

    Uses ``MultiPluginRegistry.set_skill_enabled_in_plugin`` for explicit
    plugin-scoped routing — critical for the "user re-enables a shadowed
    skill" flow. Under name collision, the previous ``find_plugin_for_skill``-
    based routing would misattribute the shadowed entry to the conflicting
    plugin and return HTTP 404, making the documented dup-check + 409
    surfacing unreachable. The explicit-routing path verifies the named
    plugin actually defines the named skill in ITS OWN registry (not via
    a flat name lookup), then runs the duplicate-check preflight before
    persisting.

    Raises:
        ValueError: if the named plugin doesn't define the named skill
            (UI bug or stale state).
        DuplicateSkillError: if enabling would shadow an already-enabled
            skill of the same name in another plugin. The FastAPI route
            catches and translates to HTTP 409 with the conflict pair.
    """
    # set_skill_enabled_in_plugin handles: plugin-exists check, skill-in-this-
    # plugin check, preflight dup-check (on enable), persistence, and reload.
    # DuplicateSkillError propagates to the FastAPI route.
    _get_registry().set_skill_enabled_in_plugin(plugin_name, skill_name, enabled)

    return {
        "success": True,
        "plugin": plugin_name,
        "skill": skill_name,
        "enabled": enabled,
        "message": f"Skill '{plugin_name}/{skill_name}' {'enabled' if enabled else 'disabled'}.",
    }


def get_skill(skill_name: str) -> dict[str, Any]:
    """Get detailed information about a specific skill."""
    entries = [e for e in _get_registry().list_skills() if e.name == skill_name]
    if not entries:
        raise ValueError(f"Skill not found: {skill_name}")

    entry = entries[0]

    try:
        skill = _loader_for(skill_name).load_skill(skill_name, skill_type=entry.type)
        content = skill.content if skill else ""
    except Exception:
        content = ""

    try:
        thresholds = _loader_for(skill_name).get_thresholds(skill_name)
    except Exception:
        thresholds = {}

    return {
        "name": entry.name,
        "description": entry.description,
        "enabled": entry.enabled,
        "is_default": entry.name == DEFAULT_SKILL,
        "content": content,
        "thresholds": thresholds,
    }


def get_thresholds(skill_name: str) -> dict[str, Any]:
    """Get thresholds for a specific skill."""
    return _loader_for(skill_name).get_thresholds(skill_name)


def update_thresholds(skill_name: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    """Update thresholds for a skill. Creates a simple .bak backup before writing."""
    is_valid, errors = _validate_thresholds(thresholds)
    if not is_valid:
        raise ValueError(f"Invalid thresholds: {', '.join(errors)}")

    loader = _loader_for(skill_name)
    thresholds_path = loader.skills_dir / skill_name / "references" / "thresholds.yaml"
    if not thresholds_path.exists():
        raise ValueError(f"Thresholds file not found: {thresholds_path}")

    # Simple backup
    shutil.copy(thresholds_path, thresholds_path.with_suffix(".yaml.bak"))

    with open(thresholds_path, "w") as f:
        yaml.dump(thresholds, f, default_flow_style=False, sort_keys=False)

    loader.clear_cache()

    return {"success": True, "thresholds": thresholds}


def get_plugin_thresholds(plugin_name: str) -> dict[str, Any]:
    """Plugin-scoped: the plugin's ``.ainstein-plugin/thresholds.yaml``.

    Empty/missing file → ``{}`` (the UI renders a 'no tunable thresholds'
    state). This is the authoritative per-plugin tuning surface
    (retrieval/abstention/truncation etc.), not a per-skill references
    file.
    """
    plugin = _get_registry().get_plugin(plugin_name)
    if plugin is None:
        raise ValueError(f"Plugin not found: {plugin_name}")
    path = plugin.thresholds_path
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def update_plugin_thresholds(
    plugin_name: str, thresholds: dict[str, Any]
) -> dict[str, Any]:
    """Plugin-scoped write of ``.ainstein-plugin/thresholds.yaml``.

    Validates known RAG sections (unknown/empty sections tolerated),
    writes a ``.yaml.bak`` backup, then reloads the registry so the new
    tuning takes effect.

    The leading comment block of the existing file is PRESERVED and
    re-prepended (stdlib ``yaml.dump`` would otherwise strip it). This
    matters because e.g. ``ainstein-kernel``'s thresholds.yaml carries a
    load-bearing CRITICAL routing note; an operator editing thresholds
    via the Plugin Settings panel must not silently destroy it.
    """
    is_valid, errors = _validate_thresholds(thresholds)
    if not is_valid:
        raise ValueError(f"Invalid thresholds: {', '.join(errors)}")
    plugin = _get_registry().get_plugin(plugin_name)
    if plugin is None:
        raise ValueError(f"Plugin not found: {plugin_name}")
    path = plugin.thresholds_path
    path.parent.mkdir(parents=True, exist_ok=True)

    header = ""
    if path.exists():
        shutil.copy(path, path.with_suffix(".yaml.bak"))
        # Capture the leading contiguous comment/blank-line block.
        lead = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() == "" or line.lstrip().startswith("#"):
                lead.append(line)
            else:
                break
        if lead:
            header = "\n".join(lead).rstrip() + "\n\n"

    body = yaml.dump(thresholds, default_flow_style=False, sort_keys=False)
    path.write_text(header + body, encoding="utf-8")
    _get_registry().reload()
    return {"success": True, "plugin": plugin_name, "thresholds": thresholds}


def reload_plugin(plugin_name: str) -> dict[str, Any]:
    """Issue-8: 'Reload Plugin'. Per the chosen design this triggers the
    proven full-registry reload (re-reads every plugin's registry +
    reloads all skills, including the named plugin's), framed per-plugin
    in the UI. There is intentionally no isolated single-plugin reload
    (rejected: registry-state-divergence risk).
    """
    reg = _get_registry()
    if reg.get_plugin(plugin_name) is None:
        raise ValueError(f"Plugin not found: {plugin_name}")
    reg.reload()
    return {"success": True, "plugin": plugin_name, "reloaded": "all-plugins"}


def _validate_thresholds(thresholds: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate thresholds configuration."""
    errors = []

    abstention = thresholds.get("abstention", {})

    distance = abstention.get("distance_threshold")
    if distance is not None:
        if not isinstance(distance, (int, float)):
            errors.append("distance_threshold must be a number")
        elif distance < 0 or distance > 1:
            errors.append("distance_threshold must be between 0 and 1")

    limits = thresholds.get("retrieval_limits", {})
    for key in ["adr", "principle", "policy", "vocabulary"]:
        val = limits.get(key)
        if val is not None:
            if not isinstance(val, int):
                errors.append(f"retrieval_limits.{key} must be an integer")
            elif val < 1 or val > 50:
                errors.append(f"retrieval_limits.{key} must be between 1 and 50")

    truncation = thresholds.get("truncation", {})
    for key in [
        "content_max_chars", "tool_content_chars", "tool_summary_chars",
        "consequences_max_chars", "direct_doc_max_chars", "max_context_results",
    ]:
        val = truncation.get(key)
        if val is not None:
            if not isinstance(val, int):
                errors.append(f"truncation.{key} must be an integer")
            elif val < 1:
                errors.append(f"truncation.{key} must be positive")

    return (len(errors) == 0, errors)


def toggle_skill_enabled(skill_name: str, enabled: bool) -> dict[str, Any]:
    """Toggle the enabled status of a skill in skills-registry.yaml."""
    _get_registry().set_skill_enabled(skill_name, enabled)
    _get_registry().reload()

    return {
        "success": True,
        "skill_name": skill_name,
        "enabled": enabled,
        "message": f"Skill '{skill_name}' {'enabled' if enabled else 'disabled'}.",
    }


def list_groups() -> list[dict[str, Any]]:
    """List all registered skill groups."""
    return [
        {
            "name": g.name,
            "description": g.description,
            "enabled": g.enabled,
            "skills": g.skills,
        }
        for g in _get_registry().list_groups()
    ]


def toggle_group_enabled(group_name: str, enabled: bool) -> dict[str, Any]:
    """Toggle the enabled status of a group in skills-registry.yaml."""
    _get_registry().set_group_enabled(group_name, enabled)
    _get_registry().reload()

    return {
        "success": True,
        "group_name": group_name,
        "enabled": enabled,
        "message": f"Group '{group_name}' {'enabled' if enabled else 'disabled'}.",
    }


def reload_skills() -> dict[str, Any]:
    """Reload all skills from disk. Clears both loader cache and registry state.

    ``MultiPluginRegistry.reload()`` already clears every plugin's loader
    cache (per-plugin ``SkillRegistry.reload`` → ``loader.clear_cache``),
    so no separate loader cache clear is needed here.
    """
    _get_registry().reload()

    return {
        "success": True,
        "message": "Skills reloaded successfully",
        "skill_count": len(_get_registry().list_skills()),
    }


# ============================================================================
# SKILL.md content management
# ============================================================================


def get_skill_content(skill_name: str) -> dict[str, Any]:
    """Get the SKILL.md content for a skill (raw + parsed)."""
    skill_path = _loader_for(skill_name).skills_dir / skill_name / "SKILL.md"
    if not skill_path.exists():
        raise ValueError(f"SKILL.md not found for skill: {skill_name}")

    with open(skill_path, encoding="utf-8") as f:
        raw_content = f.read()

    metadata, body = _parse_skill_content(raw_content)

    return {
        "skill_name": skill_name,
        "raw_content": raw_content,
        "metadata": metadata,
        "body": body,
        "path": str(skill_path),
    }


def update_skill_content(
    skill_name: str,
    content: str | None = None,
    metadata: dict[str, Any] | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    """Update the SKILL.md content. Creates a simple .bak backup before writing."""
    loader = _loader_for(skill_name)
    skill_path = loader.skills_dir / skill_name / "SKILL.md"
    if not skill_path.exists():
        raise ValueError(f"SKILL.md not found for skill: {skill_name}")

    if content is not None:
        final_content = content
    elif metadata is not None and body is not None:
        final_content = _build_skill_content(metadata, body)
    else:
        raise ValueError("Must provide either 'content' or both 'metadata' and 'body'")

    is_valid, errors = _validate_skill_content(final_content)
    if not is_valid:
        raise ValueError(f"Invalid SKILL.md content: {'; '.join(errors)}")

    # Simple backup
    shutil.copy(skill_path, skill_path.with_suffix(".md.bak"))

    with open(skill_path, "w", encoding="utf-8") as f:
        f.write(final_content)

    loader.clear_cache()

    new_metadata, new_body = _parse_skill_content(final_content)

    return {
        "success": True,
        "skill_name": skill_name,
        "metadata": new_metadata,
        "body": new_body,
    }


def _validate_skill_content(content: str) -> tuple[bool, list[str]]:
    """Validate SKILL.md content structure."""
    errors = []

    if not content.startswith("---"):
        errors.append("Missing YAML frontmatter (must start with ---)")
        return (False, errors)

    second_delimiter = content.find("---", 3)
    if second_delimiter == -1:
        errors.append("Invalid frontmatter: missing closing ---")
        return (False, errors)

    frontmatter_text = content[3:second_delimiter].strip()
    try:
        metadata = yaml.safe_load(frontmatter_text)
        if metadata is None:
            metadata = {}
    except yaml.YAMLError as e:
        errors.append(f"Invalid YAML in frontmatter: {e}")
        return (False, errors)

    if not isinstance(metadata, dict):
        errors.append("Frontmatter must be a YAML dictionary")
        return (False, errors)

    for field in ["name", "description"]:
        if field not in metadata:
            errors.append(f"Missing required frontmatter field: {field}")

    body = content[second_delimiter + 3:].strip()
    if not body:
        errors.append("Markdown body cannot be empty")

    return (len(errors) == 0, errors)


def _parse_skill_content(content: str) -> tuple[dict[str, Any], str]:
    """Parse SKILL.md into (metadata dict, body string)."""
    metadata = {}
    body = content

    if content.startswith("---"):
        second_delimiter = content.find("---", 3)
        if second_delimiter != -1:
            frontmatter_text = content[3:second_delimiter].strip()
            try:
                metadata = yaml.safe_load(frontmatter_text) or {}
            except yaml.YAMLError:
                pass
            body = content[second_delimiter + 3:].strip()

    return (metadata, body)


def _build_skill_content(metadata: dict[str, Any], body: str) -> str:
    """Build SKILL.md content from metadata and body."""
    frontmatter = yaml.dump(
        metadata,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    ).strip()

    return f"---\n{frontmatter}\n---\n\n{body}"
