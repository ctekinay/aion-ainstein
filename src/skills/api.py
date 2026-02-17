"""Skills API logic for the Skills Management UI.

Provides functions for listing, configuring, and editing skills.
Used by the FastAPI endpoints in chat_ui.py.
"""

import logging
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from . import DEFAULT_SKILL
from .loader import SkillLoader
from .registry import get_skill_registry

logger = logging.getLogger(__name__)


# ============================================================================
# Default values — centralized for consistency with UI
# ============================================================================

DEFAULT_DISTANCE_THRESHOLD = 0.5
DEFAULT_MIN_QUERY_COVERAGE = 0.2

DEFAULT_LIMIT_ADR = 8
DEFAULT_LIMIT_PRINCIPLE = 6
DEFAULT_LIMIT_POLICY = 4
DEFAULT_LIMIT_VOCABULARY = 4

DEFAULT_CONTENT_MAX_CHARS = 800
DEFAULT_ELYSIA_CONTENT_CHARS = 500
DEFAULT_ELYSIA_SUMMARY_CHARS = 300
DEFAULT_CONSEQUENCES_MAX_CHARS = 4000
DEFAULT_DIRECT_DOC_MAX_CHARS = 12000
DEFAULT_MAX_CONTEXT_RESULTS = 10

DEFAULT_LIST_INDICATORS = [
    "list", "show", "all", "exist", "exists",
    "available", "have", "many", "which", "enumerate",
]
DEFAULT_ADDITIONAL_STOP_WORDS = [
    "are", "there", "exist", "exists", "list",
    "show", "all", "me", "give",
]

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"

# Module-level instances (reused across requests)
_loader = SkillLoader()
_registry = get_skill_registry()


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
            "min_query_coverage": DEFAULT_MIN_QUERY_COVERAGE,
            "list_indicators": DEFAULT_LIST_INDICATORS,
            "additional_stop_words": DEFAULT_ADDITIONAL_STOP_WORDS,
        },
        "retrieval_limits": {
            "adr": DEFAULT_LIMIT_ADR,
            "principle": DEFAULT_LIMIT_PRINCIPLE,
            "policy": DEFAULT_LIMIT_POLICY,
            "vocabulary": DEFAULT_LIMIT_VOCABULARY,
        },
        "truncation": {
            "content_max_chars": DEFAULT_CONTENT_MAX_CHARS,
            "elysia_content_chars": DEFAULT_ELYSIA_CONTENT_CHARS,
            "elysia_summary_chars": DEFAULT_ELYSIA_SUMMARY_CHARS,
            "consequences_max_chars": DEFAULT_CONSEQUENCES_MAX_CHARS,
            "direct_doc_max_chars": DEFAULT_DIRECT_DOC_MAX_CHARS,
            "max_context_results": DEFAULT_MAX_CONTEXT_RESULTS,
        },
    }


def list_skills() -> list[dict[str, Any]]:
    """List all registered skills with their metadata."""
    skills = []
    for entry in _registry.list_skills():
        skill_info = {
            "name": entry.name,
            "description": entry.description,
            "enabled": entry.enabled,
            "auto_activate": entry.auto_activate,
            "triggers": entry.triggers,
            "is_default": entry.name == DEFAULT_SKILL,
        }

        try:
            thresholds = _loader.get_thresholds(entry.name)
            abstention = thresholds.get("abstention", {})
            skill_info["distance_threshold"] = abstention.get(
                "distance_threshold", DEFAULT_DISTANCE_THRESHOLD
            )
            skill_info["min_query_coverage"] = abstention.get(
                "min_query_coverage", DEFAULT_MIN_QUERY_COVERAGE
            )
        except Exception:
            skill_info["distance_threshold"] = DEFAULT_DISTANCE_THRESHOLD
            skill_info["min_query_coverage"] = DEFAULT_MIN_QUERY_COVERAGE

        skills.append(skill_info)

    return skills


def get_skill(skill_name: str) -> dict[str, Any]:
    """Get detailed information about a specific skill."""
    entries = [e for e in _registry.list_skills() if e.name == skill_name]
    if not entries:
        raise ValueError(f"Skill not found: {skill_name}")

    entry = entries[0]

    try:
        skill = _loader.load_skill(skill_name)
        content = skill.content if skill else ""
    except Exception:
        content = ""

    try:
        thresholds = _loader.get_thresholds(skill_name)
    except Exception:
        thresholds = {}

    return {
        "name": entry.name,
        "description": entry.description,
        "enabled": entry.enabled,
        "auto_activate": entry.auto_activate,
        "triggers": entry.triggers,
        "is_default": entry.name == DEFAULT_SKILL,
        "content": content,
        "thresholds": thresholds,
    }


def get_thresholds(skill_name: str) -> dict[str, Any]:
    """Get thresholds for a specific skill."""
    return _loader.get_thresholds(skill_name)


def update_thresholds(skill_name: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    """Update thresholds for a skill. Creates a simple .bak backup before writing."""
    is_valid, errors = _validate_thresholds(thresholds)
    if not is_valid:
        raise ValueError(f"Invalid thresholds: {', '.join(errors)}")

    thresholds_path = SKILLS_DIR / skill_name / "references" / "thresholds.yaml"
    if not thresholds_path.exists():
        raise ValueError(f"Thresholds file not found: {thresholds_path}")

    # Simple backup
    shutil.copy(thresholds_path, thresholds_path.with_suffix(".yaml.bak"))

    with open(thresholds_path, "w") as f:
        yaml.dump(thresholds, f, default_flow_style=False, sort_keys=False)

    _loader.clear_cache()

    return {"success": True, "thresholds": thresholds}


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

    coverage = abstention.get("min_query_coverage")
    if coverage is not None:
        if not isinstance(coverage, (int, float)):
            errors.append("min_query_coverage must be a number")
        elif coverage < 0 or coverage > 1:
            errors.append("min_query_coverage must be between 0 and 1")

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
        "content_max_chars", "elysia_content_chars", "elysia_summary_chars",
        "consequences_max_chars", "direct_doc_max_chars", "max_context_results",
    ]:
        val = truncation.get(key)
        if val is not None:
            if not isinstance(val, int):
                errors.append(f"truncation.{key} must be an integer")
            elif val < 1:
                errors.append(f"truncation.{key} must be positive")

    list_indicators = abstention.get("list_indicators")
    if list_indicators is not None:
        if not isinstance(list_indicators, list):
            errors.append("list_indicators must be an array")
        elif not all(isinstance(item, str) for item in list_indicators):
            errors.append("list_indicators must contain only strings")

    list_patterns = abstention.get("list_patterns")
    if list_patterns is not None:
        if not isinstance(list_patterns, list):
            errors.append("list_patterns must be an array")
        else:
            for i, pattern in enumerate(list_patterns):
                if not isinstance(pattern, str):
                    errors.append(f"list_patterns[{i}] must be a string")
                else:
                    try:
                        re.compile(pattern)
                    except re.error as e:
                        errors.append(f"list_patterns[{i}] is invalid regex: {e}")

    stop_words = abstention.get("additional_stop_words")
    if stop_words is not None:
        if not isinstance(stop_words, list):
            errors.append("additional_stop_words must be an array")
        elif not all(isinstance(item, str) for item in stop_words):
            errors.append("additional_stop_words must contain only strings")

    return (len(errors) == 0, errors)


def toggle_skill_enabled(skill_name: str, enabled: bool) -> dict[str, Any]:
    """Toggle the enabled status of a skill in registry.yaml."""
    _registry.set_skill_enabled(skill_name, enabled)
    _registry.reload()

    return {
        "success": True,
        "skill_name": skill_name,
        "enabled": enabled,
        "message": f"Skill '{skill_name}' {'enabled' if enabled else 'disabled'}.",
    }


def reload_skills() -> dict[str, Any]:
    """Reload all skills from disk. Clears both loader cache and registry state."""
    _loader.clear_cache()
    _registry.reload()

    return {
        "success": True,
        "message": "Skills reloaded successfully",
        "skill_count": len(_registry.list_skills()),
    }


# ============================================================================
# SKILL.md content management
# ============================================================================


def get_skill_content(skill_name: str) -> dict[str, Any]:
    """Get the SKILL.md content for a skill (raw + parsed)."""
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
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
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
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

    _loader.clear_cache()

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
