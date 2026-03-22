"""Shared text utilities."""

__all__ = ["strip_think_tags", "elapsed_ms"]

import re
import time


def strip_think_tags(text: str) -> str:
    """Strip <think>...</think> tags from model output.

    Chain-of-thought models (SmolLM3, Qwen3) wrap reasoning in <think> tags.
    These must be removed before showing output to users.
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?think>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def elapsed_ms(start: float) -> int:
    """Milliseconds elapsed since *start* (a ``time.perf_counter()`` value)."""
    return int((time.perf_counter() - start) * 1000)
