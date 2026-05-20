"""Long-lived stdio MCP client.

The MCP SDK's ``stdio_client`` is an ``@asynccontextmanager`` that spawns the
subprocess on enter and tears it down on exit. For plugin-supplied servers
(e.g. the enterpower-architecture ``preview`` server backing Vite) we need
the process to **survive across many tool calls** — paying the Vite cold-start
on every ``/archimate-viewer`` invocation is unworkable.

``StdioServer`` keeps two contexts open across the server's lifetime:

* the outer ``stdio_client`` context (owns the subprocess + reader/writer
  tasks), and
* the inner ``ClientSession`` context (owns the JSON-RPC session state).

Manual ``__aenter__`` / ``__aexit__`` is the canonical Python pattern for
context lifetimes that exceed a single ``async with``. The MCP SDK is built
on ``@asynccontextmanager`` so this works correctly — see CPython's
``contextlib.asynccontextmanager`` for how generator state is preserved
between calls.

Liveness is tracked via the ``_started`` flag, which is set after a
successful ``initialize()`` and cleared on ``stop()`` or on any call_tool
failure. The next call after a failure transparently respawns the
subprocess by re-entering both contexts.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)


def _extract_text(result: Any) -> str:
    """Reduce an MCP tool-call result to a plain string for callers.

    ``ClientSession.call_tool`` returns a ``CallToolResult`` whose ``content``
    is a list of content blocks. Most callers want a single string; we
    concatenate textual blocks and skip non-text content with a placeholder
    so the output is debuggable.
    """
    content = getattr(result, "content", None)
    if content is None:
        return ""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
            continue
        # Image / resource / other blocks — note their presence without dumping.
        kind = getattr(block, "type", type(block).__name__)
        parts.append(f"[non-text block: {kind}]")
    return "\n".join(parts)


class StdioServer:
    """One long-lived stdio MCP server process plus its JSON-RPC session."""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ):
        self.command = command
        self.args = list(args or [])
        self.env = dict(env) if env else None
        self.cwd = str(cwd) if cwd is not None else None

        self._session: ClientSession | None = None
        self._stdio_cm: Any = None
        self._session_cm: ClientSession | None = None
        self._started = False
        self._lock = asyncio.Lock()

    def is_alive(self) -> bool:
        """Cheap liveness check — does not exercise the session."""
        return self._started and self._session is not None

    async def start(self) -> None:
        """Spawn the subprocess and initialize the MCP session.

        No-op if already started. Safe to call concurrently — serialized
        via an internal lock so two coroutines racing on first use don't
        spawn duplicate processes.
        """
        async with self._lock:
            if self._started:
                return

            params = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=self.env,
                cwd=self.cwd,
            )
            stdio_cm = stdio_client(params)
            try:
                read, write = await stdio_cm.__aenter__()
            except Exception:
                logger.exception("StdioServer failed to spawn process: command=%r args=%r", self.command, self.args)
                raise

            session_cm = ClientSession(read, write)
            try:
                session = await session_cm.__aenter__()
                await session.initialize()
            except Exception:
                # Roll back the stdio context if session init fails.
                try:
                    await stdio_cm.__aexit__(None, None, None)
                except Exception:
                    logger.warning("Cleanup of stdio context after failed init also raised", exc_info=True)
                logger.exception("StdioServer ClientSession.initialize failed")
                raise

            self._stdio_cm = stdio_cm
            self._session_cm = session_cm
            self._session = session
            self._started = True
            logger.info("StdioServer started: command=%s", self.command)

    async def list_tools(self) -> list[Any]:
        """Return the server's advertised tool list (auto-starts if needed)."""
        if not self._started:
            await self.start()
        assert self._session is not None
        result = await self._session.list_tools()
        return list(result.tools)

    async def call_tool(self, name: str, arguments: dict | None = None) -> str:
        """Invoke a tool, auto-starting and auto-respawning on failure.

        Returns the textual content of the call result via ``_extract_text``.
        Errors during the call mark the server dead and propagate — the
        next call attempts a fresh spawn.
        """
        if not self._started:
            await self.start()
        assert self._session is not None
        try:
            result = await self._session.call_tool(name, arguments or {})
        except Exception as e:
            logger.warning(
                "stdio MCP call_tool(%s) failed (%s) — marking server dead for next call",
                name, e,
            )
            await self.stop(suppress_errors=True)
            raise
        return _extract_text(result)

    async def stop(self, suppress_errors: bool = False) -> None:
        """Tear down the session and subprocess. Safe to call multiple times."""
        async with self._lock:
            if not self._started:
                return
            errors: list[Exception] = []

            if self._session_cm is not None:
                try:
                    await self._session_cm.__aexit__(None, None, None)
                except Exception as e:
                    errors.append(e)

            if self._stdio_cm is not None:
                try:
                    await self._stdio_cm.__aexit__(None, None, None)
                except Exception as e:
                    errors.append(e)

            self._session = None
            self._session_cm = None
            self._stdio_cm = None
            self._started = False

            if errors and not suppress_errors:
                logger.warning(
                    "StdioServer.stop encountered %d error(s); last: %s",
                    len(errors), errors[-1],
                )
