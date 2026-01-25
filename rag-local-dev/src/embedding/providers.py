"""
Re-export embedding providers for convenient imports.
"""

from .factory import (
    EmbeddingProvider,
    OpenAIEmbedder,
    TogetherEmbedder,
    LocalEmbedder,
    get_embedder,
)

__all__ = [
    "EmbeddingProvider",
    "OpenAIEmbedder",
    "TogetherEmbedder",
    "LocalEmbedder",
    "get_embedder",
]
