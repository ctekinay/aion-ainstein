"""Plugin discovery from env var, user dir, and the in-tree deployment dir.

Discovery order (deterministic):
  1. Explicit paths from the `AINSTEIN_PLUGINS` env var (colon-separated).
  2. Auto-discovery under `~/.ainstein/plugins/` (each child dir is a
     candidate plugin root if it contains `.ainstein-plugin/`).
  3. Auto-discovery under `<repo>/plugins/` — each child dir that contains
     `.ainstein-plugin/` is a candidate. `plugins/ainstein-kernel/`
     (role=kernel), `plugins/esa-workflow/`, and
     `plugins/enterpower-architecture/` are the bundled plugins, committed
     to the repo; other entries under `plugins/` are operator-deployed and
     gitignored.

In-tree is LAST so explicit env-var and user-dir plugins win the
`conflicts_with` tie-breaker. Duplicate paths are deduplicated by
resolved-absolute path. Malformed plugins are logged and skipped — the
loader never raises during discovery so an invalid third-party plugin
can't break server startup. The multi-plugin registry is where conflicts
between *valid* plugins surface.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from aion.skills.plugin import Plugin, PluginManifestError, load_plugin_manifest

logger = logging.getLogger(__name__)

DEFAULT_USER_PLUGIN_DIR = Path.home() / ".ainstein" / "plugins"

# Project root = parent of src/aion/skills/plugin_loader.py up four levels:
# .../esa-ainstein-artifacts/src/aion/skills/plugin_loader.py
DEFAULT_IN_TREE_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class PluginLoader:
    """Discovers plugin roots from configured sources."""

    @staticmethod
    def discover(
        env_var: str = "AINSTEIN_PLUGINS",
        user_dir: Path | None = None,
        in_tree_root: Path | None = None,
    ) -> list[Plugin]:
        """Discover all plugins from env var, user dir, and the in-tree root.

        Args:
            env_var: Name of the env var holding colon-separated absolute
                paths to plugin roots. Defaults to `AINSTEIN_PLUGINS`.
            user_dir: Directory whose immediate children are scanned for
                `.ainstein-plugin/` subdirectories. Defaults to
                `~/.ainstein/plugins/`. Pass `None` to use the default;
                pass a non-existent path to skip user-dir discovery.
            in_tree_root: Repo root whose `plugins/` subdirectory is
                scanned. Each child of `<in_tree_root>/plugins/` that
                contains `.ainstein-plugin/` is added as a candidate.
                Defaults to the project root.

        Returns:
            Plugins in discovery order, deduplicated by resolved path.
            Invalid manifests are logged and skipped.
        """
        candidate_paths: list[Path] = []

        # 1. Explicit env var paths (platform-native separator: ":" on POSIX, ";" on Windows)
        env_val = os.environ.get(env_var, "")
        for raw in env_val.split(os.pathsep):
            raw = raw.strip()
            if raw:
                candidate_paths.append(Path(raw).resolve())

        # 2. User dir auto-discovery
        if user_dir is None:
            user_dir = DEFAULT_USER_PLUGIN_DIR
        if user_dir.is_dir():
            for child in sorted(user_dir.iterdir()):
                if child.is_dir() and (child / ".ainstein-plugin").is_dir():
                    candidate_paths.append(child.resolve())

        # 3. In-tree deployment dir: <repo>/plugins/*/
        if in_tree_root is None:
            in_tree_root = DEFAULT_IN_TREE_ROOT
        plugins_dir = in_tree_root / "plugins"
        if plugins_dir.is_dir():
            for child in sorted(plugins_dir.iterdir()):
                if child.is_dir() and (child / ".ainstein-plugin").is_dir():
                    candidate_paths.append(child.resolve())

        # Dedup preserving order
        seen: set[Path] = set()
        ordered: list[Path] = []
        for p in candidate_paths:
            if p not in seen:
                seen.add(p)
                ordered.append(p)

        plugins: list[Plugin] = []
        for plugin_root in ordered:
            try:
                plugin = load_plugin_manifest(plugin_root)
                plugins.append(plugin)
                logger.info(
                    "Loaded plugin %r v%s from %s",
                    plugin.name, plugin.version, plugin_root,
                )
            except PluginManifestError as e:
                logger.warning("Skipping plugin at %s: %s", plugin_root, e)
            except Exception as e:
                logger.exception("Unexpected error loading plugin at %s: %s", plugin_root, e)

        return plugins
