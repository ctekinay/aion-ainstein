"""Intent classification via embedding similarity."""

from .embedding_classifier import (
    ClassificationResult,
    EmbeddingClassifier,
    DEFAULT_THRESHOLDS,
    DEFAULT_MIN_MARGIN,
)

__all__ = [
    "ClassificationResult",
    "EmbeddingClassifier",
    "DEFAULT_THRESHOLDS",
    "DEFAULT_MIN_MARGIN",
]
