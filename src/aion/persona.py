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
from aion.skills.loader import get_thresholds_value
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

# Intents that MUST route to an agent — never trust the LLM's "direct"
# flag for these. The classification LLM doesn't have access to documents
# or KB tools, so it can't actually answer these queries.
_AGENT_REQUIRED_INTENTS = frozenset({
    "retrieval", "listing", "follow_up", "generation", "inspect", "refinement",
})

_FALLBACK_PROMPT = """\
Classify the user's intent as one of: retrieval, listing, follow_up, refinement, identity, off_topic, clarification, conversational.
Respond with a single JSON object: {"intent": "<label>", "content": "<rewritten query or direct response>"}
"""

# Minimal classification prompt (<5K chars). Used instead of the full
# persona-orchestrator SKILL.md (47K) + ainstein-identity (15K) to keep
# classification fast on all models. Identity is lazy-loaded only for
# direct response intents.
_CLASSIFICATION_PROMPT = """\
You are the intent classifier for AInstein, an Energy System Architecture AI Assistant. \
Classify the user's message and rewrite the query for the retrieval system.

## Intents

| Intent | When to use | Examples |
|--------|-------------|---------|
| retrieval | Wants specific information from the knowledge base | "What does ADR.21 decide?", "Tell me about data governance" |
| listing | Wants an enumeration or count of documents | "List all ADRs", "How many principles exist?" |
| follow_up | References prior conversation with pronouns or implicit refs | "Tell me more about that", "What about its consequences?" |
| generation | Wants to create a structured artifact (ArchiMate model, XML) | "Create an ArchiMate model for ADR.29", "Analyze this repo and build a model: https://github.com/org/repo" |
| inspect | Wants to review/analyze an existing ArchiMate model. NOT for "architectural principles" or repo analysis | "Describe the model you generated", "What elements are in this model?" |
| refinement | Wants changes to something AInstein previously generated | "Add a Technology layer to the model", "Make the names shorter" |
| identity | Asks who AInstein is, greets, or shares context about themselves | "Who are you?", "Hello", "I'm working on ADR.29" |
| conversational | General architecture/engineering question answerable without KB | "What are trade-offs of event-driven architecture?" |
| off_topic | Completely outside architecture/engineering scope | "What's the weather?", "Write me a poem" |
| clarification | Too vague to process (not greetings, not general questions) | "Tell me about that thing" (without context) |

## Skill Tags

| Tag | When to use | NOT this tag |
|-----|-------------|--------------|
| `"archimate"` | ArchiMate models, elements, relationships, XML generation | "architectural principles", compliance, governance |
| `"vocabulary"` | Term definitions, abbreviations, IEC standards, SKOSMOS lookups | |
| `"principle-quality"` | Evaluate document against principles (compliance), assess principle quality | |
| `"generate-principle"` | Draft or generate a new principle | |
| `"repo-analysis"` | GitHub URL + analyze/model/build (intent: generation) | Bare URL without build intent → use inspect |

Default: `[]` for normal KB queries, follow-ups, language/format changes.

## Classification Examples

| User message | intent | skill_tags | content (rewrite) |
|-------------|--------|------------|-------------------|
| "Evaluate this document against our principles" | retrieval | ["principle-quality"] | "Evaluate the attached document against all architecture principles (PCP.10-50)" |
| "What does ADR.21 decide?" | retrieval | [] | "What does ADR.21 decide?" |
| "Create an ArchiMate model for ADR.29" | generation | ["archimate"] | "Create an ArchiMate model for ADR.29" |
| "Analyze github.com/org/repo and build a model" | generation | ["repo-analysis"] | "Analyze the repository and generate an ArchiMate model" |
| "What are the architectural principles?" | retrieval | ["principle-quality"] | "List all architecture principles" |
| "Describe the model you generated" | inspect | ["archimate"] | "Describe the ArchiMate model from the previous response" |
| "In English, please" | follow_up | [] | "Translate the previous response to English" |
| "As a table" | follow_up | [] | "Reformat the previous response as a table" |
| "In het Nederlands" | follow_up | [] | "Translate the previous response to Dutch" |
| "What is interoperability?" | retrieval | ["vocabulary"] | "Define interoperability in IEC/ESAV context" |
| "Add a Technology layer" | refinement | ["archimate"] | "Add a Technology layer to the previously generated ArchiMate model" |
| "github.com/org/repo" | inspect | [] | "Browse the repository at github.com/org/repo" |

## Query Rewrite Rules

For non-direct intents, produce a self-contained rewritten query:
- Resolve pronouns to concrete referents from conversation history
- Expand follow-ups with full context
- Preserve ADR/PCP numbers and domain terms exactly
- If already self-contained, return unchanged

## Output Format

Respond with a single JSON object only:

{"intent": "<intent>", "direct": false, "content": "<rewritten query or direct response>", \
"skill_tags": [], "doc_refs": [], "github_refs": [], "complexity": "simple", \
"synthesis_instruction": null, "steps": []}

- `direct`: true when answerable from conversation context without agent routing
- `doc_refs`: Specific document references like ["ADR.29", "PCP.10"]
- `github_refs`: GitHub repos as "owner/repo" — extract ONLY from the CURRENT MESSAGE, not from conversation history. If the current message contains no GitHub URL, set to []
- `complexity`: "simple" for single lookups, "multi-step" when combining user content with KB
- `steps`: For multi-step, 2-3 retrieval queries: [{"query": "...", "skill_tags": [], "doc_refs": []}]

For identity/off_topic/clarification/conversational: set direct=true, put response in content.
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
        self._cached_identity: str | None = None

    @property
    def _use_openai_api(self) -> bool:
        """True for any OpenAI-compatible API (GitHub Models or native OpenAI)."""
        return settings.effective_persona_provider in ("github_models", "openai")

    async def process(
        self,
        user_message: str,
        conversation_history: list[dict],
        conversation_id: str | None = None,
        active_artifact: dict | None = None,
    ) -> PersonaResult:
        """Classify intent and rewrite the query using conversation context.

        Args:
            user_message: The raw user message.
            conversation_history: List of message dicts from SQLite (with
                role, content, turn_summary fields).
            conversation_id: Conversation ID for loading running summary
                and user profile from the session store.
            active_artifact: Metadata dict with 'filename' and 'content_type'
                of the latest artifact in the conversation (if any).
                NOT the content itself -- just enough for routing decisions.

        Returns:
            PersonaResult with intent, rewritten query or direct response.
        """
        try:
            # R-14: Skip classification for models too slow for LLM routing.
            # These would timeout on the 62K+ prompt. Route directly to RAG.
            _persona_cfg = get_thresholds_value("get_persona_config", {})
            _skip_models = _persona_cfg.get("skip_classification_models", [])
            _current_model = settings.effective_persona_model
            if _current_model in _skip_models:
                logger.info(
                    "persona_skip_classification",
                    model=_current_model,
                    reason="model in skip_classification_models",
                )
                # Skip mode always routes to RAG with raw query. This means
                # cross-reference intent (document + KB comparison) cannot be
                # detected — all document uploads go to DOCUMENT_ANALYSIS.
                # Acceptable: slow models that timeout on classification would
                # also struggle with cross-reference workloads.
                return PersonaResult(
                    intent="retrieval",
                    rewritten_query=user_message,
                    direct_response=None,
                    original_message=user_message,
                )

            system_prompt = self._get_classification_prompt()

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
            if active_artifact:
                ct = active_artifact.get("content_type", "")
                fn = active_artifact.get("filename", "unnamed")
                if ct.startswith("document/"):
                    label = "uploaded document"
                elif "archimate" in ct or ct == "text/yaml":
                    label = "ArchiMate model (generated or uploaded)"
                elif "repo-analysis" in ct:
                    label = "repository analysis output"
                else:
                    label = "artifact"
                user_prompt_parts.append(
                    f'ACTIVE ARTIFACT: The conversation has an active {label}: '
                    f'"{fn}" (type: {ct}). '
                    f'Consider this when classifying the user\'s intent.'
                )
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

            # Never trust "direct=true" for intents that require agent routing.
            # The LLM may think it can answer from context, but it doesn't
            # have access to documents, KB tools, or generation pipelines.
            is_direct = (
                (parsed.get("direct", False) and parsed["intent"] not in _AGENT_REQUIRED_INTENTS)
                or parsed["intent"] in DIRECT_RESPONSE_INTENTS
            )
            if is_direct:
                # For direct responses, enrich with identity if available.
                # The minimal classification prompt doesn't include personality
                # or tone instructions, so direct responses would be bland.
                direct_content = parsed["content"] or user_message
                identity = self._get_identity_prompt()
                if identity and parsed["intent"] in DIRECT_RESPONSE_INTENTS:
                    try:
                        identity_prompt = (
                            f"{identity}\n\n"
                            "Respond to the user's message in character. "
                            "Keep it concise and helpful."
                        )
                        direct_content, id_latency = await self._classify(
                            identity_prompt, user_message,
                        )
                        latency_ms += id_latency
                        logger.info("identity_response_generated", latency_ms=id_latency)
                    except Exception as e:
                        logger.warning("identity_generation_failed", error=str(e))
                        # Fall back to classification's direct response

                return PersonaResult(
                    intent=parsed["intent"],
                    rewritten_query=None,
                    direct_response=direct_content,
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

    def _get_classification_prompt(self) -> str:
        """Return the minimal classification prompt (<5K chars).

        Uses _CLASSIFICATION_PROMPT (hardcoded) instead of the full
        persona-orchestrator SKILL.md (47K chars). The full skill file
        has detailed edge-case rules that improve quality on fast models,
        but causes guaranteed timeouts on Ollama and wastes 20-30s on
        cloud models. The minimal prompt covers all intents, skill tags,
        and output format.

        Identity content (ainstein-identity SKILL.md, 15K chars) is NOT
        loaded here — it's lazy-loaded only for direct response intents.
        """
        return _CLASSIFICATION_PROMPT

    def _get_identity_prompt(self) -> str:
        """Lazy-load ainstein-identity skill for direct response generation.

        Only called after classification determines a direct response is
        needed (identity, off_topic, clarification, conversational).
        """
        if self._cached_identity is not None:
            return self._cached_identity

        identity = self._loader.load_skill("ainstein-identity")
        if identity:
            self._cached_identity = identity.content
            logger.info("identity_prompt_loaded", chars=len(self._cached_identity))
        else:
            self._cached_identity = ""
            logger.warning("ainstein-identity skill not found")
        return self._cached_identity

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

        async with AsyncOpenAI(**settings.get_openai_client_kwargs(
            provider, timeout=settings.timeout_llm_inspect,
        )) as client:
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            token_limits = get_thresholds_value("get_llm_token_limits", {})
            if is_reasoning_model(model):
                kwargs["max_completion_tokens"] = token_limits.get("persona_reasoning", 2048)
            else:
                kwargs["max_tokens"] = token_limits.get("persona_standard", 500)

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
            complexity = raw_complexity if raw_complexity in ("simple", "multi-step", "listing") else "simple"
            # Force listing complexity for listing intent — the LLM sometimes
            # sets complexity="simple" even when intent="listing", which lets
            # the quality gate condense enumeration responses.
            if intent == "listing" and complexity != "listing":
                logger.info("persona_complexity_override intent=listing complexity=%s→listing", complexity)
                complexity = "listing"
            synthesis_instruction = data.get("synthesis_instruction") or None
            direct = bool(data.get("direct", False))
            raw_steps = data.get("steps", [])
            if isinstance(raw_steps, list):
                if len(raw_steps) > 3:
                    logger.warning(
                        "persona_steps_capped requested=%d cap=3",
                        len(raw_steps),
                    )
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
            # ── Complexity guardrails (code-level, not LLM-dependent) ──
            # Force multi-step when steps are populated — prevents silent
            # step drop if LLM sets complexity="simple" with populated steps.
            if steps and complexity != "multi-step":
                logger.info(
                    "persona_complexity_override steps=%d complexity=%s→multi-step",
                    len(steps), complexity,
                )
                complexity = "multi-step"
            # Warn when multi-step is set but no steps populated — orchestrator
            # will fall through to single RAG, which works but is worth logging.
            if complexity == "multi-step" and not steps:
                logger.warning("persona_complexity_mismatch complexity=multi-step steps=0")
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
