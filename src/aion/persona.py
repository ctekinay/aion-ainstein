"""AInstein Persona — intent classification, query rewriting, and routing.

Thin LLM layer between the Chat UI and the RAG agent. Classifies user
intent, resolves conversation context (pronouns, follow-ups), and routes
to the appropriate execution path.
"""

import json
import time
from dataclasses import dataclass, field
from typing import TypedDict

import structlog

from aion.config import is_reasoning_model, settings
from aion.memory.session_store import get_running_summary, get_user_profile
from aion.skills.loader import SkillLoader
from aion.text_utils import elapsed_ms, strip_think_tags

logger = structlog.get_logger(__name__)


class PermanentLLMError(Exception):
    """LLM configuration errors that will never resolve by retrying.

    Examples: model not found (404), invalid API key (401).
    Raised from classify methods so that fallback handlers do not
    swallow these — they must be surfaced to the user.
    """

    pass


VALID_INTENTS = frozenset({
    "retrieval", "listing", "follow_up", "refinement", "generation",
    "inspect", "identity", "off_topic", "clarification", "conversational",
})

# Intents where the Persona produces a direct response (no Tree needed)
DIRECT_RESPONSE_INTENTS = frozenset({"identity", "off_topic", "clarification", "conversational"})

_FALLBACK_PROMPT = """\
Classify the user's intent as one of: retrieval, listing, follow_up, refinement, identity, off_topic, clarification, conversational.
Respond with a single JSON object: {"intent": "<label>", "content": "<rewritten query or direct response>"}
"""


@dataclass
class PlanStep:
    """A single retrieval step in a multi-step Persona plan."""
    query: str
    skill_tags: list[str] = field(default_factory=list)
    doc_refs: list[str] = field(default_factory=list)


class _ParsedResponse(TypedDict):
    """Intermediate parsed fields from _parse_response(). Excludes fields added by process()."""
    intent: str
    content: str
    direct: bool  # LLM signals "I can answer from context, don't route to agent"
    skill_tags: list[str]
    doc_refs: list[str]
    github_refs: list[str]
    complexity: str
    synthesis_instruction: str | None
    steps: list  # list[PlanStep]


@dataclass
class PersonaResult:
    """Result of the Persona's intent classification and query rewriting."""

    intent: str
    rewritten_query: str | None
    direct_response: str | None
    original_message: str
    latency_ms: int = 0
    skill_tags: list[str] = field(default_factory=list)
    doc_refs: list[str] = field(default_factory=list)
    github_refs: list[str] = field(default_factory=list)  # "owner/repo" strings
    complexity: str = "simple"           # "simple" | "multi-step"
    synthesis_instruction: str | None = None
    steps: list = field(default_factory=list)  # list[PlanStep]; non-empty → Phase 2 orchestration


class Persona:
    """Thin LLM layer for intent classification, query rewriting, and routing."""

    def __init__(self):
        self._loader = SkillLoader()
        self._cached_prompt: str | None = None

    @property
    def _use_openai_api(self) -> bool:
        """True for any OpenAI-compatible API (GitHub Models or native OpenAI)."""
        return settings.effective_persona_provider in ("github_models", "openai")

    async def process(
        self,
        user_message: str,
        conversation_history: list[dict],
        conversation_id: str | None = None,
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
            parsed = self._parse_response(raw)

            logger.info(
                "persona_classified",
                intent=parsed["intent"],
                complexity=parsed["complexity"],
                steps_count=len(parsed["steps"]),
                synthesis_instruction_set=parsed["synthesis_instruction"] is not None,
                skill_tags=parsed["skill_tags"],
                doc_refs=parsed["doc_refs"],
                latency_ms=latency_ms,
                rewritten_query=parsed["content"][:200],
            )

            is_direct = parsed.get("direct", False) or parsed["intent"] in DIRECT_RESPONSE_INTENTS
            if is_direct:
                return PersonaResult(
                    intent=parsed["intent"],
                    rewritten_query=None,
                    direct_response=parsed["content"] or user_message,
                    original_message=user_message,
                    latency_ms=latency_ms,
                    skill_tags=parsed["skill_tags"],
                    doc_refs=parsed["doc_refs"],
                    github_refs=parsed["github_refs"],
                    complexity=parsed["complexity"],
                    synthesis_instruction=parsed["synthesis_instruction"],
                    steps=parsed["steps"],
                )

            return PersonaResult(
                intent=parsed["intent"],
                rewritten_query=parsed["content"] or user_message,
                direct_response=None,
                original_message=user_message,
                latency_ms=latency_ms,
                skill_tags=parsed["skill_tags"],
                doc_refs=parsed["doc_refs"],
                github_refs=parsed["github_refs"],
                complexity=parsed["complexity"],
                synthesis_instruction=parsed["synthesis_instruction"],
                steps=parsed["steps"],
            )

        except PermanentLLMError:
            raise  # Never swallow configuration errors — surface to user
        except Exception as e:
            logger.warning("persona_fallback", error=str(e), original_message=user_message[:100])
            return PersonaResult(
                intent="retrieval",
                rewritten_query=user_message,
                direct_response=None,
                original_message=user_message,
            )

    def _get_persona_prompt(self) -> str:
        """Load persona-orchestrator + ainstein-identity skill content.

        The orchestrator provides classification rules. The identity skill
        provides tone, personality, and conversation style — needed for
        direct responses (identity, off_topic) that bypass the Tree.
        """
        if self._cached_prompt is not None:
            return self._cached_prompt

        skill = self._loader.load_skill("persona-orchestrator")
        if skill:
            prompt = skill.content
        else:
            logger.warning("persona-orchestrator skill not found, using fallback prompt")
            prompt = _FALLBACK_PROMPT

        identity = self._loader.load_skill("ainstein-identity")
        if identity:
            prompt = f"{prompt}\n\n{identity.content}"

        self._cached_prompt = prompt
        logger.info(f"Persona prompt loaded: {len(self._cached_prompt)} chars")
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

        start = time.perf_counter()
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            async with httpx.AsyncClient(timeout=settings.timeout_llm_inspect) as client:
                response = await client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model": settings.effective_persona_model,
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {"num_predict": 500},
                    },
                )
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        model = settings.effective_persona_model
                        raise PermanentLLMError(
                            f"Model '{model}' not found in Ollama. "
                            f"Run 'ollama pull {model}' or check your model settings."
                        ) from e
                    raise  # re-raise transient HTTP errors (429, 500, etc.)
                result = response.json()
                text = result.get("response", "")

            # Strip <think> tags (chain-of-thought models)
            text = strip_think_tags(text)

            latency = elapsed_ms(start)
            logger.info(f"Persona classification (Ollama): {latency}ms")

            return text.strip(), latency
        except httpx.TimeoutException:
            latency = elapsed_ms(start)
            logger.warning("Ollama persona classification timed out after %dms", latency)
            raise

    async def _classify_openai(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        """Classify via OpenAI API.

        Returns:
            Tuple of (response text, latency in ms).
        """
        from openai import AsyncOpenAI, AuthenticationError, NotFoundError

        start = time.perf_counter()
        model = settings.effective_persona_model
        provider = settings.effective_persona_provider

        async with AsyncOpenAI(**settings.get_openai_client_kwargs(provider)) as client:
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
            if is_reasoning_model(model):
                kwargs["max_completion_tokens"] = 2048
            else:
                kwargs["max_tokens"] = 500

            try:
                response = await client.chat.completions.create(**kwargs)
            except NotFoundError:
                raise PermanentLLMError(
                    f"Model '{model}' not found on {provider}. Check your model settings."
                )
            except AuthenticationError:
                raise PermanentLLMError(
                    f"Authentication failed for {provider}. Check your API key."
                )

        choice = response.choices[0] if response.choices else None
        text = choice.message.content or "" if choice else ""

        latency = elapsed_ms(start)
        logger.info(f"Persona classification (OpenAI): {latency}ms")

        return text.strip(), latency

    def _parse_response(self, raw: str) -> _ParsedResponse:
        """Parse the Persona's JSON response into a _ParsedResponse dict.

        Expected: {"intent": "...", "content": "...", "skill_tags": [...], "doc_refs": [...],
                   "github_refs": [...], "complexity": "simple|multi-step", "synthesis_instruction": null}
        Falls back to line-based parsing if JSON fails (model compatibility).
        """
        skill_tags: list[str] = []
        doc_refs: list[str] = []
        github_refs: list[str] = []
        steps: list[PlanStep] = []
        complexity: str = "simple"
        synthesis_instruction: str | None = None
        intent = "retrieval"
        content = ""

        direct: bool = False

        if not raw:
            return _ParsedResponse(
                intent=intent, content=content, direct=direct,
                skill_tags=skill_tags, doc_refs=doc_refs, github_refs=github_refs,
                complexity=complexity, synthesis_instruction=synthesis_instruction,
                steps=steps,
            )

        text = raw.strip()

        # Primary: JSON parsing
        try:
            # Strip markdown code blocks if model wraps JSON in ```json ... ```
            if text.startswith("```"):
                parts = text.split("\n", 1)
                if len(parts) > 1:
                    text = parts[1].rsplit("```", 1)[0].strip()
            data = json.loads(text)
            intent = str(data.get("intent", "retrieval")).strip().lower()
            content = str(data.get("content", ""))
            raw_tags = data.get("skill_tags", [])
            if isinstance(raw_tags, list):
                skill_tags = [str(t).strip().lower() for t in raw_tags if t]
            raw_refs = data.get("doc_refs", [])
            if isinstance(raw_refs, list):
                doc_refs = [str(r).strip() for r in raw_refs if r]
            raw_github = data.get("github_refs", [])
            if isinstance(raw_github, list):
                github_refs = [str(r).strip() for r in raw_github if r]
            raw_complexity = str(data.get("complexity", "simple")).strip()
            complexity = raw_complexity if raw_complexity in ("simple", "multi-step") else "simple"
            synthesis_instruction = data.get("synthesis_instruction") or None
            direct = bool(data.get("direct", False))
            raw_steps = data.get("steps", [])
            if isinstance(raw_steps, list):
                for s in raw_steps[:3]:  # cap at 3 — prevent runaway orchestration
                    if not isinstance(s, dict):
                        continue
                    query = s.get("query", "")
                    if not isinstance(query, str) or not query.strip():
                        continue
                    steps.append(PlanStep(
                        query=query.strip(),
                        skill_tags=[t for t in s.get("skill_tags", []) if isinstance(t, str)],
                        doc_refs=[r for r in s.get("doc_refs", []) if isinstance(r, str)],
                    ))
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

        return _ParsedResponse(
            intent=intent, content=content, direct=direct,
            skill_tags=skill_tags, doc_refs=doc_refs, github_refs=github_refs,
            complexity=complexity, synthesis_instruction=synthesis_instruction,
            steps=steps,
        )

    def _get_persona_config(self) -> dict:
        """Load persona thresholds from persona-orchestrator skill."""
        thresholds = self._loader.get_thresholds("persona-orchestrator")
        return thresholds.get("persona", {})

    def _format_history(
        self,
        messages: list[dict],
        conversation_id: str | None = None,
    ) -> str:
        """Format conversation history as running summary + verbatim recent messages.

        Every message in the session is accessible to the model: older turns
        through the rolling summary, recent turns verbatim. No messages are
        silently dropped.
        """
        if not messages:
            return ""

        config = self._get_persona_config()
        verbatim_window = config.get("verbatim_window", 20)
        truncation = config.get("message_truncation_chars", 8000)

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

        # 2. Verbatim recent messages.
        # For assistant messages, prefer turn_summary (compact, covers full
        # response range) over full content (which is truncated at
        # message_truncation_chars and can cut off mid-list — e.g., a
        # 41-principle listing truncated at PCP.34 causes the Persona to
        # scope follow-up rewrites to "PCP.10 through PCP.34"). User messages
        # are always shown verbatim since they are typically short.
        recent = messages[-verbatim_window:]
        if recent:
            lines = []
            for msg in recent:
                role = "User" if msg["role"] == "user" else "Assistant"
                if msg["role"] == "assistant" and msg.get("turn_summary"):
                    text = msg["turn_summary"]
                else:
                    text = msg.get("content", "")
                    if len(text) > truncation:
                        text = text[:truncation] + "..."
                lines.append(f"{role}: {text}")
            parts.append("RECENT MESSAGES:\n" + "\n".join(lines))

        return "\n\n".join(parts)
