"""AInstein Persona — intent classification, query rewriting, and routing.

Thin LLM layer between the Chat UI and the Elysia Tree. Classifies user
intent, resolves conversation context (pronouns, follow-ups), and routes
to the appropriate execution path.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from src.aion.config import settings
from src.aion.memory.session_store import get_running_summary, get_user_profile
from src.aion.skills.loader import SkillLoader

logger = logging.getLogger(__name__)

VALID_INTENTS = frozenset({
    "retrieval", "listing", "follow_up", "refinement", "identity", "off_topic", "clarification",
})

# Intents where the Persona produces a direct response (no Tree needed)
DIRECT_RESPONSE_INTENTS = frozenset({"identity", "off_topic", "clarification"})

_FALLBACK_PROMPT = """\
Classify the user's intent as one of: retrieval, listing, follow_up, refinement, identity, off_topic, clarification.
Respond with a single JSON object: {"intent": "<label>", "content": "<rewritten query or direct response>"}
"""


@dataclass
class PersonaResult:
    """Result of the Persona's intent classification and query rewriting."""

    intent: str
    rewritten_query: Optional[str]
    direct_response: Optional[str]
    original_message: str
    latency_ms: int = 0
    skill_tags: list[str] = field(default_factory=list)


class Persona:
    """Thin LLM layer for intent classification, query rewriting, and routing."""

    def __init__(self):
        self._loader = SkillLoader()
        self._cached_prompt: Optional[str] = None

    @property
    def _use_openai_api(self) -> bool:
        """True for any OpenAI-compatible API (GitHub Models or native OpenAI)."""
        return settings.effective_persona_provider in ("github_models", "openai")

    async def process(
        self,
        user_message: str,
        conversation_history: list[dict],
        conversation_id: Optional[str] = None,
    ) -> PersonaResult:
        """Classify intent and rewrite the query using conversation context.

        Args:
            user_message: The raw user message.
            conversation_history: List of message dicts from SQLite (with
                role, content, turn_summary fields).
            conversation_id: Conversation ID for loading running summary
                and user profile from the session store.

        Returns:
            PersonaResult with intent, rewritten query or direct response.
        """
        try:
            system_prompt = self._get_persona_prompt()

            # Inject user profile into system prompt if available
            profile_block = self._get_user_profile_block()
            if profile_block:
                system_prompt = f"{system_prompt}\n\n{profile_block}"

            history_text = self._format_history(
                conversation_history, conversation_id=conversation_id,
            )

            user_prompt_parts = []
            if history_text:
                user_prompt_parts.append(f"CONVERSATION HISTORY:\n{history_text}")
            user_prompt_parts.append(f"CURRENT MESSAGE:\n{user_message}")
            user_prompt = "\n\n".join(user_prompt_parts)

            raw, latency_ms = await self._classify(system_prompt, user_prompt)
            intent, content, skill_tags = self._parse_response(raw)

            logger.info(
                f"Persona: intent={intent}, skill_tags={skill_tags}, "
                f"latency={latency_ms}ms, "
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
                    skill_tags=skill_tags,
                )

            return PersonaResult(
                intent=intent,
                rewritten_query=content or user_message,
                direct_response=None,
                original_message=user_message,
                latency_ms=latency_ms,
                skill_tags=skill_tags,
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

    def _get_user_profile_block(self) -> str:
        """Load the user profile block for system prompt injection."""
        try:
            profile = get_user_profile()
            if not profile:
                return ""
            parts = []
            if profile.get("display_name"):
                parts.append(f"User's name: {profile['display_name']}")
            if profile.get("profile_block"):
                parts.append(profile["profile_block"])
            if parts:
                return "USER PROFILE:\n" + "\n".join(parts)
        except Exception as e:
            logger.warning(f"Failed to load user profile: {e}")
        return ""

    async def _classify(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        """Make a single LLM call for intent classification + query rewriting.

        Returns:
            Tuple of (response text, latency in ms).
        """
        if self._use_openai_api:
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
                    "model": settings.effective_persona_model,
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
        client = OpenAI(**settings.get_openai_client_kwargs(settings.effective_persona_provider))

        model = settings.effective_persona_model
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        # gpt-5.x models (native OpenAI) use max_completion_tokens;
        # GitHub Models catalog IDs are prefixed (openai/gpt-5).
        # GPT-5 models spend reasoning tokens WITHIN max_completion_tokens,
        # so 500 total can leave 0 tokens for visible output. Use 2048
        # to give the model room for both reasoning and the ~100-token
        # JSON response we need.
        model_base = model.rsplit("/", 1)[-1] if "/" in model else model
        if model_base.startswith("gpt-5"):
            kwargs["max_completion_tokens"] = 2048
        else:
            kwargs["max_tokens"] = 500

        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0] if response.choices else None
        text = choice.message.content or "" if choice else ""

        latency = int((time.time() - start) * 1000)
        logger.info(f"Persona classification (OpenAI): {latency}ms")

        return text.strip(), latency

    def _parse_response(self, raw: str) -> tuple[str, str, list[str]]:
        """Parse the Persona's JSON response into (intent, content, skill_tags).

        Expected: {"intent": "...", "content": "...", "skill_tags": [...]}
        Falls back to line-based parsing if JSON fails (model compatibility).
        """
        skill_tags: list[str] = []

        if not raw:
            return "retrieval", "", skill_tags

        text = raw.strip()

        # Primary: JSON parsing
        try:
            # Strip markdown code blocks if model wraps JSON in ```json ... ```
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(text)
            intent = str(data.get("intent", "retrieval")).strip().lower()
            content = str(data.get("content", ""))
            raw_tags = data.get("skill_tags", [])
            if isinstance(raw_tags, list):
                skill_tags = [str(t).strip().lower() for t in raw_tags if t]
        except (json.JSONDecodeError, AttributeError):
            # Fallback: line-based parsing for backward compat
            logger.warning("Persona returned non-JSON, using line-based fallback")
            parts = text.split("\n", 1)
            intent = parts[0].strip().lower().replace(" ", "_")
            content = parts[1].strip() if len(parts) > 1 else ""

        # Strip formatting artifacts (**, *, `) as safety net
        intent = intent.strip("*`_ ")

        if intent not in VALID_INTENTS:
            logger.warning(f"Unrecognized intent '{intent}', defaulting to retrieval")
            intent = "retrieval"

        return intent, content, skill_tags

    # Number of recent messages to include verbatim (full text).
    # Older messages are covered by the running summary.
    VERBATIM_WINDOW = 6

    def _format_history(
        self,
        messages: list[dict],
        conversation_id: Optional[str] = None,
    ) -> str:
        """Format conversation history as running summary + verbatim recent messages.

        Every message in the session is accessible to the model: older turns
        through the rolling summary, recent turns verbatim. No messages are
        silently dropped.
        """
        if not messages:
            return ""

        parts = []

        # 1. Running summary (covers all messages before the verbatim window)
        summary = ""
        if conversation_id:
            try:
                summary = get_running_summary(conversation_id)
            except Exception as e:
                logger.warning(f"Failed to load running summary: {e}")

        if summary:
            parts.append(f"SESSION SUMMARY (earlier context):\n{summary}")

        # 2. Verbatim recent messages
        recent = messages[-self.VERBATIM_WINDOW:]
        if recent:
            lines = []
            for msg in recent:
                role = "User" if msg["role"] == "user" else "Assistant"
                text = msg.get("turn_summary") or msg.get("content", "")
                if len(text) > 300:
                    text = text[:300] + "..."
                lines.append(f"{role}: {text}")
            parts.append("RECENT MESSAGES:\n" + "\n".join(lines))

        return "\n\n".join(parts)
