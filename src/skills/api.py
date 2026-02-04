"""Skills API logic for the Skills Management UI.

Provides functions for listing, testing, and configuring skills.
Used by the FastAPI endpoints in chat_ui.py.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from . import DEFAULT_SKILL
from .loader import SkillLoader
from .registry import SkillRegistry


# ============================================================================
# Default values - centralized for consistency with UI
# ============================================================================

# Abstention thresholds
DEFAULT_DISTANCE_THRESHOLD = 0.5
DEFAULT_MIN_QUERY_COVERAGE = 0.2

# Retrieval limits
DEFAULT_LIMIT_ADR = 8
DEFAULT_LIMIT_PRINCIPLE = 6
DEFAULT_LIMIT_POLICY = 4
DEFAULT_LIMIT_VOCABULARY = 4

# Truncation limits
DEFAULT_CONTENT_MAX_CHARS = 800
DEFAULT_ELYSIA_CONTENT_CHARS = 500
DEFAULT_ELYSIA_SUMMARY_CHARS = 300
DEFAULT_MAX_CONTEXT_RESULTS = 10

# Backup management
MAX_TIMESTAMPED_BACKUPS = 5  # Keep this many timestamped backups per skill


# Module-level instances (reused across requests)
_loader = SkillLoader()
_registry = SkillRegistry()


def list_skills() -> list[dict[str, Any]]:
    """List all registered skills with their metadata.

    Returns:
        List of skill info dictionaries
    """
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

        # Try to load thresholds summary
        try:
            thresholds = _loader.get_thresholds(entry.name)
            abstention = thresholds.get("abstention", {})
            skill_info["distance_threshold"] = abstention.get("distance_threshold", DEFAULT_DISTANCE_THRESHOLD)
            skill_info["min_query_coverage"] = abstention.get("min_query_coverage", DEFAULT_MIN_QUERY_COVERAGE)
        except Exception:
            skill_info["distance_threshold"] = DEFAULT_DISTANCE_THRESHOLD
            skill_info["min_query_coverage"] = DEFAULT_MIN_QUERY_COVERAGE

        skills.append(skill_info)

    return skills


def get_skill(skill_name: str) -> dict[str, Any]:
    """Get detailed information about a specific skill.

    Args:
        skill_name: Name of the skill

    Returns:
        Skill details including thresholds

    Raises:
        ValueError: If skill not found
    """
    # Find the skill in registry
    entries = [e for e in _registry.list_skills() if e.name == skill_name]
    if not entries:
        raise ValueError(f"Skill not found: {skill_name}")

    entry = entries[0]

    # Load full content and thresholds
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
    """Get thresholds for a specific skill.

    Args:
        skill_name: Name of the skill

    Returns:
        Thresholds dictionary
    """
    return _loader.get_thresholds(skill_name)


def update_thresholds(skill_name: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    """Update thresholds for a skill.

    Creates a backup before writing.

    Args:
        skill_name: Name of the skill
        thresholds: New thresholds configuration

    Returns:
        Updated thresholds

    Raises:
        ValueError: If validation fails
    """
    # Validate thresholds
    is_valid, errors = validate_thresholds(thresholds)
    if not is_valid:
        raise ValueError(f"Invalid thresholds: {', '.join(errors)}")

    # Get path to thresholds file
    skills_dir = Path(__file__).parent.parent.parent / "skills"
    thresholds_path = skills_dir / skill_name / "references" / "thresholds.yaml"

    if not thresholds_path.exists():
        raise ValueError(f"Thresholds file not found: {thresholds_path}")

    # Create backup
    backup_path = backup_config(skill_name)

    # Write new thresholds
    with open(thresholds_path, "w") as f:
        yaml.dump(thresholds, f, default_flow_style=False, sort_keys=False)

    # Clear cache so changes take effect
    _loader.clear_cache()

    return {
        "success": True,
        "backup_path": backup_path,
        "thresholds": thresholds,
    }


def validate_thresholds(thresholds: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate thresholds configuration.

    Args:
        thresholds: Thresholds to validate

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    # Validate abstention section
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

    # Validate retrieval_limits section
    limits = thresholds.get("retrieval_limits", {})
    for key in ["adr", "principle", "policy", "vocabulary"]:
        val = limits.get(key)
        if val is not None:
            if not isinstance(val, int):
                errors.append(f"retrieval_limits.{key} must be an integer")
            elif val < 1 or val > 50:
                errors.append(f"retrieval_limits.{key} must be between 1 and 50")

    # Validate truncation section
    truncation = thresholds.get("truncation", {})
    for key in ["content_max_chars", "elysia_content_chars", "elysia_summary_chars", "max_context_results"]:
        val = truncation.get(key)
        if val is not None:
            if not isinstance(val, int):
                errors.append(f"truncation.{key} must be an integer")
            elif val < 1:
                errors.append(f"truncation.{key} must be positive")

    # Validate list query detection fields (stored under abstention)
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


def backup_config(skill_name: str) -> str:
    """Create a backup of the skill's thresholds.yaml.

    Creates a timestamped backup and maintains a simple .bak file for easy restore.
    Cleans up old timestamped backups, keeping only the most recent ones.

    Args:
        skill_name: Name of the skill

    Returns:
        Path to the backup file
    """
    skills_dir = Path(__file__).parent.parent.parent / "skills"
    thresholds_path = skills_dir / skill_name / "references" / "thresholds.yaml"

    if not thresholds_path.exists():
        raise ValueError(f"Thresholds file not found: {thresholds_path}")

    # Create backup with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = thresholds_path.with_suffix(f".yaml.bak.{timestamp}")

    # Also maintain a simple .bak for easy restore
    simple_backup = thresholds_path.with_suffix(".yaml.bak")

    shutil.copy(thresholds_path, backup_path)
    shutil.copy(thresholds_path, simple_backup)

    # Clean up old timestamped backups (keep last N)
    _cleanup_old_backups(thresholds_path.parent, MAX_TIMESTAMPED_BACKUPS)

    return str(simple_backup)


def _cleanup_old_backups(directory: Path, keep_count: int) -> None:
    """Remove old timestamped backup files, keeping only the most recent ones.

    Args:
        directory: Directory containing backup files
        keep_count: Number of backups to keep
    """
    # Find all timestamped backups (pattern: thresholds.yaml.bak.YYYYMMDD_HHMMSS)
    backup_pattern = "thresholds.yaml.bak.*"
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
            # Ignore errors when deleting old backups
            pass


def restore_config(skill_name: str) -> dict[str, Any]:
    """Restore thresholds from the most recent backup.

    Args:
        skill_name: Name of the skill

    Returns:
        Restored thresholds

    Raises:
        ValueError: If no backup exists
    """
    skills_dir = Path(__file__).parent.parent.parent / "skills"
    thresholds_path = skills_dir / skill_name / "references" / "thresholds.yaml"
    backup_path = thresholds_path.with_suffix(".yaml.bak")

    if not backup_path.exists():
        raise ValueError(f"No backup found for skill: {skill_name}")

    # Restore from backup
    shutil.copy(backup_path, thresholds_path)

    # Clear cache
    _loader.clear_cache()

    # Return restored thresholds
    with open(thresholds_path) as f:
        thresholds = yaml.safe_load(f)

    return thresholds


def test_query(skill_name: str, query: str) -> dict[str, Any]:
    """Test how a query would behave with the current skill config.

    Simulates the abstention logic without actually querying the database.

    Args:
        skill_name: Name of the skill to test
        query: Test query string

    Returns:
        Test results including whether it would abstain
    """
    # Load thresholds
    thresholds = _loader.get_thresholds(skill_name)
    abstention = thresholds.get("abstention", {})

    distance_threshold = abstention.get("distance_threshold", DEFAULT_DISTANCE_THRESHOLD)
    min_query_coverage = abstention.get("min_query_coverage", DEFAULT_MIN_QUERY_COVERAGE)

    # Load list query detection config
    list_config = _loader.get_list_query_config(skill_name)
    list_indicators = set(list_config.get("list_indicators", []))
    list_patterns = list_config.get("list_patterns", [])
    additional_stop_words = set(list_config.get("additional_stop_words", []))

    # Detect if this is a list query
    query_lower = query.lower()
    query_words = set(query_lower.split())

    matched_indicator = None
    for indicator in list_indicators:
        if indicator in query_words:
            matched_indicator = indicator
            break

    is_list_query = matched_indicator is not None
    matched_pattern = None

    if not is_list_query:
        for pattern in list_patterns:
            if re.search(pattern, query_lower):
                is_list_query = True
                matched_pattern = pattern
                break

    # Check for specific ADR/PCP queries
    adr_match = re.search(r'adr[- ]?0*(\d+)', query_lower)
    pcp_match = re.search(r'pcp[- ]?0*(\d+)', query_lower)

    specific_doc_query = None
    if adr_match:
        specific_doc_query = f"ADR-{adr_match.group(1).zfill(4)}"
    elif pcp_match:
        specific_doc_query = f"PCP-{pcp_match.group(1).zfill(4)}"

    # Extract query terms for coverage analysis
    base_stop_words = {"what", "is", "the", "a", "an", "of", "in", "to", "for", "and", "or", "how", "does", "do", "about", "our"}
    stop_words = base_stop_words | additional_stop_words
    query_terms = [re.sub(r'[^\w]', '', t) for t in query_lower.split()]
    query_terms = [t for t in query_terms if t not in stop_words and len(t) > 2]

    return {
        "query": query,
        "skill_name": skill_name,
        "config": {
            "distance_threshold": distance_threshold,
            "min_query_coverage": min_query_coverage,
        },
        "analysis": {
            "is_list_query": is_list_query,
            "matched_indicator": matched_indicator,
            "matched_pattern": matched_pattern,
            "specific_doc_query": specific_doc_query,
            "query_terms": query_terms,
            "query_term_count": len(query_terms),
        },
        "behavior": {
            "skip_coverage_check": is_list_query,
            "requires_exact_match": specific_doc_query is not None,
            "note": _get_behavior_note(is_list_query, specific_doc_query, query_terms),
        }
    }


def _get_behavior_note(is_list_query: bool, specific_doc: str | None, terms: list[str]) -> str:
    """Generate a human-readable behavior note."""
    if is_list_query:
        return "List query detected - will skip coverage check if distance is acceptable"
    elif specific_doc:
        return f"Specific document query - will require {specific_doc} to exist in results"
    elif not terms:
        return "No meaningful query terms extracted - may have low coverage"
    else:
        return f"Standard query - will check both distance and coverage of {len(terms)} terms"


def reload_skills() -> dict[str, Any]:
    """Reload all skills from disk.

    Returns:
        Reload status
    """
    _loader.clear_cache()
    _registry.reload()

    return {
        "success": True,
        "message": "Skills reloaded successfully",
        "skill_count": len(_registry.list_skills()),
    }
