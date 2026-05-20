"""PostToolUse hook firing for plugin-declared scripts.

Plugin authors declare hooks in their AInstein manifest
(``.ainstein-plugin/plugin.json``'s ``hooks`` field — either inline or
referencing a separate JSON file). Schema mirrors the standard plugin-host
hook convention so the same script can be reused across hosts:

    {
      "PostToolUse": [
        {
          "matcher": "Write",
          "hooks": [
            {"type": "command", "command": "${AINSTEIN_PLUGIN_ROOT}/hooks/my-hook.sh"}
          ]
        }
      ]
    }

**AInstein's file_path semantics** — note for plugin authors:

AInstein's artifact-save path stores blobs in SQLite, not on disk. The
``file_path`` passed to PostToolUse hooks fired from ``save_artifact``
is the **artifact filename only** (e.g. ``"explorer.html"``), not a
full filesystem path. Hooks that need the artifact's content must
either (a) match by filename pattern and use the AInstein API to
download the artifact by ID, or (b) be triggered from a different
call site that does have a real file on disk.

A plugin's hook script written for the partner agentic-IDE host's
``Write`` tool semantics (where ``file_path`` is a real on-disk path)
won't fire usefully from AInstein's artifact-save unless its matcher
happens to align with an artifact filename pattern.

**Module-level functions, no class.** The plan's single firing point
(artifact-save → PostToolUse/Write) doesn't justify a runner class
with state. ``fire_post_tool_use(file_path)`` iterates every loaded
plugin's hook declarations and fires every matching script
synchronously with a per-script 30s timeout. Best-effort — exit codes
are advisory; stderr is logged.

**Environment passed to hooks**:

* ``AINSTEIN_PLUGIN_ROOT`` substituted in the ``command`` field at
  registration time (not at firing time).
* The parent process env minus secrets matching
  ``AINSTEIN_*``, ``*_KEY``, ``*_TOKEN``, ``*_PASSWORD``, ``*_SECRET``.
* Per-hook override via the optional ``env: [VAR1, VAR2, ...]`` field
  in the hook config — when present, only these vars (after secret
  filtering) are passed.

Hook contract designed for portability across plugin-supporting hosts.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from typing import Any

from aion.skills.multi_registry import get_multi_registry

logger = logging.getLogger(__name__)


# Default hook execution timeout — generous enough for legitimate work
# (e.g. running a build step), short enough to fail loudly on a runaway
# script. Matches the value documented in the migration plan.
_HOOK_TIMEOUT_SECONDS = 30

# Secret patterns stripped from the env passed to hook scripts.
# Compiled once for efficiency across many hook fires.
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^AINSTEIN_.*$"),
    re.compile(r".*_KEY$"),
    re.compile(r".*_TOKEN$"),
    re.compile(r".*_PASSWORD$"),
    re.compile(r".*_SECRET$"),
]


def _is_secret_env_name(name: str) -> bool:
    return any(p.match(name) for p in _SECRET_PATTERNS)


def _filter_env(
    parent_env: dict[str, str],
    override_allowlist: list[str] | None = None,
) -> dict[str, str]:
    """Return a copy of ``parent_env`` minus secrets, or restricted to ``override_allowlist``.

    When the hook config declares ``env: [VAR1, ...]``, only those vars
    are forwarded — but secret-pattern matches are still excluded even
    if explicitly listed (defence in depth).
    """
    if override_allowlist is not None:
        candidates = {k: parent_env[k] for k in override_allowlist if k in parent_env}
    else:
        candidates = dict(parent_env)
    return {k: v for k, v in candidates.items() if not _is_secret_env_name(k)}


def _matcher_matches(matcher: Any, tool_name: str) -> bool:
    """Apply a single matcher entry to a tool name.

    The hook matcher convention treats the value as a string compared
    against the tool name — exact match suffices for the canonical use
    cases (``"Write"``, ``"Edit"``, etc.). For forward compatibility we
    also accept a list of strings (any-match).
    """
    if matcher is None or matcher == "":
        return True  # absent matcher fires on every tool
    if isinstance(matcher, str):
        return matcher == tool_name
    if isinstance(matcher, list):
        return any(isinstance(m, str) and m == tool_name for m in matcher)
    return False


def _fire_one_script(
    command: str,
    payload: dict,
    env_allowlist: list[str] | None,
) -> None:
    """Spawn one hook script. Errors are logged, never propagated."""
    env = _filter_env(dict(os.environ), env_allowlist)
    try:
        result = subprocess.run(
            command,
            shell=True,
            input=json.dumps(payload),
            text=True,
            timeout=_HOOK_TIMEOUT_SECONDS,
            env=env,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Hook %r timed out after %ds", command, _HOOK_TIMEOUT_SECONDS)
        return
    except Exception:
        logger.exception("Hook %r failed to spawn", command)
        return

    if result.stderr:
        for line in result.stderr.splitlines():
            logger.info("Hook %r stderr: %s", command, line)
    if result.returncode != 0:
        logger.info("Hook %r exited %d (advisory)", command, result.returncode)


def _fire_plugin_hooks(plugin, post_tool_use: list, tool_name: str, payload: dict) -> None:
    """Fire one plugin's matching PostToolUse hooks with a prepared payload.

    Extracted so the materialized-real-path branch and the filename-only
    branch share IDENTICAL matcher/command/env/${AINSTEIN_PLUGIN_ROOT}
    handling — the only difference between them is the ``file_path`` value
    already baked into ``payload``.
    """
    for entry in post_tool_use:
        if not isinstance(entry, dict):
            continue
        if not _matcher_matches(entry.get("matcher"), tool_name):
            continue
        inner_hooks = entry.get("hooks")
        if not isinstance(inner_hooks, list):
            continue
        for hook in inner_hooks:
            if not isinstance(hook, dict):
                continue
            command = hook.get("command")
            if not isinstance(command, str) or not command:
                continue
            # Substitute the plugin's root variable in the command path.
            # The MCPPluginManager performs this same substitution for
            # mcpServers entries; we duplicate it here so hooks can
            # reference scripts under the plugin tree without forcing
            # the plugin author to pre-resolve paths in the manifest.
            resolved_command = command.replace(
                "${AINSTEIN_PLUGIN_ROOT}", str(plugin.root),
            )
            env_allowlist = hook.get("env")
            if env_allowlist is not None and not isinstance(env_allowlist, list):
                env_allowlist = None  # ignore malformed override
            _fire_one_script(resolved_command, payload, env_allowlist)


def fire_post_tool_use(
    file_path: str,
    tool_name: str = "Write",
    *,
    content: str | None = None,
    content_type: str | None = None,
) -> None:
    """Fire every matching PostToolUse hook across all loaded plugins.

    For each plugin in the multi-registry, resolves its hooks config
    (inline or path-referenced from ``.ainstein-plugin/plugin.json``),
    looks up the ``PostToolUse`` array, walks each matcher block, and
    spawns every command in the inner ``hooks`` array whose matcher
    accepts ``tool_name``.

    Stdin payload, canonical cross-host-compatible form:

        {"tool_name": "<name>", "tool_input": {"file_path": "<path>"}}

    **Per-plugin file_path semantics (Phase 3, hard part C — A5 opt-in):**
    by default (and for every plugin that does NOT declare
    ``requires_host_api: {"artifact_materialization": ...}``) ``file_path``
    is the artifact *filename only* — unchanged, byte-identical to before;
    existing hook-payload tests are protected by construction. For a
    plugin that DOES require the artifact-materialization host capability
    AND ``content`` is available, the artifact is materialized to a real
    ephemeral on-disk path (SQLite stays authoritative, no sync-back) and
    that real path is passed for the duration of that plugin's hooks, then
    cleaned up. ``content``/``content_type`` are keyword-only and optional
    so existing callers are unaffected.

    Synchronous and best-effort: 30s timeout per hook, exceptions
    logged, advisory exit codes. No exceptions propagate to the caller.
    """
    filename_payload = {
        "tool_name": tool_name, "tool_input": {"file_path": file_path},
    }

    from aion.skills.artifact_materialization import (
        materialized_artifact,
        plugin_requires_materialization,
    )

    multi = get_multi_registry()
    for plugin_name in multi.list_plugins():
        plugin = multi.get_plugin(plugin_name)
        if plugin is None:
            # Legacy in-tree synthesized plugin (pre-commit-4 fallback); no manifest object.
            continue
        hooks_config = plugin.resolve_hooks_config()
        if hooks_config is None:
            continue

        post_tool_use = hooks_config.get("PostToolUse")
        if not isinstance(post_tool_use, list):
            continue

        if content is not None and plugin_requires_materialization(plugin):
            # Opt-in: project the SQLite blob onto a real path for this
            # plugin's hooks only, then clean up (ephemeral, no sync-back).
            with materialized_artifact(file_path, content) as real_path:
                materialized_payload = {
                    "tool_name": tool_name,
                    "tool_input": {"file_path": str(real_path)},
                }
                _fire_plugin_hooks(
                    plugin, post_tool_use, tool_name, materialized_payload,
                )
        else:
            # Default / non-requiring: filename-only payload — unchanged.
            _fire_plugin_hooks(
                plugin, post_tool_use, tool_name, filename_payload,
            )
