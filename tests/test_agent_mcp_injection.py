"""Tests for plugin-supplied MCP tool injection into Pydantic AI agents.

attach_mcp_tools is called inside each ``_build_*_agent`` after the
static ``@agent.tool`` decorators. A failing tool registration is
logged and skipped so one bad MCP tool can't break the agent.
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import MagicMock

import pytest

from aion.agents._mcp_inject import attach_mcp_tools


def _make_signature(params: list[tuple[str, type]]) -> inspect.Signature:
    """Helper to build a synthetic signature for a fake MCP tool."""
    sig_params = [
        inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Any)
    ] + [
        inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, annotation=annot)
        for name, annot in params
    ]
    return inspect.Signature(parameters=sig_params, return_annotation=str)


class TestAttachMcpTools:
    def test_none_is_noop(self):
        agent = MagicMock()
        attach_mcp_tools(agent, None)
        agent.tool.assert_not_called()

    def test_empty_list_is_noop(self):
        agent = MagicMock()
        attach_mcp_tools(agent, [])
        agent.tool.assert_not_called()

    def test_each_tool_registered_once(self):
        agent = MagicMock()

        async def tool_a():
            return ""

        async def tool_b():
            return ""

        attach_mcp_tools(agent, [tool_a, tool_b])
        assert agent.tool.call_count == 2
        registered = [call_args[0][0] for call_args in agent.tool.call_args_list]
        assert tool_a in registered
        assert tool_b in registered

    def test_failing_tool_skipped_others_still_register(self, caplog):
        agent = MagicMock()

        async def good_tool():
            return ""

        async def bad_tool():
            return ""

        # The agent.tool call for bad_tool raises; good_tool should still register.
        def side_effect(fn):
            if fn is bad_tool:
                raise RuntimeError("registration failed")

        agent.tool.side_effect = side_effect

        # Order matters: put bad first to verify good still registers after.
        attach_mcp_tools(agent, [bad_tool, good_tool])

        assert agent.tool.call_count == 2  # both attempted
        assert any("Failed to attach MCP tool" in r.message for r in caplog.records)

    def test_preserves_registration_order(self):
        agent = MagicMock()
        tools = []
        for i in range(5):
            async def t():
                return ""
            t.__name__ = f"tool_{i}"
            tools.append(t)

        attach_mcp_tools(agent, tools)
        registered_names = [
            call_args[0][0].__name__ for call_args in agent.tool.call_args_list
        ]
        assert registered_names == [f"tool_{i}" for i in range(5)]


# ---------------------------------------------------------------------- integration


class TestRealPydanticAIAgentAcceptsBridgedTools:
    """Integration test: synthesize a bridged tool, register on a real
    pydantic_ai.Agent, verify Pydantic AI doesn't silently reject it.

    The failure mode this test catches: ``build_mcp_tool_callable`` sets
    ``ctx: Any`` as the first parameter (for parity with AInstein's existing
    @agent.tool pattern). If Pydantic AI's tool-spec introspector rejects
    ``Any`` instead of treating it as a context-shaped parameter,
    ``agent.tool()`` raises — which ``attach_mcp_tools`` catches and logs,
    leading to silently inert MCP tools at runtime. The unit tests use
    MagicMock for the agent and miss this.
    """

    def test_synthesized_tool_registers_on_real_agent_without_warning(self, caplog):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from pydantic_ai import Agent
        from aion.mcp.tool_bridge import build_mcp_tool_callable

        # Minimal Agent — test model so no real provider call is made.
        agent: Agent = Agent("test")

        # Static @agent.tool first, mirroring the production agent build order.
        @agent.tool_plain
        def static_tool(x: str) -> str:
            return x

        async def fake_lookup(plugin, server):
            return SimpleNamespace(call_tool=AsyncMock(return_value="ok"))

        bridged = build_mcp_tool_callable(
            plugin_name="demo",
            server_name="preview",
            tool_name="preview_start",
            description="Open the preview",
            input_schema={
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
            server_lookup=fake_lookup,
        )

        import logging
        caplog.set_level(logging.WARNING, logger="aion.agents._mcp_inject")

        attach_mcp_tools(agent, [bridged])

        # If Pydantic AI rejected the synthesized signature, attach_mcp_tools
        # logs "Failed to attach MCP tool ... — skipping". Absence of that
        # warning is the success condition.
        assert not any(
            "Failed to attach MCP tool" in r.message for r in caplog.records
        ), "Pydantic AI rejected the bridged tool's synthesized signature"


_CHAT_UI_AGENT_GLOBALS = (
    "_rag_agent", "_vocabulary_agent", "_archimate_agent",
    "_principle_agent", "_repo_analysis_agent", "_document_agent",
    "_generation_pipeline",
)


@pytest.fixture
def restore_chat_ui_agent_globals():
    """Snapshot/restore the chat_ui agent module-globals.

    ``_rebuild_agents()`` does ``global _rag_agent; _rag_agent = ...`` —
    calling it under ``patch`` leaves the *globals* pointing at MagicMocks
    after the patch context exits (patch restores ``cui.RAGAgent``, not the
    ``_rag_agent`` the function reassigned). Without this, the mocks leak
    into every later test that touches chat_ui agents.
    """
    import aion.chat_ui as cui

    saved = {n: getattr(cui, n, None) for n in _CHAT_UI_AGENT_GLOBALS}
    try:
        yield
    finally:
        for n, v in saved.items():
            setattr(cui, n, v)


class TestRebuildAgentsPropagatesMcpTools:
    """Item 6 regression: a model switch must not strip plugin MCP tools.

    The bug: ``_rebuild_agents()`` (sole caller: the ``set_llm_settings``
    model-switch endpoint) reconstructed every agent *without* mcp_tools,
    so switching the LLM model silently dropped plugin MCP tools that were
    wired only at lifespan startup. Fix: both construction sites route
    through the shared ``_discover_agent_mcp_tools()`` helper so they
    cannot drift; ``_rebuild_agents`` takes the resolved bundles and
    passes each routed bundle into its agent's constructor.
    """

    def test_rebuild_passes_each_routed_bundle_to_its_agent(
        self, restore_chat_ui_agent_globals,
    ):
        import aion.chat_ui as cui
        from unittest.mock import patch

        bundles = {
            "tree": ["rag_tool"],
            "vocabulary": ["vocab_tool"],
            "archimate": ["arch_tool"],
            "principle": ["princ_tool"],
            "repo_analysis": ["repo_tool"],
            "document_analysis": ["doc_tool"],
        }
        with patch.object(cui, "RAGAgent") as RA, \
             patch.object(cui, "VocabularyAgent") as VA, \
             patch.object(cui, "ArchiMateAgent") as AA, \
             patch.object(cui, "PrincipleAgent") as PA, \
             patch.object(cui, "GenerationPipeline"), \
             patch("aion.agents.repo_analysis_agent.RepoAnalysisAgent") as RPA, \
             patch("aion.agents.document_agent.DocumentAnalysisAgent") as DA:
            cui._rebuild_agents(mcp_tools_by_agent=bundles)

        assert RA.call_args.kwargs["mcp_tools"] == ["rag_tool"]
        assert VA.call_args.kwargs["mcp_tools"] == ["vocab_tool"]
        assert AA.call_args.kwargs["mcp_tools"] == ["arch_tool"]
        assert PA.call_args.kwargs["mcp_tools"] == ["princ_tool"]
        assert RPA.call_args.kwargs["mcp_tools"] == ["repo_tool"]
        assert DA.call_args.kwargs["mcp_tools"] == ["doc_tool"]

    def test_rebuild_without_bundles_is_explicit_empty_not_silent(
        self, restore_chat_ui_agent_globals,
    ):
        """None → every agent gets ``[]`` (explicit degraded fallback),
        never a crash and never an undefined/implicit tool set."""
        import aion.chat_ui as cui
        from unittest.mock import patch

        with patch.object(cui, "RAGAgent") as RA, \
             patch.object(cui, "VocabularyAgent"), \
             patch.object(cui, "ArchiMateAgent"), \
             patch.object(cui, "PrincipleAgent"), \
             patch.object(cui, "GenerationPipeline"), \
             patch("aion.agents.repo_analysis_agent.RepoAnalysisAgent"), \
             patch("aion.agents.document_agent.DocumentAnalysisAgent"):
            cui._rebuild_agents()  # defensive no-arg path

        assert RA.call_args.kwargs["mcp_tools"] == []

    def test_discover_returns_a_bundle_for_every_agent_type(self):
        """The shared helper keys *every* routed agent type, so both
        construction sites consume the same complete mapping (the
        convergence that prevents the drift Item 6 was caused by).

        Runs the coroutine on a private loop and does NOT use
        ``asyncio.run()`` — that calls ``set_event_loop(None)`` on exit,
        which breaks the legacy ``asyncio.get_event_loop()`` tests that
        run after this one (cross-file ordering pollution).
        """
        import asyncio
        from unittest.mock import MagicMock, patch

        import aion.chat_ui as cui

        loop = asyncio.new_event_loop()  # not registered with the policy
        try:
            with patch("aion.skills.registry.get_skill_registry", return_value=MagicMock()), \
                 patch("aion.mcp.tool_bridge.mcp_servers_for_agent", return_value=[]):
                result = loop.run_until_complete(cui._discover_agent_mcp_tools())
        finally:
            loop.close()

        assert set(result.keys()) == set(cui._AGENT_MCP_TYPES)
        assert all(v == [] for v in result.values())
