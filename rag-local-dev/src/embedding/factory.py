"""
Embedding provider abstraction.
Enables switching between OpenAI, Together AI, and local models.
"""

from abc import ABC, abstractmethod
from typing import List
import logging

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the dimension of embeddings produced by this provider."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model name/identifier."""
        pass

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of texts and return their embeddings.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each a list of floats)
        """
        pass

    def embed_single(self, text: str) -> List[float]:
        """Embed a single text and return its embedding."""
        return self.embed([text])[0]


class OpenAIEmbedder(EmbeddingProvider):
    """OpenAI embedding provider using text-embedding-3-small."""

    def __init__(self, model: str = "text-embedding-3-small", dimensions: int = 1536):
        import openai

        self.client = openai.OpenAI()
        self.model = model
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self.model

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts using OpenAI API."""
        if not texts:
            return []

        # Handle empty strings
        texts = [t if t.strip() else " " for t in texts]

        try:
            response = self.client.embeddings.create(model=self.model, input=texts)
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            raise


class TogetherEmbedder(EmbeddingProvider):
    """Together AI embedding provider for multilingual models."""

    def __init__(
        self, model: str = "intfloat/multilingual-e5-large-instruct", dimensions: int = 1024
    ):
        try:
            from together import Together

            self.client = Together()
        except ImportError:
            raise ImportError("together package not installed. Install with: pip install together")

        self.model = model
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self.model

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts using Together AI API."""
        if not texts:
            return []

        texts = [t if t.strip() else " " for t in texts]

        try:
            response = self.client.embeddings.create(model=self.model, input=texts)
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"Together embedding failed: {e}")
            raise


class LocalEmbedder(EmbeddingProvider):
    """Local embedding provider using sentence-transformers."""

    def __init__(self, model: str = "intfloat/multilingual-e5-large", device: str = "cuda"):
        try:
            from sentence_transformers import SentenceTransformer

            self.model_instance = SentenceTransformer(model, device=device)
        except ImportError:
            raise ImportError(
                "sentence-transformers package not installed. "
                "Install with: pip install sentence-transformers"
            )

        self.model = model
        self._dimensions = self.model_instance.get_sentence_embedding_dimension()

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self.model

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts using local model."""
        if not texts:
            return []

        texts = [t if t.strip() else " " for t in texts]

        try:
            embeddings = self.model_instance.encode(texts, normalize_embeddings=True)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Local embedding failed: {e}")
            raise


def get_embedder(config: dict) -> EmbeddingProvider:
    """
    Factory function to create appropriate embedding provider.

    Args:
        config: Configuration dictionary with embedding settings

    Returns:
        An EmbeddingProvider instance

    Example config:
        {
            "embedding": {
                "provider": "openai",
                "openai": {
                    "model": "text-embedding-3-small",
                    "dimensions": 1536
                }
            }
        }
    """
    embedding_config = config.get("embedding", {})
    provider = embedding_config.get("provider", "openai")
    provider_config = embedding_config.get(provider, {})

    providers = {
        "openai": OpenAIEmbedder,
        "together": TogetherEmbedder,
        "local": LocalEmbedder,
    }

    if provider not in providers:
        raise ValueError(f"Unknown embedding provider: {provider}. Available: {list(providers.keys())}")

    logger.info(f"Initializing {provider} embedding provider with config: {provider_config}")

    return providers[provider](**provider_config)
