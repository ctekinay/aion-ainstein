"""AInstein Persona — intent classification, query rewriting, and routing.

Thin LLM layer between the Chat UI and the Elysia Tree. Classifies user
intent, resolves conversation context (pronouns, follow-ups), and routes
to the appropriate execution path.
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from .config import settings
from .skills.loader import SkillLoader

logger = logging.getLogger(__name__)

VALID_INTENTS = frozenset({
    "retrieval", "listing", "follow_up", "identity", "off_topic", "clarification",
})

# Intents where the Persona produces a direct response (no Tree needed)
DIRECT_RESPONSE_INTENTS = frozenset({"identity", "off_topic", "clarification"})

_FALLBACK_PROMPT = """\
Classify the user's intent as one of: retrieval, listing, follow_up, identity, off_topic, clarification.
Line 1: the intent label.
Line 2+: the rewritten query (for retrieval/listing/follow_up) or a direct response (for identity/off_topic/clarification).
"""


@dataclass
class PersonaResult:
    """Result of the Persona's intent classification and query rewriting."""

    intent: str
    rewritten_query: Optional[str]
    direct_response: Optional[str]
    original_message: str
    latency_ms: int = 0


class Persona:
    """Thin LLM layer for intent classification, query rewriting, and routing."""

    def __init__(self):
        self._loader = SkillLoader()
        self._cached_prompt: Optional[str] = None

    @property
    def _use_openai(self) -> bool:
        """Read provider at call time so UI model switches take effect."""
        return settings.llm_provider == "openai"

    async def process(
        self, user_message: str, conversation_history: list[dict]
    ) -> PersonaResult:
        """Classify intent and rewrite the query using conversation context.

        Args:
            user_message: The raw user message.
            conversation_history: List of message dicts from SQLite (with
                role, content, turn_summary fields).

        Returns:
            PersonaResult with intent, rewritten query or direct response.
        """
        try:
            system_prompt = self._get_persona_prompt()
            history_text = self._format_history(conversation_history)

            user_prompt_parts = []
            if history_text:
                user_prompt_parts.append(f"CONVERSATION HISTORY:\n{history_text}")
            user_prompt_parts.append(f"CURRENT MESSAGE:\n{user_message}")
            user_prompt = "\n\n".join(user_prompt_parts)

            raw, latency_ms = await self._classify(system_prompt, user_prompt)
            intent, content = self._parse_response(raw)

            logger.info(
                f"Persona: intent={intent}, latency={latency_ms}ms, "
                f"original={user_message!r}, "
                f"rewritten={content!r}"
            )

            if intent in DIRECT_RESPONSE_INTENTS:
                return PersonaResult(
                    intent=intent,
                    rewritten_query=None,
                    direct_response=content or user_message,
                    original_message=user_message,
                    latency_ms=latency_ms,
                )

            return PersonaResult(
                intent=intent,
                rewritten_query=content or user_message,
                direct_response=None,
                original_message=user_message,
                latency_ms=latency_ms,
            )

        except Exception as e:
            logger.warning(f"Persona failed, falling back to passthrough: {e}")
            return PersonaResult(
                intent="retrieval",
                rewritten_query=user_message,
                direct_response=None,
                original_message=user_message,
            )

    def _get_persona_prompt(self) -> str:
        """Load the persona-orchestrator skill content."""
        if self._cached_prompt is not None:
            return self._cached_prompt

        skill = self._loader.load_skill("persona-orchestrator")
        if skill:
            self._cached_prompt = skill.content
            return self._cached_prompt

        logger.warning("persona-orchestrator skill not found, using fallback prompt")
        self._cached_prompt = _FALLBACK_PROMPT
        return self._cached_prompt

    async def _classify(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        """Make a single LLM call for intent classification + query rewriting.

        Returns:
            Tuple of (response text, latency in ms).
        """
        if self._use_openai:
            return await self._classify_openai(system_prompt, user_prompt)
        return await self._classify_ollama(system_prompt, user_prompt)

    async def _classify_ollama(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        """Classify via Ollama API.

        Returns:
            Tuple of (response text, latency in ms).
        """
        import httpx

        start = time.time()
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {"num_predict": 500},
                },
            )
            response.raise_for_status()
            result = response.json()
            text = result.get("response", "")

            # Strip <think> tags (chain-of-thought models)
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
            text = re.sub(r"</?think>", "", text)

            latency = int((time.time() - start) * 1000)
            logger.info(f"Persona classification (Ollama): {latency}ms")

            return text.strip(), latency

    async def _classify_openai(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        """Classify via OpenAI API.

        Returns:
            Tuple of (response text, latency in ms).
        """
        from openai import OpenAI

        start = time.time()
        client = OpenAI(api_key=settings.openai_api_key)

        model = settings.openai_chat_model
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if model.startswith("gpt-5"):
            kwargs["max_completion_tokens"] = 500
        else:
            kwargs["max_tokens"] = 500

        response = client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or ""

        latency = int((time.time() - start) * 1000)
        logger.info(f"Persona classification (OpenAI): {latency}ms")

        return text.strip(), latency

    def _parse_response(self, raw: str) -> tuple[str, str]:
        """Parse the LLM's two-line response into (intent, content).

        Line 1 = intent label. Lines 2+ = rewritten query or direct response.
        Uses maxsplit=1 to preserve multi-line direct responses.
        """
        if not raw:
            return "retrieval", ""

        parts = raw.strip().split("\n", 1)
        intent = parts[0].strip().lower().replace(" ", "_")

        # Validate intent
        if intent not in VALID_INTENTS:
            logger.warning(f"Unrecognized intent '{intent}', defaulting to retrieval")
            intent = "retrieval"

        content = parts[1].strip() if len(parts) > 1 else ""
        return intent, content

    def _format_history(
        self, messages: list[dict], max_messages: int = 6
    ) -> str:
        """Format conversation history for the Persona's context.

        Uses turn_summary when available (compact semantic summary),
        falls back to truncated content.
        """
        if not messages:
            return ""

        recent = messages[-max_messages:]
        lines = []

        for msg in recent:
            role = "User" if msg["role"] == "user" else "Assistant"
            # Prefer turn_summary for assistant messages
            text = msg.get("turn_summary") or msg.get("content", "")
            if len(text) > 200:
                text = text[:200] + "..."
            lines.append(f"{role}: {text}")

        return "\n".join(lines)
