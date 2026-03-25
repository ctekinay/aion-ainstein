"""Document Analysis Agent -- tool-less agent for uploaded document analysis.

Uses Pydantic AI Agent with zero tools. The LLM reasons over the
document content injected into its system prompt. No RAG search,
no KB tools -- pure document analysis.
"""

from __future__ import annotations

import time

import structlog
from pydantic_ai import Agent
from pydantic_ai.tools import RunContext

from aion.agents import AGENT_LABELS, SessionContext
from aion.config import is_reasoning_model, settings
from aion.skills.loader import get_thresholds_value

logger = structlog.get_logger(__name__)


def _build_document_agent() -> Agent[SessionContext, str]:
    """Build a Pydantic AI agent with zero tools for document analysis."""
    agent = Agent(
        model=settings.build_pydantic_ai_model("rag"),
        deps_type=SessionContext,
        retries=1,
    )

    @agent.system_prompt
    def dynamic_prompt(ctx: RunContext[SessionContext]) -> str:
        return ctx.deps.system_prompt

    return agent


class DocumentAnalysisAgent:
    """Analyze uploaded documents without KB tools.

    The document content is injected into the system prompt. The agent
    has no tools registered, so the LLM responds directly from the
    document context. This avoids the RAG agent's tool-calling behavior
    that causes it to search the KB for the document instead of reading it.
    """

    def __init__(self):
        self._agent = _build_document_agent()

    async def query(
        self,
        question: str,
        document_content: str,
        filename: str,
        conversation_id: str | None = None,
        message_history: list | None = None,
    ) -> tuple[str, dict]:
        """Analyze document content and answer the user's question.

        Returns (response_text, metadata) tuple.
        """
        # System prompt: instructions only. Document content goes in user
        # message, not system prompt. Models process user message content
        # reliably; long system prompts get truncated or deprioritized.
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

        # User message: document + question
        user_message = f"## DOCUMENT: {filename}\n\n{document_content}\n\n## QUESTION:\n{question}"

        ctx = SessionContext(
            conversation_id=conversation_id,
            doc_refs=[],
            skill_tags=[],
            agent_label=AGENT_LABELS.get("document_agent", "Document Analysis"),
            system_prompt=system_prompt,
            _query_start=time.perf_counter(),
            max_tool_calls=0,  # No tools
        )

        # Read token budget from thresholds -- NOT hardcoded
        token_limits = get_thresholds_value("get_llm_token_limits", {})
        model = settings.effective_rag_model
        model_settings = {}
        if is_reasoning_model(model):
            model_settings["max_tokens"] = token_limits.get(
                "document_analysis_reasoning", 8192,
            )
        else:
            model_settings["max_tokens"] = token_limits.get(
                "document_analysis_standard", 4096,
            )

        # Truncate conversation history to configurable max turn pairs
        _upload_cfg = get_thresholds_value("get_upload_config", {})
        _max_pairs = _upload_cfg.get("history_max_turn_pairs", 4)
        _max_msgs = _max_pairs * 2
        if message_history and len(message_history) > _max_msgs:
            message_history = message_history[-_max_msgs:]

        result = await self._agent.run(
            user_message, deps=ctx, model_settings=model_settings,
            message_history=message_history or [],
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
