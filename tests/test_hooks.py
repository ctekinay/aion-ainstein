"""Tests for the PostToolUse hook firing module.

No real subprocesses spawned. Hooks invoke ``/bin/sh -c`` with simple
commands that write to a sentinel file in tmp_path — we verify the
sentinel afterward to confirm the hook fired and received the correct
stdin payload.
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import pytest

from aion.skills import hooks as hooks_module
from aion.skills.hooks import (
    _filter_env,
    _is_secret_env_name,
    _matcher_matches,
    fire_post_tool_use,
)
from aion.skills.multi_registry import (
    MultiPluginRegistry,
    _reset_multi_registry_for_tests,
)
from aion.skills.plugin import load_plugin_manifest


# ---------------------------------------------------------------------- helpers


def _plugin_with_hooks(
    root: Path,
    plugin_name: str,
    hooks_config: dict | str | None,
    skills: list[dict] | None = None,
) -> Path:
    plugin_dir = root / ".ainstein-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": plugin_name,
        "runtime": "ainstein",
        "version": "0.0.1",
    }
    if hooks_config is not None:
        manifest["hooks"] = hooks_config
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    import yaml as _yaml
    (plugin_dir / "skills-registry.yaml").write_text(
        _yaml.safe_dump({"skills": skills or []}, sort_keys=False),
        encoding="utf-8",
    )
    skills_dir = root / "skills"
    skills_dir.mkdir(exist_ok=True)
    for s in (skills or []):
        sdir = skills_dir / s["name"]
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "SKILL.md").write_text(
            f"---\nname: {s['name']}\ndescription: x\n---\nbody\n", encoding="utf-8",
        )
    return root


def _install_registry_with(plugin_root: Path) -> MultiPluginRegistry:
    """Build a multi-registry, install as singleton, load."""
    _reset_multi_registry_for_tests()
    from aion.skills.multi_registry import _global_multi  # noqa
    import aion.skills.multi_registry as mr

    multi = MultiPluginRegistry()
    multi.add_plugin_from_object(load_plugin_manifest(plugin_root))
    multi.load()
    mr._global_multi = multi
    return multi


# ---------------------------------------------------------------------- _is_secret_env_name / _filter_env


class TestSecretEnvFiltering:
    @pytest.mark.parametrize("name,is_secret", [
        ("AINSTEIN_FOO", True),
        ("AINSTEIN_API_KEY", True),
        ("OPENAI_API_KEY", True),
        ("MY_TOKEN", True),
        ("DB_PASSWORD", True),
        ("STRIPE_SECRET", True),
        ("HOME", False),
        ("PATH", False),
        ("USER", False),
        ("NODE_PATH", False),
    ])
    def test_secret_pattern_match(self, name, is_secret):
        assert _is_secret_env_name(name) is is_secret

    def test_filter_env_strips_secrets(self):
        env = {"HOME": "/h", "AINSTEIN_KEY": "x", "OPENAI_API_KEY": "y", "PATH": "/p"}
        out = _filter_env(env)
        assert out == {"HOME": "/h", "PATH": "/p"}

    def test_filter_env_with_allowlist_restricts_then_filters(self):
        env = {"HOME": "/h", "AINSTEIN_KEY": "x", "PATH": "/p", "NODE_PATH": "/np"}
        out = _filter_env(env, override_allowlist=["HOME", "NODE_PATH", "AINSTEIN_KEY"])
        # AINSTEIN_KEY removed even though allowlisted — defence in depth.
        assert out == {"HOME": "/h", "NODE_PATH": "/np"}


# ---------------------------------------------------------------------- _matcher_matches


class TestMatcher:
    def test_exact_string_match(self):
        assert _matcher_matches("Write", "Write") is True
        assert _matcher_matches("Write", "Edit") is False

    def test_empty_or_none_matches_everything(self):
        assert _matcher_matches(None, "Write") is True
        assert _matcher_matches("", "Edit") is True

    def test_list_any_match(self):
        assert _matcher_matches(["Write", "Edit"], "Edit") is True
        assert _matcher_matches(["Write", "Edit"], "Bash") is False

    def test_invalid_matcher_rejects(self):
        assert _matcher_matches(123, "Write") is False
        assert _matcher_matches({"x": 1}, "Write") is False


# ---------------------------------------------------------------------- fire_post_tool_use


def _hook_script_command(sentinel: Path) -> str:
    """A POSIX shell command that writes the stdin payload into ``sentinel``.

    Using ``cat`` (universally available) so the test doesn't need Python.
    """
    return f"cat > {sentinel}"


class TestFirePostToolUse:
    def test_inline_hooks_fire_on_matching_tool(self, tmp_path):
        sentinel = tmp_path / "hook-fired.json"
        hooks_config = {
            "PostToolUse": [{
                "matcher": "Write",
                "hooks": [{"type": "command", "command": _hook_script_command(sentinel)}],
            }]
        }
        root = _plugin_with_hooks(tmp_path / "p", "demo", hooks_config=hooks_config)
        _install_registry_with(root)

        fire_post_tool_use("my-artifact.html", tool_name="Write")

        assert sentinel.exists(), "hook script did not write the sentinel"
        payload = json.loads(sentinel.read_text(encoding="utf-8"))
        assert payload == {
            "tool_name": "Write",
            "tool_input": {"file_path": "my-artifact.html"},
        }

    def test_non_matching_tool_does_not_fire(self, tmp_path):
        sentinel = tmp_path / "hook-fired.json"
        hooks_config = {
            "PostToolUse": [{
                "matcher": "Write",
                "hooks": [{"type": "command", "command": _hook_script_command(sentinel)}],
            }]
        }
        root = _plugin_with_hooks(tmp_path / "p", "demo", hooks_config=hooks_config)
        _install_registry_with(root)

        fire_post_tool_use("anything", tool_name="Edit")  # mismatched

        assert not sentinel.exists()

    def test_path_referenced_hooks_resolved(self, tmp_path):
        """When manifest "hooks" is a string path, the file is loaded and parsed."""
        sentinel = tmp_path / "hook-fired.json"
        hooks_json_path = tmp_path / "p" / ".ainstein-plugin" / "hooks.json"
        hooks_inner = {
            "PostToolUse": [{
                "matcher": "Write",
                "hooks": [{"type": "command", "command": _hook_script_command(sentinel)}],
            }]
        }
        root = _plugin_with_hooks(
            tmp_path / "p", "demo", hooks_config="./.ainstein-plugin/hooks.json",
        )
        hooks_json_path.write_text(json.dumps(hooks_inner), encoding="utf-8")
        _install_registry_with(root)

        fire_post_tool_use("x.txt", tool_name="Write")
        assert sentinel.exists()

    def test_ainstein_plugin_root_substituted_in_command(self, tmp_path):
        sentinel = tmp_path / "hook-fired.json"
        # Use ${AINSTEIN_PLUGIN_ROOT} in the command — should resolve to plugin root.
        hooks_config = {
            "PostToolUse": [{
                "matcher": "Write",
                "hooks": [{
                    "type": "command",
                    "command": f"cat > ${{AINSTEIN_PLUGIN_ROOT}}/../hook-fired.json",
                }],
            }]
        }
        plugin_root = tmp_path / "p"
        _plugin_with_hooks(plugin_root, "demo", hooks_config=hooks_config)
        _install_registry_with(plugin_root)

        fire_post_tool_use("y", tool_name="Write")
        assert sentinel.exists()

    def test_no_hooks_config_is_a_noop(self, tmp_path):
        root = _plugin_with_hooks(tmp_path / "p", "demo", hooks_config=None)
        _install_registry_with(root)
        # Doesn't raise; nothing to assert beyond "no exception."
        fire_post_tool_use("x", tool_name="Write")

    def test_timeout_logged_does_not_raise(self, tmp_path, monkeypatch, caplog):
        """A hung hook is killed after the configured timeout."""
        # Shorten the timeout to keep the test fast.
        monkeypatch.setattr(hooks_module, "_HOOK_TIMEOUT_SECONDS", 1)

        hooks_config = {
            "PostToolUse": [{
                "matcher": "Write",
                "hooks": [{"type": "command", "command": "sleep 10"}],
            }]
        }
        root = _plugin_with_hooks(tmp_path / "p", "demo", hooks_config=hooks_config)
        _install_registry_with(root)

        # Should NOT raise; just log a warning.
        fire_post_tool_use("x", tool_name="Write")

        assert any("timed out" in r.message for r in caplog.records)

    def test_nonzero_exit_logged_not_raised(self, tmp_path, caplog):
        import logging
        caplog.set_level(logging.INFO, logger="aion.skills.hooks")
        hooks_config = {
            "PostToolUse": [{
                "matcher": "Write",
                "hooks": [{"type": "command", "command": "exit 7"}],
            }]
        }
        root = _plugin_with_hooks(tmp_path / "p", "demo", hooks_config=hooks_config)
        _install_registry_with(root)
        fire_post_tool_use("x", tool_name="Write")
        assert any("exited 7" in r.message for r in caplog.records)

    def test_no_loaded_plugins_is_a_noop(self, tmp_path):
        """When no plugin exposes a hooks block, fire is a no-op."""
        # Build a multi-registry with no hooks-declaring plugins.
        root = _plugin_with_hooks(tmp_path / "p", "demo", hooks_config=None)
        _install_registry_with(root)
        fire_post_tool_use("x", tool_name="Write")  # no error
