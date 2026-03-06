"""Rolling summary generation for in-session memory.

Takes the current running summary + messages leaving the verbatim window
and produces an updated summary via a single LLM call. Uses the same
provider as the Persona (not the Tree).
"""

import logging
import re
import time

from src.aion.config import settings

logger = logging.getLogger(__name__)

_SUMMARIZE_PROMPT = """\
You are a conversation summarizer for AInstein, an architecture assistant.

Below is the CURRENT SUMMARY of the conversation so far (may be empty if this is the first summary), followed by NEW MESSAGES that need to be incorporated.

Update the summary to include key facts from the new messages. Preserve:
- User's name and any personal preferences
- Specific documents mentioned (ADR numbers, PCP numbers, policy names)
- Decisions made or opinions expressed
- Open questions or pending follow-ups
- Key findings from knowledge base searches

Keep the summary concise (~200 words max). Write in third person ("The user asked about..."). Do not include greetings or small talk.

CURRENT SUMMARY:
{current_summary}

NEW MESSAGES:
{new_messages}

UPDATED SUMMARY:"""

# Summarize only when this many messages have accumulated beyond the
# verbatim window. Prevents an LLM call on every single turn.
SUMMARIZE_TRIGGER_COUNT = 4


async def generate_rolling_summary(
    current_summary: str,
    messages_to_summarize: list[dict],
) -> str:
    """Generate an updated rolling summary incorporating new messages.

    Args:
        current_summary: The existing running summary (may be empty).
        messages_to_summarize: Messages that have left the verbatim window.

    Returns:
        Updated summary text.
    """
    if not messages_to_summarize:
        return current_summary

    # Format messages for the prompt
    lines = []
    for msg in messages_to_summarize:
        role = "User" if msg["role"] == "user" else "Assistant"
        text = msg.get("turn_summary") or msg.get("content", "")
        # Truncate very long messages for the summarizer
        if len(text) > 400:
            text = text[:400] + "..."
        lines.append(f"{role}: {text}")

    new_messages_text = "\n".join(lines)

    prompt = _SUMMARIZE_PROMPT.format(
        current_summary=current_summary or "(No summary yet — this is the start of the conversation)",
        new_messages=new_messages_text,
    )

    try:
        summary, latency_ms = await _call_llm(prompt)
        logger.info(f"Rolling summary generated: {latency_ms}ms, {len(summary)} chars")
        return summary.strip()
    except Exception as e:
        logger.warning(f"Rolling summary generation failed: {e}")
        # Fallback: keep the existing summary rather than losing it
        return current_summary


async def _call_llm(prompt: str) -> tuple[str, int]:
    """Single LLM call using the Persona's provider.

    Returns:
        Tuple of (response text, latency in ms).
    """
    provider = settings.effective_persona_provider

    if provider in ("github_models", "openai"):
        return await _call_openai(prompt)
    return await _call_ollama(prompt)


async def _call_ollama(prompt: str) -> tuple[str, int]:
    """Call Ollama for summary generation."""
    import httpx

    start = time.time()

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.ollama_url}/api/generate",
            json={
                "model": settings.effective_persona_model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 300},
            },
        )
        response.raise_for_status()
        result = response.json()
        text = result.get("response", "")

        # Strip <think> tags (chain-of-thought models)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"</?think>", "", text)

        latency = int((time.time() - start) * 1000)
        return text.strip(), latency


async def _call_openai(prompt: str) -> tuple[str, int]:
    """Call OpenAI-compatible API for summary generation."""
    from openai import OpenAI

    start = time.time()
    client = OpenAI(**settings.get_openai_client_kwargs(settings.effective_persona_provider))

    model = settings.effective_persona_model
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    model_base = model.rsplit("/", 1)[-1] if "/" in model else model
    if model_base.startswith("gpt-5"):
        kwargs["max_completion_tokens"] = 300
    else:
        kwargs["max_tokens"] = 300

    response = client.chat.completions.create(**kwargs)
    text = response.choices[0].message.content or ""

    latency = int((time.time() - start) * 1000)
    return text.strip(), latency
