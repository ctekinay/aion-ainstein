"""System-runtime configuration accessor.

Reads from src/aion/config/runtime.yaml — values that are NOT per-plugin
(KB collections, agent tool-call ceilings, LLM token budgets, document
agent timeouts, persona classification config, quality gate, upload limits).

Plugin-content tuning (retrieval, truncation, abstention threshold) lives
in each plugin's .ainstein-plugin/thresholds.yaml and is accessed via the
SkillLoader's per-plugin accessors, not this module.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_RUNTIME_YAML_PATH = Path(__file__).parent / "runtime.yaml"

_cache: dict[str, Any] | None = None


def _load_runtime() -> dict[str, Any]:
    """Load and cache the runtime config from runtime.yaml.

    Error handling — chosen deliberately:

    * **File missing or unreadable** → log a warning, return ``{}``. Callers
      have explicit fallback defaults at every call site, so the server
      still boots in a sensible state (e.g. fresh install with no overrides).
    * **YAML malformed** → raise ``RuntimeError``. Silent fallback would hide
      a real configuration bug behind defaults that may not match what the
      operator intended. Fail-fast surfaces the problem immediately.
    """
    global _cache
    if _cache is not None:
        return _cache

    if not _RUNTIME_YAML_PATH.exists():
        logger.warning("runtime.yaml not found at %s — returning empty config", _RUNTIME_YAML_PATH)
        _cache = {}
        return _cache

    try:
        text = _RUNTIME_YAML_PATH.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Failed to read runtime.yaml at %s: %s — returning empty config", _RUNTIME_YAML_PATH, e)
        _cache = {}
        return _cache

    try:
        _cache = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise RuntimeError(f"Malformed runtime.yaml at {_RUNTIME_YAML_PATH}: {e}") from e
    return _cache


def get_runtime_value(dotted_path: str, default: Any) -> Any:
    """Read a value from runtime.yaml using a dotted path.

    Returns whole sections (dict/list) for top-level keys, nested values
    for dotted paths. Returns ``default`` if any path segment is missing.

    Examples:
        get_runtime_value("llm_token_limits", {})            # whole dict
        get_runtime_value("agents.max_tool_calls.rag_agent", 15)  # nested int
        get_runtime_value("kb_collections", [])              # whole list
    """
    config = _load_runtime()
    value: Any = config
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def clear_cache() -> None:
    """Reset the cached runtime config. Used in tests."""
    global _cache
    _cache = None
