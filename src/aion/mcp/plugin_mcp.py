"""Plugin-supplied MCP server lifecycle management.

A plugin can ship a ``.mcp.json`` at its root declaring stdio MCP servers:

    {
      "mcpServers": {
        "preview": {
          "command": "bash",
          "args": ["${AINSTEIN_PLUGIN_ROOT}/mcp/visual-preview/start.sh"]
        }
      }
    }

``MCPPluginManager`` parses these declarations at plugin-registration time,
substitutes ``${AINSTEIN_PLUGIN_ROOT}`` against the plugin's root path, but
DOES NOT spawn anything yet. Servers are spawned lazily on first
``get_server(plugin, server)`` call, which is what makes
``/archimate-viewer`` cheap until the user actually invokes it.

Lifecycle:

* **Registration**: synchronous, reads ``.mcp.json``, builds a config table.
* **First use**: ``get_server(...)`` constructs a ``StdioServer`` and calls
  ``await server.start()``. Subsequent calls return the same instance.
* **Liveness**: ``get_server`` checks ``is_alive()`` and respawns if dead.
* **Shutdown**: ``atexit`` + SIGTERM/SIGINT signal handlers call
  ``shutdown_all()``. Best-effort — Python's ``atexit`` can't run async,
  so we drive shutdown via a new event loop on the main thread.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import signal
from typing import TYPE_CHECKING

from aion.mcp.stdio_client import StdioServer

if TYPE_CHECKING:
    from aion.skills.plugin import Plugin

logger = logging.getLogger(__name__)


def _substitute(value: str, plugin_root: str) -> str:
    """Replace ``${AINSTEIN_PLUGIN_ROOT}`` (AInstein's plugin-root variable) inside a string."""
    return value.replace("${AINSTEIN_PLUGIN_ROOT}", plugin_root)


class MCPPluginManager:
    """Per-process registry of plugin-supplied stdio MCP servers."""

    def __init__(self) -> None:
        # (plugin_name, server_name) -> resolved config dict
        self._configs: dict[tuple[str, str], dict] = {}
        # (plugin_name, server_name) -> StdioServer instance (created lazily)
        self._servers: dict[tuple[str, str], StdioServer] = {}
        # Serializes the construct-and-store window in get_server so two
        # concurrent coroutines requesting the same (plugin, server) can't
        # each spawn a fresh StdioServer (orphan subprocess + dict overwrite).
        # The lock is held only across dict reads/writes — actual subprocess
        # spawn happens after release, where StdioServer.start has its own
        # internal lock against duplicate spawns.
        self._construct_lock = asyncio.Lock()
        self._atexit_registered = False
        self._signal_handlers_installed = False

    # ------------------------------------------------------------------
    # Registration

    def register_plugin(self, plugin: "Plugin") -> None:
        """Parse the plugin's MCP server declarations and record them.

        Resolution order (Option 2 manifest-driven config, with legacy fallback):

        1. ``mcpServers`` (or ``mcp_servers``) field on ``.ainstein-plugin/plugin.json``
           — inline dict OR a string path to a JSON file with the same schema.
        2. Plugin-root ``.mcp.json`` — legacy default, retained for plugins
           that haven't migrated to the manifest-driven form.

        No-op if neither is present. Malformed input is logged at WARNING
        and the plugin's MCP declarations are skipped — a broken plugin
        shouldn't crash the host.
        """
        servers = plugin.resolve_mcp_config()

        if servers is None:
            # Legacy fallback: read the plugin-root .mcp.json directly.
            path = plugin.mcp_config_path
            if not path.exists():
                return
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                logger.warning("Plugin %s: invalid .mcp.json — %s", plugin.name, e)
                return
            if not isinstance(raw, dict):
                logger.warning("Plugin %s: .mcp.json top-level must be an object", plugin.name)
                return
            servers = raw.get("mcpServers")
            if not isinstance(servers, dict):
                return

        plugin_root = str(plugin.root)
        for server_name, server_cfg in servers.items():
            if not isinstance(server_cfg, dict):
                logger.warning(
                    "Plugin %s server %r: config must be an object", plugin.name, server_name,
                )
                continue
            command = server_cfg.get("command")
            if not isinstance(command, str) or not command:
                logger.warning(
                    "Plugin %s server %r: missing/invalid 'command'", plugin.name, server_name,
                )
                continue
            args = [
                _substitute(str(a), plugin_root)
                for a in (server_cfg.get("args") or [])
            ]
            env_raw = server_cfg.get("env")
            env: dict[str, str] | None = None
            if isinstance(env_raw, dict):
                env = {str(k): _substitute(str(v), plugin_root) for k, v in env_raw.items()}
            cwd_raw = server_cfg.get("cwd")
            cwd = _substitute(str(cwd_raw), plugin_root) if cwd_raw else plugin_root

            self._configs[(plugin.name, server_name)] = {
                "command": _substitute(command, plugin_root),
                "args": args,
                "env": env,
                "cwd": cwd,
            }
            logger.info("Registered MCP server %s/%s", plugin.name, server_name)

    def list_servers(self) -> list[tuple[str, str]]:
        """All registered ``(plugin_name, server_name)`` pairs."""
        return list(self._configs.keys())

    def has_server(self, plugin_name: str, server_name: str) -> bool:
        return (plugin_name, server_name) in self._configs

    def is_alive(self, plugin_name: str, server_name: str) -> bool:
        """True iff the server is spawned and the session was initialized."""
        srv = self._servers.get((plugin_name, server_name))
        return srv is not None and srv.is_alive()

    # ------------------------------------------------------------------
    # Lifecycle

    async def get_server(self, plugin_name: str, server_name: str) -> StdioServer:
        """Return a running StdioServer for the declared (plugin, server).

        Lazy spawn on first call. Respawns if a prior call killed the
        process (e.g. via ``call_tool`` failure). Raises ``KeyError`` if
        the server name isn't declared in any plugin's manifest.

        Concurrent calls for the same key are safe — the construct-and-store
        window is serialized through ``_construct_lock`` so two coroutines
        racing on first use can't each spawn a fresh StdioServer.
        """
        key = (plugin_name, server_name)
        cfg = self._configs.get(key)
        if cfg is None:
            raise KeyError(f"MCP server {plugin_name}/{server_name!r} is not registered")

        # Serialize construct-and-store. The locked region only reads/writes
        # the _servers dict — subprocess spawn happens outside the lock so
        # two different-keyed gets don't serialize on each other's cold-start.
        async with self._construct_lock:
            server = self._servers.get(key)
            if server is None:
                server = StdioServer(
                    command=cfg["command"],
                    args=cfg["args"],
                    env=cfg["env"],
                    cwd=cfg["cwd"],
                )
                self._servers[key] = server
                self._install_shutdown_hooks_once()

        # start() itself has internal idempotent locking, so two coroutines
        # passing this is_alive check are safe — only one actually spawns.
        if not server.is_alive():
            await server.start()
        return server

    async def shutdown_all(self) -> None:
        """Stop every spawned server. Safe to call multiple times."""
        for key, server in list(self._servers.items()):
            try:
                await server.stop(suppress_errors=True)
            except Exception:
                logger.exception("Error stopping MCP server %s/%s", *key)
        self._servers.clear()

    # ------------------------------------------------------------------
    # Shutdown hook installation (atexit + SIGTERM/SIGINT)

    def _install_shutdown_hooks_once(self) -> None:
        if not self._atexit_registered:
            atexit.register(self._atexit_handler)
            self._atexit_registered = True
        if not self._signal_handlers_installed:
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    prior = signal.getsignal(sig)
                    signal.signal(sig, self._make_signal_handler(prior, sig))
                except (ValueError, OSError):
                    # Not on main thread, or signal not available — skip.
                    pass
            self._signal_handlers_installed = True

    def _atexit_handler(self) -> None:
        if not self._servers:
            return
        try:
            asyncio.run(self.shutdown_all())
        except RuntimeError:
            # An event loop is already running (e.g. during nested shutdown);
            # best-effort skip — the loop's own cleanup will catch it.
            logger.debug("MCPPluginManager atexit: event loop already running, skipping")
        except Exception:
            logger.exception("MCPPluginManager atexit handler raised")

    def _make_signal_handler(self, prior, signum_installed):
        """Build a signal handler that runs cleanup then preserves prior semantics.

        - ``prior`` is a callable → invoke it after cleanup.
        - ``prior`` is ``SIG_DFL`` → restore the default handler and re-deliver
          the signal so the default behavior fires (e.g. terminate on SIGTERM,
          raise KeyboardInterrupt on SIGINT). Without this, replacing the
          default would silently swallow Ctrl+C and SIGTERM.
        - ``prior`` is ``SIG_IGN`` → preserve the explicit-ignore by doing
          nothing after cleanup.
        """
        def _handler(signum, frame):
            self._atexit_handler()
            if callable(prior):
                try:
                    prior(signum, frame)
                except Exception:
                    logger.exception("Prior signal handler raised")
            elif prior is signal.SIG_DFL:
                # Restore default and re-deliver so the default semantics apply.
                signal.signal(signum_installed, signal.SIG_DFL)
                os.kill(os.getpid(), signum_installed)
            # SIG_IGN: caller explicitly chose to ignore — honor it.
        return _handler


# ----------------------------------------------------------------------
# Singleton

_global_manager: MCPPluginManager | None = None


def get_mcp_plugin_manager() -> MCPPluginManager:
    """Process-wide MCPPluginManager singleton."""
    global _global_manager
    if _global_manager is None:
        _global_manager = MCPPluginManager()
    return _global_manager


def _reset_mcp_plugin_manager_for_tests() -> None:
    """Drop the cached manager. Tests call this to avoid cross-test pollution."""
    global _global_manager
    _global_manager = None
