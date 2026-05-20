"""Plugin manifest data model and parser.

A plugin is a directory containing a `.ainstein-plugin/` subdirectory with
a `plugin.json` manifest. The plugin's other assets (skills, hooks, MCP
servers, templates, shared references) live as siblings of `.ainstein-plugin/`.

  <plugin-root>/
    .ainstein-plugin/
      plugin.json
      skills-registry.yaml
      thresholds.yaml
    .mcp.json
    hooks/hooks.json
    mcp/<server>/start.sh
    shared-references/<group>/*.md
    skills/<skill>/SKILL.md
    templates/<template>/

Plugin discovery and multi-plugin orchestration live in plugin_loader.py
and multi_registry.py (commit 3).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PluginManifestError(Exception):
    """Raised when a plugin manifest is missing, malformed, or has the wrong runtime."""


# Valid plugin roles. `kernel` is host-enforced policy (non-removable,
# non-shadowable, implicitly always-loaded) — enforcement lands in later
# phases; Phase 1 only parses + validates the declared value.
VALID_PLUGIN_ROLES = ("kernel", "domain")
DEFAULT_PLUGIN_ROLE = "domain"
DEFAULT_MANIFEST_VERSION = "1.0"

# Host-side half of the two-sided versioning contract (Amendment A3):
# what host capabilities + provided major versions AInstein offers.
# Plugins declare `requires_host_api`; the host declares what it provides.
# Capabilities are registered as the phases that implement them land.
#   - `artifact_materialization` (major 1): registered in Phase 3 — the
#     host projects a SQLite-stored artifact onto a real filesystem path
#     for the duration of a PostToolUse hook (ephemeral, SQLite remains
#     authoritative, no sync-back). See aion.skills.artifact_materialization.
HOST_CAPABILITIES: dict[str, int] = {
    "artifact_materialization": 1,
}


def host_supports(capability: str, required_major: int) -> bool:
    """True iff the host provides `capability` at >= `required_major`.

    Defined now so the host side of the contract is concrete (A3), but
    NOT called during load in Phase 1 — enforcement is deferred so adding
    `requires_host_api` to a manifest can never break loading yet.
    """
    provided = HOST_CAPABILITIES.get(capability)
    return provided is not None and provided >= required_major


@dataclass
class PluginManifest:
    """Parsed content of `.ainstein-plugin/plugin.json`.

    The ``raw`` dict carries the full parsed JSON so callers can read
    optional fields (``hooks``, ``mcpServers``, future additions) without
    requiring a schema update here. Use the ``resolve_*_config`` helpers
    on ``Plugin`` to dereference path-vs-inline declarations.

    ``role`` / ``manifest_version`` / ``requires_host_api`` are the
    Phase-1 additive contract fields. All default safely so existing and
    external manifests (incl. enterpower's placeholder) keep loading
    unchanged; ``requires_host_api`` is parsed but NOT enforced in Phase 1.
    """

    name: str
    runtime: str
    version: str = "0.0.0"
    description: str = ""
    author: dict[str, Any] = field(default_factory=dict)
    role: str = DEFAULT_PLUGIN_ROLE
    manifest_version: str = DEFAULT_MANIFEST_VERSION
    requires_host_api: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plugin:
    """A discovered plugin — manifest plus resolved paths to its assets.

    `root` is the directory containing `.ainstein-plugin/`. Use the
    property accessors for asset paths; they don't check existence —
    callers should handle missing optional assets (`mcp_config_path`,
    `hooks_dir`, etc.) gracefully.
    """

    root: Path
    manifest: PluginManifest

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def role(self) -> str:
        """Plugin role: ``kernel`` | ``domain`` (default ``domain``).

        Phase 1: parsed/validated only. Host-enforced kernel policy
        (non-removable, non-shadowable, always-loaded, rejected by every
        enable/disable mutation path) lands in Phase 4.
        """
        return self.manifest.role

    @property
    def manifest_version(self) -> str:
        return self.manifest.manifest_version

    @property
    def requires_host_api(self) -> dict[str, Any]:
        """Declared host-capability requirements (Phase 1: parsed, NOT
        enforced — see ``host_supports``)."""
        return self.manifest.requires_host_api

    @property
    def plugin_dir(self) -> Path:
        return self.root / ".ainstein-plugin"

    @property
    def registry_path(self) -> Path:
        return self.plugin_dir / "skills-registry.yaml"

    @property
    def thresholds_path(self) -> Path:
        return self.plugin_dir / "thresholds.yaml"

    @property
    def skills_dir(self) -> Path:
        return self.root / "skills"

    @property
    def shared_refs_dir(self) -> Path:
        return self.root / "shared-references"

    @property
    def mcp_config_path(self) -> Path:
        return self.root / ".mcp.json"

    @property
    def hooks_dir(self) -> Path:
        return self.root / "hooks"

    @property
    def hooks_config_path(self) -> Path:
        return self.hooks_dir / "hooks.json"

    @property
    def templates_dir(self) -> Path:
        return self.root / "templates"

    # -- manifest-driven config resolution (Option 2 layout) -----------

    def _resolve_config_field(self, field_name: str) -> dict[str, Any] | None:
        """Resolve a manifest config field (``hooks`` / ``mcpServers``).

        Each field may be either:

        * **inline**: a dict matching the field's schema (returned as-is), or
        * **path-referenced**: a string giving a path (relative or absolute)
          to a JSON file whose top-level dict matches the schema.

        Relative paths resolve against the plugin root. Returns ``None`` if
        the field is absent, malformed, or its referenced file is missing
        or unreadable (logged at WARNING for malformed cases).
        """
        value = self.manifest.raw.get(field_name)
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            target = (self.root / value).resolve() if not Path(value).is_absolute() else Path(value)
            if not target.exists():
                logger.warning(
                    "Plugin %s: manifest %r references missing file %s",
                    self.name, field_name, target,
                )
                return None
            try:
                import json as _json
                parsed = _json.loads(target.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(
                    "Plugin %s: failed to read %r config from %s: %s",
                    self.name, field_name, target, e,
                )
                return None
            if not isinstance(parsed, dict):
                logger.warning(
                    "Plugin %s: %s top-level must be a JSON object",
                    self.name, target,
                )
                return None
            return parsed
        logger.warning(
            "Plugin %s: manifest %r must be an object or a string path (got %s)",
            self.name, field_name, type(value).__name__,
        )
        return None

    def resolve_hooks_config(self) -> dict[str, Any] | None:
        """Return the resolved ``hooks`` config from the manifest.

        Schema (compatible with standard plugin-host hook conventions):

            {
              "PostToolUse": [
                {
                  "matcher": "Write",
                  "hooks": [
                    {"type": "command", "command": "<absolute or substituted path>"}
                  ]
                }
              ]
            }

        ``None`` means this plugin declares no hooks.
        """
        return self._resolve_config_field("hooks")

    def resolve_mcp_config(self) -> dict[str, Any] | None:
        """Return the resolved ``mcpServers`` config from the manifest.

        Schema (compatible with standard plugin-host MCP conventions):

            {
              "preview": {"command": "...", "args": [...], "env": {...}, "cwd": "..."},
              ...
            }

        ``None`` means this plugin declares no MCP servers via the manifest.
        For backward compatibility, the MCP loader also falls back to the
        plugin-root ``.mcp.json`` if neither the inline nor the path-ref form
        is present in the manifest.
        """
        # The canonical field name is ``mcpServers`` (camelCase per the cross-host
        # plugin manifest convention). Some plugin authors may type
        # ``mcp_servers`` (Python convention) — accept both.
        for name in ("mcpServers", "mcp_servers"):
            resolved = self._resolve_config_field(name)
            if resolved is not None:
                return resolved
        return None


def load_plugin_manifest(plugin_root: Path) -> Plugin:
    """Load a `Plugin` from a directory containing `.ainstein-plugin/plugin.json`.

    Raises `PluginManifestError` if the manifest is missing, malformed,
    or declares a runtime other than "ainstein".
    """
    plugin_root = Path(plugin_root).resolve()
    manifest_path = plugin_root / ".ainstein-plugin" / "plugin.json"

    if not manifest_path.exists():
        raise PluginManifestError(f"plugin.json not found at {manifest_path}")

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PluginManifestError(f"{manifest_path}: invalid JSON — {e}") from e

    if not isinstance(data, dict):
        raise PluginManifestError(f"{manifest_path}: top-level must be a JSON object")

    name = data.get("name")
    if not name or not isinstance(name, str):
        raise PluginManifestError(f"{manifest_path}: missing or invalid 'name' field")

    runtime = data.get("runtime")
    if runtime != "ainstein":
        raise PluginManifestError(
            f"{manifest_path}: runtime must be 'ainstein', got {runtime!r}"
        )

    author = data.get("author", {})
    if not isinstance(author, dict):
        raise PluginManifestError(
            f"{manifest_path}: 'author' must be a JSON object, got {type(author).__name__}"
        )

    # Phase-1 additive contract fields. All optional with safe defaults so
    # existing/external manifests (incl. enterpower's placeholder) keep
    # loading unchanged.
    role = data.get("role", DEFAULT_PLUGIN_ROLE)
    if role not in VALID_PLUGIN_ROLES:
        # Reject unknown roles EARLY (reviewer Phase-1 note) — a typo'd
        # role must not silently change host policy behavior later.
        raise PluginManifestError(
            f"{manifest_path}: 'role' must be one of {VALID_PLUGIN_ROLES}, "
            f"got {role!r}"
        )

    manifest_version = str(data.get("manifest_version", DEFAULT_MANIFEST_VERSION))

    requires_host_api = data.get("requires_host_api", {})
    if not isinstance(requires_host_api, dict):
        raise PluginManifestError(
            f"{manifest_path}: 'requires_host_api' must be a JSON object, "
            f"got {type(requires_host_api).__name__}"
        )
    # Parsed but NOT enforced in Phase 1 (host_supports() exists but is
    # not called at load) — adding the field can never break loading yet.

    manifest = PluginManifest(
        name=name,
        runtime=runtime,
        version=data.get("version", "0.0.0"),
        description=data.get("description", ""),
        author=author,
        role=role,
        manifest_version=manifest_version,
        requires_host_api=requires_host_api,
        raw=data,
    )
    return Plugin(root=plugin_root, manifest=manifest)
