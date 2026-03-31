"""Post-generation quality gate for RAG responses.

Evaluates whether a response's shape matches the query's complexity
classification. When it doesn't, reshapes via LLM condensation or
code-level abstention cleanup.

All gate parameters are configurable in
skills/thresholds.yaml under quality_gate.
"""

from __future__ import annotations

import re
import time
from queue import Queue

import structlog

from aion.config import is_reasoning_model, settings

logger = structlog.get_logger(__name__)


def _get_quality_gate_config() -> dict:
    """Read quality gate config at call time (supports hot reload)."""
    from aion.skills.loader import SkillLoader

    loader = SkillLoader()
    thresholds = loader.get_thresholds("rag-quality-assurance")
    return thresholds.get("quality_gate", {"enabled": False})


def _estimate_tokens(text: str) -> int:
    """Rough word-count proxy for token estimation. For logging only."""
    return len(text.split())


def _extract_citations(text: str) -> set[str]:
    """Extract ADR.XX and PCP.XX citation patterns from text."""
    return set(re.findall(r"(?:ADR|PCP)\.\d+", text))


def _count_list_items(text: str) -> int:
    """Count structured list items (bullets, numbered lines, or repeated ID patterns).

    Detects:
      - Markdown bullets: ``- item``, ``* item``, ``• item``
      - Numbered lists: ``1. item``, ``2) item``
      - Repeated document IDs: ``ADR.XX``, ``PCP.XX`` at line start
    """
    return len(re.findall(
        r"^(?:\s*[-•*]\s+|\s*\d+[.)]\s+|(?:ADR|PCP)\.\d+)",
        text,
        re.MULTILINE,
    ))


def _emit(queue: Queue | None, agent_label: str, content: str) -> None:
    """Emit a QA status event to the UI trace."""
    if queue is not None:
        queue.put({
            "type": "status",
            "agent": agent_label,
            "content": content,
        })


class ResponseQualityGate:
    """Closed-loop quality gate: generate, evaluate, correct."""

    async def evaluate(
        self,
        response: str,
        query: str,
        complexity: str | None,
        event_queue: Queue | None,
        agent_label: str,
    ) -> tuple[str, dict]:
        """Evaluate and optionally reshape a RAG response.

        Returns (possibly_modified_response, gate_metadata).
        """
        config = _get_quality_gate_config()

        # Gate disabled or complexity not provided (CLI, tests, etc.)
        if not config.get("enabled", False) or complexity is None:
            return response, {"gate_fired": False, "action": "skipped"}

        # ── Abstention cleanup (code-level, zero latency) ──
        abstention_cfg = config.get("abstention_cleanup", {})
        if abstention_cfg.get("enabled", False):
            trimmed, meta = self._check_abstention_overflow(
                response, abstention_cfg,
            )
            if meta["gate_fired"]:
                _emit(queue=event_queue, agent_label=agent_label,
                      content=f"[QA] Abstention trimmed: {meta['reason']}")
                logger.info(
                    "[QA] gate_fired",
                    action="abstention_trimmed",
                    reason=meta["reason"],
                    original_tokens=meta["original_tokens"],
                    final_tokens=meta["final_tokens"],
                    latency_ms=0,
                )
                return trimmed, meta

        # ── Proportionality (LLM-assisted, simple queries only) ──
        if complexity != "simple":
            return response, {"gate_fired": False, "action": "passed"}

        # ── Enumeration guard (code-level, zero latency) ──
        # Responses with 5+ structured list items are enumerations that
        # condensation would destroy. Skip regardless of complexity/intent.
        enum_count = _count_list_items(response)
        if enum_count >= 5:
            logger.info(
                "[QA] gate_skipped",
                reason="enumeration detected",
                list_items=enum_count,
            )
            return response, {
                "gate_fired": False, "action": "skipped",
                "reason": f"enumeration detected ({enum_count} items)",
            }

        prop_cfg = config.get("proportionality", {})
        if not prop_cfg.get("enabled", False):
            return response, {"gate_fired": False, "action": "passed"}

        # Fast pre-check: skip LLM if response is already concise
        token_ceiling = prop_cfg.get("token_ceiling", 300)
        est_tokens = _estimate_tokens(response)
        if est_tokens <= token_ceiling:
            logger.info(
                "[QA] gate_skipped",
                reason="under token ceiling",
                response_tokens=est_tokens,
                ceiling=token_ceiling,
            )
            return response, {
                "gate_fired": False, "action": "skipped",
                "reason": "under token ceiling",
            }

        # LLM evaluation: is this response proportionate?
        gate_start = time.perf_counter()
        needs_condensation = await self._evaluate_proportionality(
            response, prop_cfg,
        )
        eval_ms = int((time.perf_counter() - gate_start) * 1000)

        if not needs_condensation:
            logger.info(
                "[QA] gate_passed",
                complexity="simple",
                response_tokens=est_tokens,
                latency_ms=eval_ms,
            )
            return response, {
                "gate_fired": False, "action": "passed",
                "latency_ms": eval_ms,
            }

        # Condensation pass
        condensed = await self._condense(response, query, prop_cfg)
        final_tokens = _estimate_tokens(condensed)

        # Citation recovery: check if condensation dropped any references
        original_citations = _extract_citations(response)
        condensed_citations = _extract_citations(condensed)
        missing = original_citations - condensed_citations
        if missing:
            sorted_missing = sorted(missing)
            condensed = f"{condensed}\n\nSee also: {', '.join(sorted_missing)}"
            final_tokens = _estimate_tokens(condensed)
            logger.warning(
                "[QA] citation_recovery",
                refs_restored=sorted_missing,
            )

        total_ms = int((time.perf_counter() - gate_start) * 1000)

        _emit(
            queue=event_queue, agent_label=agent_label,
            content=(
                f"[QA] Response condensed: simple query, "
                f"reshaped from {est_tokens} to {final_tokens} tokens"
            ),
        )
        logger.info(
            "[QA] gate_fired",
            action="condensed",
            reason="simple query, response disproportionate",
            original_tokens=est_tokens,
            final_tokens=final_tokens,
            latency_ms=total_ms,
        )
        return condensed, {
            "gate_fired": True,
            "action": "condensed",
            "reason": "simple query, response disproportionate",
            "original_tokens": est_tokens,
            "final_tokens": final_tokens,
            "latency_ms": total_ms,
        }

    # ── Private helpers ──

    def _check_abstention_overflow(
        self, response: str, config: dict,
    ) -> tuple[str, dict]:
        """Code-level heuristic: negation + too many list items → truncate."""
        threshold = config.get("item_threshold", 2)
        signals = config.get("negation_signals", [])

        paragraphs = response.strip().split("\n\n")
        if not paragraphs:
            return response, {"gate_fired": False}

        first_para = paragraphs[0].lower()
        has_negation = any(sig in first_para for sig in signals)
        if not has_negation:
            return response, {"gate_fired": False}

        # Count list items in the rest of the response
        rest = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else ""
        list_items = re.findall(r"^(?:\s*[-•*]|\s*\d+[.)]\s)", rest, re.MULTILINE)

        if len(list_items) <= threshold:
            return response, {"gate_fired": False}

        # Truncate: keep first paragraph + specific offer from truncated items
        # Extract brief hints from the list items so the offer isn't vague
        item_lines = re.findall(r"^(?:\s*[-•*]\s*|\s*\d+[.)]\s*)(.+)", rest, re.MULTILINE)
        hints = [line.strip()[:60].rstrip(".,:; ") for line in item_lines[:3]]
        if hints:
            hint_text = ", ".join(hints)
            offer = f"The document does mention related topics ({hint_text}). Want me to detail those?"
        else:
            offer = "The document contains related content — want me to surface it?"
        trimmed = f"{paragraphs[0]}\n\n{offer}"
        orig_tokens = _estimate_tokens(response)
        final_tokens = _estimate_tokens(trimmed)
        return trimmed, {
            "gate_fired": True,
            "action": "abstention_trimmed",
            "reason": (
                f"negation + {len(list_items)} items "
                f"exceeds threshold {threshold}"
            ),
            "original_tokens": orig_tokens,
            "final_tokens": final_tokens,
        }

    async def _evaluate_proportionality(
        self, response: str, config: dict,
    ) -> bool:
        """LLM call: is this response proportionate? Returns True if condensation needed."""
        prompt = config.get("evaluation_prompt", "")
        if not prompt:
            return False  # No prompt configured → pass

        model = config.get("model_override") or settings.effective_rag_model
        provider = settings.effective_rag_provider

        try:
            result = await self._llm_call(
                system_prompt=prompt,
                user_content=f"Response to evaluate:\n\n{response}",
                model=model,
                provider=provider,
                max_tokens=config.get("evaluation_max_tokens", 10),
            )
            # Default to pass — only condense on explicit FAIL
            return result.strip().upper().startswith("FAIL")
        except Exception as e:
            logger.warning(f"[QA] evaluation call failed: {e}, defaulting to pass")
            return False

    async def _condense(
        self, response: str, query: str, config: dict,
    ) -> str:
        """LLM call: condense the response to summary format."""
        prompt = config.get("condensation_prompt", "")
        if not prompt:
            return response  # No prompt → return original

        model = config.get("model_override") or settings.effective_rag_model
        provider = settings.effective_rag_provider

        try:
            result = await self._llm_call(
                system_prompt=prompt,
                user_content=(
                    f"Original query: {query}\n\n"
                    f"Response to condense:\n\n{response}"
                ),
                model=model,
                provider=provider,
                max_tokens=config.get("condensation_max_tokens", 1024),
            )
            return result.strip() if result.strip() else response
        except Exception as e:
            logger.warning(f"[QA] condensation call failed: {e}, using original")
            return response

    async def _llm_call(
        self,
        system_prompt: str,
        user_content: str,
        model: str,
        provider: str,
        max_tokens: int,
    ) -> str:
        """Direct LLM call (not agentic). Supports OpenAI and Ollama."""
        if provider in ("github_models", "openai"):
            from openai import AsyncOpenAI

            async with AsyncOpenAI(**settings.get_openai_client_kwargs(
                provider, timeout=settings.timeout_llm_inspect,
            )) as client:
                kwargs = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                }
                if is_reasoning_model(model):
                    kwargs["max_completion_tokens"] = max_tokens
                else:
                    kwargs["max_tokens"] = max_tokens

                resp = await client.chat.completions.create(**kwargs)
            choice = resp.choices[0] if resp.choices else None
            return choice.message.content or "" if choice else ""

        # Ollama
        import httpx

        async with httpx.AsyncClient(timeout=settings.timeout_llm_inspect) as client:
            resp = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": f"{system_prompt}\n\n{user_content}",
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
