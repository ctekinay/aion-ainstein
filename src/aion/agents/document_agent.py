"""Document Analysis Agent -- tool-less agent for uploaded document analysis.

Uses Pydantic AI Agent with zero tools. The LLM reasons over the
document content prepended to the user message. No RAG search,
no KB tools -- pure document analysis.

Supports token-level streaming via stream_query() for progressive
output to the frontend.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator

import structlog
from pydantic_ai import Agent
from pydantic_ai.tools import RunContext

from aion.agents import AGENT_LABELS, SessionContext
from aion.config import is_reasoning_model, settings
from aion.config.runtime import get_runtime_value

logger = structlog.get_logger(__name__)


def _build_document_agent(mcp_tools=None) -> Agent[SessionContext, str]:
    """Build a Pydantic AI agent with zero static tools for document analysis.

    Uses provider-aware timeout and retry config from runtime.yaml.
    Ollama gets longer timeout (300s) with zero retries — retrying a
    timeout on a local model is pointless. Cloud gets shorter timeout
    (60s) with one retry for transient failures.

    Plugin-supplied MCP tools routed to this agent (per the per-skill
    mcp_servers routing rule, D10) are attached after construction via
    aion.agents._mcp_inject.attach_mcp_tools. Tools default to none.
    """
    _cfg = get_runtime_value("document_agent", {})
    is_ollama = settings.effective_rag_provider == "ollama"
    _timeout = _cfg.get("timeout_ollama", 300) if is_ollama else _cfg.get("timeout_cloud", 60)
    _retries = _cfg.get("max_retries_ollama", 0) if is_ollama else _cfg.get("max_retries_cloud", 1)

    agent = Agent(
        model=settings.build_pydantic_ai_model("rag", timeout=_timeout, max_retries=_retries),
        deps_type=SessionContext,
        retries=0,  # No Pydantic AI retries — zero static tools, nothing to retry
    )

    @agent.system_prompt
    def dynamic_prompt(ctx: RunContext[SessionContext]) -> str:
        return ctx.deps.system_prompt

    from aion.agents._mcp_inject import attach_mcp_tools
    attach_mcp_tools(agent, mcp_tools)

    return agent


class DocumentAnalysisAgent:
    """Analyze uploaded documents with optional plugin-supplied MCP tools.

    The document content is prepended to the user message. Without
    mcp_tools, the agent has no static tools registered, so the LLM
    responds directly from the document context (avoids RAG-style
    tool-calling against the KB). Plugins routing skills to this agent
    (execution: document_analysis) inject MCP tools at construction.
    """

    def __init__(self, mcp_tools=None):
        self._agent = _build_document_agent(mcp_tools=mcp_tools)

    def _prepare_query(
        self,
        question: str,
        document_content: str,
        filename: str,
        conversation_id: str | None = None,
        message_history: list | None = None,
    ) -> tuple[str, SessionContext, dict, list]:
        """Build the user message, context, model settings, and history.

        Shared setup for both query() and stream_query().
        """
        system_prompt = (
            "You are AInstein, the Energy System Architecture AI Assistant "
            "at Alliander.\n\n"
            "The user will provide a document and a question. Answer ONLY "
            "from the document content provided. Do NOT fabricate quotes, "
            "page numbers, or section references that do not appear in the "
            "document. If you cannot find the answer in the document, say so.\n\n"
            "NEVER claim you have access to a document unless its content "
            "appears in your current context. If a user references a document "
            "you cannot see, tell them to re-upload it."
        )

        user_message = f"## DOCUMENT: {filename}\n\n{document_content}\n\n## QUESTION:\n{question}"

        ctx = SessionContext(
            conversation_id=conversation_id,
            doc_refs=[],
            skill_tags=[],
            agent_label=AGENT_LABELS.get("document_agent", "Document Analysis"),
            system_prompt=system_prompt,
            _query_start=time.perf_counter(),
            max_tool_calls=0,
        )

        token_limits = get_runtime_value("llm_token_limits", {})
        model = self._agent.model.model_name
        logger.info("document_agent_model", model=model)
        model_settings = {}
        if is_reasoning_model(model):
            model_settings["max_tokens"] = token_limits.get(
                "document_analysis_reasoning", 8192,
            )
        else:
            model_settings["max_tokens"] = token_limits.get(
                "document_analysis_standard", 4096,
            )

        _upload_cfg = get_runtime_value("upload", {})
        _max_pairs = _upload_cfg.get("history_max_turn_pairs", 4)
        _max_msgs = _max_pairs * 2
        if message_history and len(message_history) > _max_msgs:
            message_history = message_history[-_max_msgs:]

        return user_message, ctx, model_settings, message_history or []

    async def query(
        self,
        question: str,
        document_content: str,
        filename: str,
        conversation_id: str | None = None,
        message_history: list | None = None,
    ) -> tuple[str, dict]:
        """Analyze document content and answer the user's question.

        Blocking (non-streaming) variant. Returns (response_text, metadata).
        """
        user_message, ctx, model_settings, history = self._prepare_query(
            question, document_content, filename, conversation_id, message_history,
        )

        result = await self._agent.run(
            user_message, deps=ctx, model_settings=model_settings,
            message_history=history,
        )

        elapsed = int((time.perf_counter() - ctx._query_start) * 1000)
        logger.info(
            "document_agent_complete",
            conversation_id=conversation_id,
            filename=filename,
            doc_chars=len(document_content),
            response_chars=len(result.output),
            latency_ms=elapsed,
        )

        return result.output, {"execution_model": "document_analysis"}

    async def stream_query(
        self,
        question: str,
        document_content: str,
        filename: str,
        conversation_id: str | None = None,
        message_history: list | None = None,
        batch_chars: int = 200,
    ) -> AsyncGenerator[str, None]:
        """Stream document analysis tokens as they arrive.

        Yields text chunks (batched to ~batch_chars). Final chunk may
        be smaller. Caller is responsible for wrapping in SSE events.
        """
        user_message, ctx, model_settings, history = self._prepare_query(
            question, document_content, filename, conversation_id, message_history,
        )

        buf = ""
        chars_yielded = 0

        async with self._agent.run_stream(
            user_message, deps=ctx, model_settings=model_settings,
            message_history=history,
        ) as stream:
            async for delta in stream.stream_text(delta=True, debounce_by=None):
                buf += delta
                if len(buf) >= batch_chars:
                    chars_yielded += len(buf)
                    yield buf
                    buf = ""

        # Flush remaining buffer
        if buf:
            chars_yielded += len(buf)
            yield buf

        elapsed = int((time.perf_counter() - ctx._query_start) * 1000)
        # Caller accumulates full text; we only log the char count.
        logger.info(
            "document_agent_stream_complete",
            conversation_id=conversation_id,
            filename=filename,
            doc_chars=len(document_content),
            response_chars=chars_yielded,
            latency_ms=elapsed,
        )
