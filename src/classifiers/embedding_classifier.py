"""Embedding-based intent classifier for architecture queries.

Replaces the signal-based scoring gate (_extract_signals → _score_intents →
_select_winner) with cosine-similarity classification against prototype
utterance centroids.

Intents (6 — no 'followup', which is handled by rule-based pre-check):
  list, count, lookup_doc, semantic_answer, compare, conversational

Maintenance surface: add example utterances to config/intent_prototypes.yaml
instead of expanding regex lists.
"""

import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import yaml

logger = logging.getLogger(__name__)

# Default confidence thresholds per intent (tune from parallel-run data)
DEFAULT_THRESHOLDS: dict[str, float] = {
    "list": 0.45,
    "count": 0.45,
    "lookup_doc": 0.40,
    "semantic_answer": 0.35,
    "compare": 0.40,
    "conversational": 0.30,
}

DEFAULT_MIN_MARGIN: float = 0.03


@dataclass
class ClassificationResult:
    """Result of intent classification."""

    intent: str
    confidence: float
    margin: float
    scores: dict[str, float] = field(default_factory=dict)
    threshold_met: bool = False
    margin_ok: bool = False


def _l2_normalize(vec: list[float]) -> list[float]:
    """L2-normalize a vector. Returns zero vector if norm is 0."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-12:
        return vec
    return [x / norm for x in vec]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors (assumed L2-normalized)."""
    return sum(x * y for x, y in zip(a, b))


def _mean_vectors(vectors: list[list[float]]) -> list[float]:
    """Element-wise mean of a list of vectors."""
    if not vectors:
        return []
    dim = len(vectors[0])
    result = [0.0] * dim
    for vec in vectors:
        for i, v in enumerate(vec):
            result[i] += v
    n = len(vectors)
    return [x / n for x in result]


class EmbeddingClassifier:
    """Classify user queries into intents via embedding cosine similarity.

    Init:
        Embeds all prototype utterances, computes per-intent centroids
        (mean of L2-normalized vectors, re-normalized).

    Classify:
        Embeds the query, computes cosine similarity to each centroid,
        applies threshold + margin gate.

    Args:
        embed_fn: Function to embed a single text → list[float]
        embed_batch_fn: Function to embed a batch → list[list[float]]
        prototypes: Dict mapping intent → list of example utterances.
            If provided, prototype_file is ignored.
        prototype_file: Path to YAML file with prototypes.
            Used only if prototypes is None.
        thresholds: Per-intent confidence thresholds.
        min_margin: Minimum gap between top-1 and top-2 scores.
    """

    def __init__(
        self,
        embed_fn: Callable[[str], list[float]],
        embed_batch_fn: Callable[[list[str]], list[list[float]]],
        prototypes: Optional[dict[str, list[str]]] = None,
        prototype_file: Optional[Path] = None,
        thresholds: Optional[dict[str, float]] = None,
        min_margin: float = DEFAULT_MIN_MARGIN,
    ):
        self._embed_fn = embed_fn
        self._embed_batch_fn = embed_batch_fn
        self._thresholds = thresholds or dict(DEFAULT_THRESHOLDS)
        self._min_margin = min_margin

        # Load prototypes
        if prototypes is not None:
            proto_map = prototypes
        elif prototype_file is not None:
            proto_map = self._load_yaml(prototype_file)
        else:
            raise ValueError("Either prototypes or prototype_file must be provided")

        if not proto_map:
            raise ValueError("Prototype bank is empty — cannot build centroids")

        # Store prototype counts for diagnostics
        self._prototype_counts: dict[str, int] = {
            intent: len(utterances) for intent, utterances in proto_map.items()
        }

        # Build centroids
        try:
            self._centroids = self._build_centroids(proto_map)
        except (ConnectionError, OSError, Exception) as e:
            raise RuntimeError(
                f"EmbeddingClassifier init failed: Ollama unavailable. "
                f"Flip embedding_classifier_enabled to false or fix Ollama. "
                f"Error: {e}"
            ) from e

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, list[str]]:
        """Load prototypes from YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Prototype file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        # Support both flat format and nested format with 'intents' key
        if "intents" in data:
            return data["intents"]
        # Filter out _meta and non-dict entries
        return {k: v for k, v in data.items() if k != "_meta" and isinstance(v, list)}

    def _build_centroids(
        self, proto_map: dict[str, list[str]]
    ) -> dict[str, list[float]]:
        """Embed all prototypes and compute per-intent centroids."""
        # Flatten all texts for batch embedding
        all_texts: list[str] = []
        intent_ranges: list[tuple[str, int, int]] = []
        for intent, utterances in proto_map.items():
            start = len(all_texts)
            all_texts.extend(utterances)
            intent_ranges.append((intent, start, len(all_texts)))

        logger.info(
            "Building centroids: %d prototypes across %d intents",
            len(all_texts), len(proto_map),
        )

        # Batch embed (timed for init latency monitoring)
        t0 = time.monotonic()
        all_embeddings = self._embed_batch_fn(all_texts)
        embed_ms = (time.monotonic() - t0) * 1000

        # Compute centroids
        centroids: dict[str, list[float]] = {}
        for intent, start, end in intent_ranges:
            vecs = [_l2_normalize(all_embeddings[i]) for i in range(start, end)]
            mean = _mean_vectors(vecs)
            centroids[intent] = _l2_normalize(mean)

        total_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Centroids built for %d intents: embed=%.0fms total=%.0fms",
            len(centroids), embed_ms, total_ms,
        )
        return centroids

    def classify(self, query: str) -> ClassificationResult:
        """Classify a query into an intent.

        Returns ClassificationResult with intent, confidence, margin, and gate flags.
        On embedding failure, returns conversational with confidence=0.
        """
        try:
            qvec = _l2_normalize(self._embed_fn(query))
        except Exception:
            logger.error("Embedding failed for query, falling back to conversational")
            return ClassificationResult(
                intent="conversational",
                confidence=0.0,
                margin=0.0,
                scores={},
                threshold_met=False,
                margin_ok=False,
            )

        # Compute cosine similarity to each centroid
        scores: dict[str, float] = {}
        for intent, centroid in self._centroids.items():
            scores[intent] = _cosine_similarity(qvec, centroid)

        # Rank by score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        winner_name, winner_score = ranked[0]
        runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = winner_score - runner_up_score

        # Apply threshold gate
        threshold = self._thresholds.get(winner_name, 0.35)
        threshold_met = winner_score >= threshold
        margin_ok = margin >= self._min_margin

        # If threshold not met, fall back to conversational
        if not threshold_met:
            return ClassificationResult(
                intent="conversational",
                confidence=winner_score,
                margin=margin,
                scores=scores,
                threshold_met=False,
                margin_ok=margin_ok,
            )

        logger.info(
            "CLASSIFY_TRACE intent=%s conf=%.2f margin=%.2f "
            "threshold_met=%s margin_ok=%s top3=%s",
            winner_name, winner_score, margin,
            threshold_met, margin_ok,
            [(n, round(s, 2)) for n, s in ranked[:3]],
        )

        return ClassificationResult(
            intent=winner_name,
            confidence=winner_score,
            margin=margin,
            scores=scores,
            threshold_met=threshold_met,
            margin_ok=margin_ok,
        )

    def explain(self, query: str) -> dict:
        """Diagnostic tool: returns detailed classification breakdown."""
        result = self.classify(query)
        ranked = sorted(result.scores.items(), key=lambda x: x[1], reverse=True)
        return {
            "query": query,
            "winner": result.intent,
            "confidence": result.confidence,
            "margin": result.margin,
            "threshold_met": result.threshold_met,
            "margin_ok": result.margin_ok,
            "top_scores": [(name, round(score, 4)) for name, score in ranked],
            "thresholds": dict(self._thresholds),
            "min_margin": self._min_margin,
        }
