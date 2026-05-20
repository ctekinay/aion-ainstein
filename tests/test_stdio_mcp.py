"""Unit tests for StdioServer — mocks the MCP SDK session, no real subprocess.

The fake_plugin fixture (commit 5+ — exercised in commit 8's e2e) is what
spawns a real stub MCP server end-to-end. Here we patch
``aion.mcp.stdio_client.stdio_client`` and ``ClientSession`` so test
speed stays under a second and protocol-drift maintenance is trivial.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from aion.mcp import stdio_client as stdio_module
from aion.mcp.stdio_client import StdioServer, _extract_text


# ---------------------------------------------------------------------- helpers


class _FakeSessionCM:
    """Fake ClientSession async-context-manager."""

    def __init__(self, *, tools=None, call_results=None, init_error=None, call_error=None):
        self.initialize = AsyncMock()
        if init_error is not None:
            self.initialize.side_effect = init_error
        self.list_tools = AsyncMock(return_value=SimpleNamespace(tools=tools or []))
        if call_error is not None:
            self.call_tool = AsyncMock(side_effect=call_error)
        else:
            # Return a CallToolResult-shaped object with .content blocks.
            blocks = [
                SimpleNamespace(text=v, type="text") for v in (call_results or ["ok"])
            ]
            self.call_tool = AsyncMock(return_value=SimpleNamespace(content=blocks))
        self.aexit_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.aexit_calls += 1
        return False


@asynccontextmanager
async def _fake_stdio_client_cm(server_params):
    # Yield a (read, write) tuple — StdioServer only forwards these to ClientSession.
    yield (MagicMock(name="read_stream"), MagicMock(name="write_stream"))


def _install_fakes(monkeypatch, *, session_cm):
    """Patch stdio_client + ClientSession in the stdio_module."""
    monkeypatch.setattr(stdio_module, "stdio_client", _fake_stdio_client_cm)
    monkeypatch.setattr(stdio_module, "ClientSession", lambda r, w: session_cm)


# ---------------------------------------------------------------------- _extract_text


class TestExtractText:
    def test_concatenates_text_blocks(self):
        result = SimpleNamespace(content=[
            SimpleNamespace(text="line one", type="text"),
            SimpleNamespace(text="line two", type="text"),
        ])
        assert _extract_text(result) == "line one\nline two"

    def test_marks_non_text_blocks_with_placeholder(self):
        # text=None signals "not a text block"
        result = SimpleNamespace(content=[
            SimpleNamespace(text="hello", type="text"),
            SimpleNamespace(text=None, type="image"),
        ])
        out = _extract_text(result)
        assert "hello" in out
        assert "[non-text block: image]" in out

    def test_empty_result_returns_empty_string(self):
        result = SimpleNamespace(content=None)
        assert _extract_text(result) == ""


# ---------------------------------------------------------------------- start / stop


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_initializes_session(self, monkeypatch):
        session_cm = _FakeSessionCM()
        _install_fakes(monkeypatch, session_cm=session_cm)

        srv = StdioServer(command="echo", args=["hi"])
        assert not srv.is_alive()
        await srv.start()
        assert srv.is_alive()
        session_cm.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, monkeypatch):
        session_cm = _FakeSessionCM()
        _install_fakes(monkeypatch, session_cm=session_cm)

        srv = StdioServer(command="echo")
        await srv.start()
        await srv.start()  # second call no-ops
        assert session_cm.initialize.await_count == 1

    @pytest.mark.asyncio
    async def test_stop_tears_down_session(self, monkeypatch):
        session_cm = _FakeSessionCM()
        _install_fakes(monkeypatch, session_cm=session_cm)

        srv = StdioServer(command="echo")
        await srv.start()
        assert srv.is_alive()
        await srv.stop()
        assert not srv.is_alive()
        assert session_cm.aexit_calls == 1

    @pytest.mark.asyncio
    async def test_stop_before_start_is_safe(self, monkeypatch):
        session_cm = _FakeSessionCM()
        _install_fakes(monkeypatch, session_cm=session_cm)

        srv = StdioServer(command="echo")
        await srv.stop()  # no error
        assert not srv.is_alive()

    @pytest.mark.asyncio
    async def test_failed_initialize_rolls_back_stdio_context(self, monkeypatch):
        session_cm = _FakeSessionCM(init_error=RuntimeError("init failed"))
        _install_fakes(monkeypatch, session_cm=session_cm)

        srv = StdioServer(command="echo")
        with pytest.raises(RuntimeError, match="init failed"):
            await srv.start()
        # _started must remain False after init failure.
        assert not srv.is_alive()


# ---------------------------------------------------------------------- list_tools / call_tool


class TestListToolsCallTool:
    @pytest.mark.asyncio
    async def test_list_tools_auto_starts(self, monkeypatch):
        fake_tools = [
            SimpleNamespace(name="preview_start", description="start", inputSchema={}),
            SimpleNamespace(name="preview_stop", description="stop", inputSchema={}),
        ]
        session_cm = _FakeSessionCM(tools=fake_tools)
        _install_fakes(monkeypatch, session_cm=session_cm)

        srv = StdioServer(command="echo")
        tools = await srv.list_tools()
        assert len(tools) == 2
        assert tools[0].name == "preview_start"
        assert srv.is_alive()

    @pytest.mark.asyncio
    async def test_call_tool_returns_text(self, monkeypatch):
        session_cm = _FakeSessionCM(call_results=["hello from tool"])
        _install_fakes(monkeypatch, session_cm=session_cm)

        srv = StdioServer(command="echo")
        result = await srv.call_tool("preview_start", {"code": "..."})
        assert result == "hello from tool"
        session_cm.call_tool.assert_awaited_once_with("preview_start", {"code": "..."})

    @pytest.mark.asyncio
    async def test_call_tool_empty_args(self, monkeypatch):
        session_cm = _FakeSessionCM(call_results=["ok"])
        _install_fakes(monkeypatch, session_cm=session_cm)

        srv = StdioServer(command="echo")
        await srv.call_tool("preview_stop")
        session_cm.call_tool.assert_awaited_once_with("preview_stop", {})

    @pytest.mark.asyncio
    async def test_call_tool_failure_marks_dead_and_propagates(self, monkeypatch):
        session_cm = _FakeSessionCM(call_error=ConnectionError("pipe closed"))
        _install_fakes(monkeypatch, session_cm=session_cm)

        srv = StdioServer(command="echo")
        await srv.start()
        assert srv.is_alive()
        with pytest.raises(ConnectionError):
            await srv.call_tool("preview_start", {})
        # Auto-stop on failure → next call would respawn.
        assert not srv.is_alive()
