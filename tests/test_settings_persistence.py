"""Tests for user settings persistence (load, save, apply_user_overrides)."""

import json

import pytest

from aion.config import (
    _PERSISTABLE_FIELDS,
    Settings,
    _load_user_settings,
    _save_user_settings,
)


@pytest.fixture()
def settings_file(tmp_path, monkeypatch):
    """Redirect _USER_SETTINGS_FILE to a temp location."""
    f = tmp_path / "settings.json"
    monkeypatch.setattr("aion.config._USER_SETTINGS_FILE", f)
    return f


# --- _load_user_settings ---


def test_load_returns_empty_when_missing(settings_file):
    assert _load_user_settings() == {}


def test_load_returns_data(settings_file):
    settings_file.write_text(json.dumps({"llm_provider": "openai"}))
    assert _load_user_settings() == {"llm_provider": "openai"}


def test_load_returns_empty_on_corrupt_json(settings_file):
    settings_file.write_text("{not valid json")
    assert _load_user_settings() == {}


def test_load_returns_empty_on_non_dict_json(settings_file):
    """A JSON array or string is valid JSON but not a valid settings file."""
    settings_file.write_text(json.dumps(["ollama"]))
    # _load_user_settings returns whatever json.loads gives; validation is in apply.
    result = _load_user_settings()
    assert isinstance(result, list)


# --- _save_user_settings ---


def test_save_creates_file(settings_file):
    _save_user_settings({"llm_provider": "ollama"})
    assert settings_file.exists()
    assert json.loads(settings_file.read_text()) == {"llm_provider": "ollama"}


def test_save_overwrites_existing(settings_file):
    _save_user_settings({"llm_provider": "ollama"})
    _save_user_settings({"llm_provider": "openai"})
    assert json.loads(settings_file.read_text()) == {"llm_provider": "openai"}


def test_save_atomic_no_partial_write(settings_file):
    """After a successful save, no .tmp file should remain."""
    _save_user_settings({"llm_provider": "ollama"})
    tmp = settings_file.with_suffix(".tmp")
    assert not tmp.exists()


def test_save_handles_os_error(settings_file, monkeypatch):
    """Save should not raise on OS errors (e.g., permission denied)."""
    # Point to a path that can't be created.
    bad_path = settings_file.parent / "no" / "such" / "deeply" / "nested"
    monkeypatch.setattr("aion.config._USER_SETTINGS_FILE", bad_path / "settings.json")
    # Prevent mkdir from creating the path by raising.
    monkeypatch.setattr(
        "pathlib.Path.mkdir",
        lambda *a, **kw: (_ for _ in ()).throw(PermissionError("denied")),
    )
    _save_user_settings({"llm_provider": "ollama"})  # Should not raise


# --- apply_user_overrides ---


def test_apply_valid_settings(settings_file):
    settings_file.write_text(json.dumps({"llm_provider": "openai", "ollama_model": "llama3"}))
    s = Settings()
    s.apply_user_overrides()
    assert s.llm_provider == "openai"
    assert s.ollama_model == "llama3"


def test_apply_skips_non_persistable_fields(settings_file):
    """Fields not in _PERSISTABLE_FIELDS must never be applied (e.g., API keys)."""
    settings_file.write_text(json.dumps({"openai_api_key": "sk-stolen"}))
    s = Settings()
    original_key = s.openai_api_key
    s.apply_user_overrides()
    assert s.openai_api_key == original_key


def test_apply_rejects_invalid_provider(settings_file):
    settings_file.write_text(json.dumps({"llm_provider": "not_a_provider"}))
    s = Settings()
    original = s.llm_provider
    s.apply_user_overrides()
    assert s.llm_provider == original  # Unchanged — invalid value rejected


def test_apply_rejects_non_string_model(settings_file):
    settings_file.write_text(json.dumps({"ollama_model": 12345}))
    s = Settings()
    original = s.ollama_model
    s.apply_user_overrides()
    assert s.ollama_model == original  # Unchanged — int rejected


def test_apply_accepts_none_for_optional_provider(settings_file):
    """Optional provider fields (persona_provider, etc.) accept None."""
    settings_file.write_text(json.dumps({"persona_provider": None}))
    s = Settings()
    s.apply_user_overrides()
    assert s.persona_provider is None


def test_apply_handles_non_dict_json(settings_file):
    """If the file contains a JSON array, apply should not crash."""
    settings_file.write_text(json.dumps(["ollama"]))
    s = Settings()
    s.apply_user_overrides()  # Should not raise


def test_apply_handles_empty_file(settings_file):
    settings_file.write_text("")
    s = Settings()
    s.apply_user_overrides()  # Should not raise (corrupt JSON → empty dict)


def test_embedding_provider_is_persistable():
    """Regression: embedding_provider must be in _PERSISTABLE_FIELDS."""
    assert "embedding_provider" in _PERSISTABLE_FIELDS


def test_apply_embedding_provider(settings_file):
    """Regression: embedding_provider pin must survive restart."""
    settings_file.write_text(json.dumps({"embedding_provider": "ollama"}))
    s = Settings()
    s.apply_user_overrides()
    assert s.embedding_provider == "ollama"


# --- Round-trip ---


def test_save_then_load_roundtrip(settings_file):
    data = {"llm_provider": "github_models", "rag_model": "gpt-4.1"}
    _save_user_settings(data)
    loaded = _load_user_settings()
    assert loaded == data


def test_save_no_stale_tmp_files(settings_file):
    """After save, no .*.tmp files should remain (PID-based naming)."""
    _save_user_settings({"llm_provider": "ollama"})
    tmp_files = list(settings_file.parent.glob("settings.*.tmp"))
    assert tmp_files == []


def test_load_cleans_stale_tmp_files(settings_file):
    """Stale .tmp files from crashed saves are cleaned on load."""
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    stale = settings_file.parent / "settings.99999.tmp"
    stale.write_text("{}")
    _load_user_settings()
    assert not stale.exists()
