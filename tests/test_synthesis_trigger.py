"""Tests for stream_synthesis_response() and synthesis condition logic.

Tests cover:
- Default synthesis_instruction fallback (None → generic instruction used in system prompt)
- OpenAI streaming path: stream=True passed, tokens yielded as they arrive
- Ollama path: confirmed to use _iter_ollama_tokens (separate unit)
- synthesis_instruction=None does NOT raise, uses default
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aion.chat_ui import _has_user_content
from aion.generation import stream_synthesis_response


def _async_context_mock(mock_client):
    """Make a MagicMock support ``async with`` by returning itself."""
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# Default instruction fallback
# ---------------------------------------------------------------------------

class TestSynthesisInstructionDefault:
    """stream_synthesis_response() with synthesis_instruction=None uses the default."""

    @pytest.mark.asyncio
    async def test_none_instruction_uses_default_in_system_prompt(self):
        """When synthesis_instruction is None, the default instruction is used."""
        captured_messages = []

        async def mock_stream(*args, **kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            # Return a mock async stream that yields one chunk
            mock_chunk = MagicMock()
            mock_chunk.choices = [MagicMock()]
            mock_chunk.choices[0].delta.content = "response"

            async def _aiter():
                yield mock_chunk

            result = MagicMock()
            result.__aiter__ = lambda s: _aiter()
            return result

        mock_client = _async_context_mock(MagicMock())
        mock_client.chat.completions.create = mock_stream

        with patch("aion.generation.settings") as mock_settings:
            mock_settings.effective_rag_provider = "openai"
            mock_settings.effective_rag_model = "gpt-4o"
            mock_settings.get_openai_client_kwargs.return_value = {}

            with patch("openai.AsyncOpenAI", return_value=mock_client):
                chunks = []
                async for chunk in stream_synthesis_response(
                    original_message="Compare my list with yours",
                    rag_response="KB result here",
                    synthesis_instruction=None,
                ):
                    chunks.append(chunk)

        assert chunks == ["response"]
        # Verify the default instruction appears in the system prompt
        system_msg = next(m for m in captured_messages if m["role"] == "system")
        assert "Combine the user's input with the knowledge base results" in system_msg["content"]
        assert "KB result here" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_explicit_instruction_used_verbatim(self):
        """When synthesis_instruction is provided, it is used as-is."""
        captured_messages = []

        async def mock_stream(*args, **kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            mock_chunk = MagicMock()
            mock_chunk.choices = [MagicMock()]
            mock_chunk.choices[0].delta.content = "result"

            async def _aiter():
                yield mock_chunk

            result = MagicMock()
            result.__aiter__ = lambda s: _aiter()
            return result

        mock_client = _async_context_mock(MagicMock())
        mock_client.chat.completions.create = mock_stream

        with patch("aion.generation.settings") as mock_settings:
            mock_settings.effective_rag_provider = "openai"
            mock_settings.effective_rag_model = "gpt-4o"
            mock_settings.get_openai_client_kwargs.return_value = {}

            with patch("openai.AsyncOpenAI", return_value=mock_client):
                async for _ in stream_synthesis_response(
                    original_message="msg",
                    rag_response="kb",
                    synthesis_instruction="Compare the pasted draft with KB results.",
                ):
                    pass

        system_msg = next(m for m in captured_messages if m["role"] == "system")
        assert "Compare the pasted draft with KB results." in system_msg["content"]
        assert "Combine the user's input" not in system_msg["content"]


# ---------------------------------------------------------------------------
# OpenAI streaming path
# ---------------------------------------------------------------------------

class TestOpenAIStreamingPath:
    """stream_synthesis_response() uses stream=True for OpenAI provider."""

    @pytest.mark.asyncio
    async def test_stream_true_passed_to_openai(self):
        """stream=True is explicitly passed so tokens stream token-by-token."""
        create_kwargs_captured = {}

        async def mock_stream(*args, **kwargs):
            create_kwargs_captured.update(kwargs)
            mock_chunk = MagicMock()
            mock_chunk.choices = [MagicMock()]
            mock_chunk.choices[0].delta.content = "token"

            async def _aiter():
                yield mock_chunk

            result = MagicMock()
            result.__aiter__ = lambda s: _aiter()
            return result

        mock_client = _async_context_mock(MagicMock())
        mock_client.chat.completions.create = mock_stream

        with patch("aion.generation.settings") as mock_settings:
            mock_settings.effective_rag_provider = "github_models"
            mock_settings.effective_rag_model = "gpt-4o"
            mock_settings.get_openai_client_kwargs.return_value = {}

            with patch("openai.AsyncOpenAI", return_value=mock_client):
                async for _ in stream_synthesis_response("msg", "kb"):
                    pass

        assert create_kwargs_captured.get("stream") is True

    @pytest.mark.asyncio
    async def test_multiple_tokens_yielded(self):
        """Multiple tokens from the stream are yielded individually."""
        tokens = ["Hello", " world", "!"]

        async def mock_stream(*args, **kwargs):
            async def _aiter():
                for t in tokens:
                    chunk = MagicMock()
                    chunk.choices = [MagicMock()]
                    chunk.choices[0].delta.content = t
                    yield chunk

            result = MagicMock()
            result.__aiter__ = lambda s: _aiter()
            return result

        mock_client = _async_context_mock(MagicMock())
        mock_client.chat.completions.create = mock_stream

        with patch("aion.generation.settings") as mock_settings:
            mock_settings.effective_rag_provider = "openai"
            mock_settings.effective_rag_model = "gpt-4o"
            mock_settings.get_openai_client_kwargs.return_value = {}

            with patch("openai.AsyncOpenAI", return_value=mock_client):
                yielded = []
                async for chunk in stream_synthesis_response("msg", "kb"):
                    yielded.append(chunk)

        assert yielded == tokens

    @pytest.mark.asyncio
    async def test_empty_delta_content_not_yielded(self):
        """Chunks with None or empty delta.content are skipped."""
        async def mock_stream(*args, **kwargs):
            async def _aiter():
                for content in [None, "", "real token", None]:
                    chunk = MagicMock()
                    chunk.choices = [MagicMock()]
                    chunk.choices[0].delta.content = content
                    yield chunk

            result = MagicMock()
            result.__aiter__ = lambda s: _aiter()
            return result

        mock_client = _async_context_mock(MagicMock())
        mock_client.chat.completions.create = mock_stream

        with patch("aion.generation.settings") as mock_settings:
            mock_settings.effective_rag_provider = "openai"
            mock_settings.effective_rag_model = "gpt-4o"
            mock_settings.get_openai_client_kwargs.return_value = {}

            with patch("openai.AsyncOpenAI", return_value=mock_client):
                yielded = []
                async for chunk in stream_synthesis_response("msg", "kb"):
                    yielded.append(chunk)

        assert yielded == ["real token"]


# ---------------------------------------------------------------------------
# Synthesis condition gates (using _has_user_content as proxy)
# ---------------------------------------------------------------------------

class TestSynthesisConditionGates:
    """Verify the three-condition gate for synthesis:
    complexity == "multi-step" AND has_user_content AND final_response.

    These tests focus on _has_user_content since the other two conditions
    (complexity field and final_response) are straightforward string/bool checks.
    """

    def test_long_paste_triggers_condition(self):
        message = "x" * 600
        rewrite = "x" * 100
        assert _has_user_content(message, rewrite) is True

    def test_short_message_blocks_condition(self):
        """A short query (even with multi-step complexity) must not trigger synthesis."""
        message = "Compare the principles you listed with what an expert would pick"
        rewrite = message  # Persona passes through unchanged
        assert _has_user_content(message, rewrite) is False

    def test_500_char_boundary_does_not_trigger(self):
        """Exactly 500 chars is below the threshold (strict >)."""
        assert _has_user_content("x" * 500, "x" * 10) is False

    def test_501_char_boundary_triggers(self):
        assert _has_user_content("x" * 501, "x" * 10) is True

    def test_message_exactly_twice_rewrite_does_not_trigger(self):
        """Message exactly 2x rewrite length does not trigger (strict >)."""
        assert _has_user_content("x" * 600, "x" * 300) is False

    def test_message_one_char_over_twice_rewrite_triggers(self):
        assert _has_user_content("x" * 601, "x" * 300) is True
