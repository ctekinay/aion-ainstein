"""Unit tests for aion.config.runtime — dotted-path access, cache, fallback."""

from pathlib import Path


def test_top_level_key_returns_section():
    """Reading a top-level key returns the whole section (dict)."""
    from aion.config.runtime import get_runtime_value
    limits = get_runtime_value("llm_token_limits", {})
    assert isinstance(limits, dict)
    assert limits["persona_reasoning"] == 2048


def test_top_level_key_returns_list():
    """Reading a top-level key returns the whole list when applicable."""
    from aion.config.runtime import get_runtime_value
    collections = get_runtime_value("kb_collections", [])
    assert isinstance(collections, list)
    names = {c["name"] for c in collections}
    assert "ArchitecturalDecision" in names
    assert "Principle" in names


def test_dotted_path_reaches_leaf():
    """Dotted path resolves through nested dicts to a scalar."""
    from aion.config.runtime import get_runtime_value
    assert get_runtime_value("agents.max_tool_calls.rag_agent", 0) == 15
    assert get_runtime_value("quality_gate.proportionality.token_ceiling", 0) == 300


def test_missing_top_level_returns_default():
    from aion.config.runtime import get_runtime_value
    assert get_runtime_value("nope", {"x": 1}) == {"x": 1}


def test_missing_nested_segment_returns_default():
    from aion.config.runtime import get_runtime_value
    assert get_runtime_value("agents.max_tool_calls.unknown_agent", 42) == 42
    assert get_runtime_value("agents.compliance_batch_size.deep", "fallback") == "fallback"


def test_default_returned_when_yaml_missing(tmp_path, monkeypatch):
    """If runtime.yaml is absent the accessor returns the default and warns."""
    from aion.config import runtime as runtime_mod

    missing = tmp_path / "absent.yaml"
    monkeypatch.setattr(runtime_mod, "_RUNTIME_YAML_PATH", missing)
    runtime_mod.clear_cache()

    assert runtime_mod.get_runtime_value("agents", {"fallback": True}) == {"fallback": True}
    runtime_mod.clear_cache()


def test_runtime_yaml_exists_in_package():
    """Sanity: runtime.yaml ships alongside runtime.py."""
    from aion.config import runtime as runtime_mod
    assert Path(runtime_mod._RUNTIME_YAML_PATH).exists()


def test_malformed_yaml_raises(tmp_path, monkeypatch):
    """Fail-fast: a malformed runtime.yaml surfaces immediately, not silently."""
    import pytest as _pytest
    from aion.config import runtime as runtime_mod

    bad_yaml = tmp_path / "runtime.yaml"
    bad_yaml.write_text(":\n:\n  - [unbalanced\n", encoding="utf-8")
    monkeypatch.setattr(runtime_mod, "_RUNTIME_YAML_PATH", bad_yaml)
    runtime_mod.clear_cache()

    with _pytest.raises(RuntimeError, match="Malformed runtime.yaml"):
        runtime_mod.get_runtime_value("anything", None)
    runtime_mod.clear_cache()
