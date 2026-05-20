"""Tests for plugin manifest parsing and discovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aion.skills.plugin import (
    Plugin,
    PluginManifestError,
    load_plugin_manifest,
)
from aion.skills.plugin_loader import PluginLoader


def _write_manifest(plugin_root: Path, payload: dict | str) -> Path:
    plugin_dir = plugin_root / ".ainstein-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = plugin_dir / "plugin.json"
    text = payload if isinstance(payload, str) else json.dumps(payload)
    manifest.write_text(text, encoding="utf-8")
    return manifest


# ---------------------------------------------------------------------- manifest


class TestLoadPluginManifest:
    def test_valid_manifest_returns_plugin(self, tmp_path):
        _write_manifest(tmp_path, {
            "name": "demo",
            "runtime": "ainstein",
            "version": "1.2.3",
            "description": "A demo plugin",
            "author": {"name": "Tester"},
        })
        plugin = load_plugin_manifest(tmp_path)
        assert isinstance(plugin, Plugin)
        assert plugin.name == "demo"
        assert plugin.version == "1.2.3"
        assert plugin.manifest.description == "A demo plugin"
        assert plugin.manifest.author == {"name": "Tester"}
        assert plugin.root == tmp_path.resolve()

    def test_path_accessors_resolve_to_sibling_dirs(self, tmp_path):
        _write_manifest(tmp_path, {"name": "demo", "runtime": "ainstein"})
        plugin = load_plugin_manifest(tmp_path)
        assert plugin.plugin_dir == tmp_path.resolve() / ".ainstein-plugin"
        assert plugin.registry_path == tmp_path.resolve() / ".ainstein-plugin" / "skills-registry.yaml"
        assert plugin.thresholds_path == tmp_path.resolve() / ".ainstein-plugin" / "thresholds.yaml"
        assert plugin.skills_dir == tmp_path.resolve() / "skills"
        assert plugin.shared_refs_dir == tmp_path.resolve() / "shared-references"
        assert plugin.mcp_config_path == tmp_path.resolve() / ".mcp.json"
        assert plugin.hooks_dir == tmp_path.resolve() / "hooks"
        assert plugin.hooks_config_path == tmp_path.resolve() / "hooks" / "hooks.json"
        assert plugin.templates_dir == tmp_path.resolve() / "templates"

    def test_missing_manifest_raises(self, tmp_path):
        with pytest.raises(PluginManifestError, match="plugin.json not found"):
            load_plugin_manifest(tmp_path)

    def test_invalid_json_raises(self, tmp_path):
        _write_manifest(tmp_path, "not-valid-json{")
        with pytest.raises(PluginManifestError, match="invalid JSON"):
            load_plugin_manifest(tmp_path)

    def test_non_object_top_level_raises(self, tmp_path):
        _write_manifest(tmp_path, "[1, 2, 3]")
        with pytest.raises(PluginManifestError, match="top-level must be a JSON object"):
            load_plugin_manifest(tmp_path)

    def test_missing_name_raises(self, tmp_path):
        _write_manifest(tmp_path, {"runtime": "ainstein", "version": "1.0"})
        with pytest.raises(PluginManifestError, match="missing or invalid 'name' field"):
            load_plugin_manifest(tmp_path)

    def test_wrong_runtime_raises(self, tmp_path):
        _write_manifest(tmp_path, {"name": "demo", "runtime": "some-other-host"})
        with pytest.raises(PluginManifestError, match="runtime must be 'ainstein'"):
            load_plugin_manifest(tmp_path)

    def test_defaults_for_optional_fields(self, tmp_path):
        _write_manifest(tmp_path, {"name": "demo", "runtime": "ainstein"})
        plugin = load_plugin_manifest(tmp_path)
        assert plugin.version == "0.0.0"
        assert plugin.manifest.description == ""
        assert plugin.manifest.author == {}

    def test_wrong_typed_author_raises(self, tmp_path):
        """Validation consistency: author of the wrong type raises, like name/runtime."""
        _write_manifest(tmp_path, {
            "name": "demo",
            "runtime": "ainstein",
            "author": "Just a string",
        })
        with pytest.raises(PluginManifestError, match="'author' must be a JSON object"):
            load_plugin_manifest(tmp_path)


# ---------------------------------------------------------------------- discovery


class TestPluginLoaderDiscover:
    def test_discovers_via_env_var(self, tmp_path, monkeypatch):
        plugin_root = tmp_path / "demo-plugin"
        _write_manifest(plugin_root, {"name": "demo", "runtime": "ainstein"})
        monkeypatch.setenv("AINSTEIN_PLUGINS", str(plugin_root))

        # Use an empty user_dir + nonexistent in_tree_root to isolate env var.
        empty = tmp_path / "no-user-plugins"
        plugins = PluginLoader.discover(user_dir=empty, in_tree_root=empty)

        assert len(plugins) == 1
        assert plugins[0].name == "demo"

    def test_discovers_via_user_dir(self, tmp_path, monkeypatch):
        user_dir = tmp_path / "plugins"
        user_dir.mkdir()
        plugin_a = user_dir / "plugin-a"
        plugin_b = user_dir / "plugin-b"
        _write_manifest(plugin_a, {"name": "a", "runtime": "ainstein"})
        _write_manifest(plugin_b, {"name": "b", "runtime": "ainstein"})
        # Random non-plugin folder should be ignored:
        (user_dir / "not-a-plugin").mkdir()

        monkeypatch.setenv("AINSTEIN_PLUGINS", "")

        plugins = PluginLoader.discover(user_dir=user_dir, in_tree_root=tmp_path)
        names = sorted(p.name for p in plugins)
        assert names == ["a", "b"]

    def test_discovers_in_tree_plugins_dir(self, tmp_path, monkeypatch):
        """In-tree discovery scans <repo>/plugins/*/, not the repo root itself."""
        # Synthetic plugin names (not the real bundled set) — this test
        # only exercises the <repo>/plugins/*/ scan mechanics.
        repo = tmp_path / "repo"
        _write_manifest(repo / "plugins" / "legacy-domain", {
            "name": "legacy-domain", "runtime": "ainstein",
        })
        _write_manifest(repo / "plugins" / "enterpower-architecture", {
            "name": "enterpower-architecture", "runtime": "ainstein",
        })
        # A non-plugin child of plugins/ is ignored.
        (repo / "plugins" / "not-a-plugin").mkdir(parents=True)
        # A manifest at the repo ROOT is NOT discovered (root is the host).
        _write_manifest(repo, {"name": "should-not-load", "runtime": "ainstein"})

        empty = tmp_path / "empty-user-dir"
        monkeypatch.setenv("AINSTEIN_PLUGINS", "")
        plugins = PluginLoader.discover(user_dir=empty, in_tree_root=repo)
        assert sorted(p.name for p in plugins) == [
            "enterpower-architecture", "legacy-domain",
        ]

    def test_env_var_accepts_arbitrary_path(self, tmp_path, monkeypatch):
        """env var path doesn't have to be a child of ~/.ainstein/plugins."""
        arbitrary = tmp_path / "somewhere" / "anywhere" / "my-plugin"
        _write_manifest(arbitrary, {"name": "arbitrary", "runtime": "ainstein"})
        monkeypatch.setenv("AINSTEIN_PLUGINS", str(arbitrary))
        empty = tmp_path / "no-user-plugins"
        plugins = PluginLoader.discover(user_dir=empty, in_tree_root=empty)
        assert [p.name for p in plugins] == ["arbitrary"]

    def test_env_var_supports_multiple_paths(self, tmp_path, monkeypatch):
        plugin_x = tmp_path / "x"
        plugin_y = tmp_path / "y"
        _write_manifest(plugin_x, {"name": "x", "runtime": "ainstein"})
        _write_manifest(plugin_y, {"name": "y", "runtime": "ainstein"})
        monkeypatch.setenv("AINSTEIN_PLUGINS", f"{plugin_x}:{plugin_y}")
        empty = tmp_path / "empty-user-dir"
        plugins = PluginLoader.discover(user_dir=empty, in_tree_root=empty)
        assert sorted(p.name for p in plugins) == ["x", "y"]

    def test_deduplicates_by_resolved_path(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        plugin_root = repo / "plugins" / "demo"
        _write_manifest(plugin_root, {"name": "demo", "runtime": "ainstein"})
        # Same plugin reached via env var AND user dir AND in-tree
        # plugins/ scan → deduplicated to a single result.
        monkeypatch.setenv("AINSTEIN_PLUGINS", str(plugin_root))
        plugins = PluginLoader.discover(
            user_dir=repo / "plugins", in_tree_root=repo,
        )
        assert [p.name for p in plugins] == ["demo"]

    def test_invalid_plugin_is_skipped_not_raised(self, tmp_path, monkeypatch, caplog):
        bad = tmp_path / "bad"
        good = tmp_path / "good"
        _write_manifest(bad, {"runtime": "ainstein"})  # missing name
        _write_manifest(good, {"name": "good", "runtime": "ainstein"})
        monkeypatch.setenv("AINSTEIN_PLUGINS", f"{bad}:{good}")
        empty = tmp_path / "empty-user-dir"
        plugins = PluginLoader.discover(user_dir=empty, in_tree_root=empty)
        assert [p.name for p in plugins] == ["good"]
        assert any("Skipping plugin" in r.message for r in caplog.records)

    def test_nonexistent_user_dir_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AINSTEIN_PLUGINS", "")
        nonexistent = tmp_path / "does-not-exist"
        plugins = PluginLoader.discover(user_dir=nonexistent, in_tree_root=tmp_path)
        assert plugins == []
