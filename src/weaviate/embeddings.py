"""Client-side embedding utilities using Ollama.

This module provides a workaround for Weaviate's text2vec-ollama bug (#8406)
where the module ignores the apiEndpoint configuration and always connects
to localhost:11434, which fails in Docker environments.

Instead of relying on Weaviate's vectorizer, we:
1. Generate embeddings client-side using Ollama's /api/embed endpoint
2. Store objects with pre-computed vectors in Weaviate
3. Query using near_vector with client-computed query embeddings
"""

import atexit
import logging
import time
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# Known embedding dimensions by model name
_EMBEDDING_DIMENSIONS = {
    "nomic-embed-text-v2-moe": 768,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

# Cache for dynamically discovered dimensions
_dimension_cache: dict[str, int] = {}

# Backward compatibility constant
EMBEDDING_DIMENSION = 768

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


def get_embedding_dimension(model: str = None) -> int:
    """Get the embedding dimension for the configured or specified model.

    Checks a known model lookup table first. If the model is not found,
    makes a single test embedding call to discover the dimension and caches it.

    Args:
        model: Model name to look up. If None, uses settings.embedding_model.

    Returns:
        Embedding dimension as integer.
    """
    if model is None:
        model = settings.embedding_model

    # Check known dimensions
    if model in _EMBEDDING_DIMENSIONS:
        return _EMBEDDING_DIMENSIONS[model]

    # Check cache for previously discovered dimensions
    if model in _dimension_cache:
        return _dimension_cache[model]

    # Self-healing fallback: probe the model with a test embedding
    try:
        client = httpx.Client(timeout=30.0)
        response = client.post(
            f"{settings.ollama_url}/api/embed",
            json={"model": model, "input": "dimension probe"},
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings", [])
        client.close()
        if embeddings and len(embeddings) > 0:
            dim = len(embeddings[0])
            _dimension_cache[model] = dim
            logger.info(f"Discovered embedding dimension for '{model}': {dim}")
            return dim
    except Exception as e:
        logger.warning(f"Could not probe embedding dimension for '{model}': {e}. Using default 768.")

    return 768


class OllamaEmbeddings:
    """Client-side embedding generator using Ollama."""

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 300.0,  # Increased from 60s to 5 minutes for batch operations
    ):
        """Initialize the embeddings client.

        Args:
            model: Ollama model to use for embeddings
            base_url: Ollama API base URL (default: from settings)
            timeout: Request timeout in seconds (default 5 minutes for batches)
        """
        self.model = model or settings.ollama_embedding_model
        self.base_url = base_url or settings.ollama_url
        self.timeout = timeout
        self._client = None

    @property
    def _dimension(self) -> int:
        """Get the embedding dimension for this client's model."""
        return get_embedding_dimension(self.model)

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        if not text or not text.strip():
            logger.warning("Returning zero vector for empty/whitespace-only text input")
            return [0.0] * self._dimension

        try:
            response = self.client.post(
                f"{self.base_url}/api/embed",
                json={
                    "model": self.model,
                    "input": text,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Ollama returns embeddings in 'embeddings' array
            embeddings = data.get("embeddings", [])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]

            logger.warning(
                f"Ollama returned no embeddings for text (len={len(text)}): {text[:50]}... "
                "Returning zero vector fallback."
            )
            return [0.0] * self._dimension

        except httpx.HTTPError as e:
            logger.error(f"HTTP error generating embedding: {e}")
            raise
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts with retry logic.

        Falls back to one-at-a-time processing if batch fails.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Filter empty texts but keep track of indices
        non_empty_indices = []
        non_empty_texts = []
        for i, text in enumerate(texts):
            if text and text.strip():
                non_empty_indices.append(i)
                non_empty_texts.append(text)

        if not non_empty_texts:
            logger.warning(
                f"All {len(texts)} texts in batch are empty. Returning zero vectors."
            )
            return [[0.0] * self._dimension for _ in texts]

        # Try batch embedding with retries
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": self.model,
                        "input": non_empty_texts,
                    },
                )
                response.raise_for_status()
                data = response.json()

                non_empty_embeddings = data.get("embeddings", [])

                # Reconstruct full list with zero vectors for empty texts
                empty_count = len(texts) - len(non_empty_texts)
                result = [[0.0] * self._dimension for _ in texts]
                for i, idx in enumerate(non_empty_indices):
                    if i < len(non_empty_embeddings):
                        result[idx] = non_empty_embeddings[i]

                if empty_count > 0:
                    logger.warning(
                        f"Batch embedding: {empty_count}/{len(texts)} texts were empty, "
                        "using zero vector fallbacks for those entries."
                    )

                return result

            except httpx.HTTPError as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"Batch embedding attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {RETRY_DELAY_SECONDS}s..."
                    )
                    time.sleep(RETRY_DELAY_SECONDS)
                continue
            except Exception as e:
                last_error = e
                break

        # Batch failed - fall back to one-at-a-time processing
        logger.warning(
            f"Batch embedding failed after {MAX_RETRIES} attempts. "
            f"Falling back to individual processing for {len(non_empty_texts)} texts..."
        )

        result = [[0.0] * self._dimension for _ in texts]
        success_count = 0

        for i, idx in enumerate(non_empty_indices):
            text = non_empty_texts[i]
            for attempt in range(MAX_RETRIES):
                try:
                    embedding = self.embed(text)
                    result[idx] = embedding
                    success_count += 1
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY_SECONDS)
                    else:
                        logger.error(
                            f"Failed to embed text {i} after {MAX_RETRIES} attempts: {e}. "
                            "Using zero vector fallback."
                        )

        failed_count = len(non_empty_texts) - success_count
        if failed_count > 0:
            logger.warning(
                f"Individual processing complete: {success_count}/{len(non_empty_texts)} succeeded, "
                f"{failed_count} texts using zero vector fallbacks."
            )
        else:
            logger.info(f"Individual processing complete: {success_count}/{len(non_empty_texts)} succeeded")
        return result

    def close(self):
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Global instance for convenience
_embeddings_client: Optional[OllamaEmbeddings] = None


def get_embeddings_client() -> OllamaEmbeddings:
    """Get the global embeddings client instance."""
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = OllamaEmbeddings()
    return _embeddings_client


def close_embeddings_client() -> None:
    """Close and reset the global embeddings client.

    Safe to call multiple times (idempotent). Should be called during
    application shutdown to properly release HTTP connections.
    Also registered with atexit as a safety net for CLI scripts.
    """
    global _embeddings_client
    if _embeddings_client is not None:
        _embeddings_client.close()
        _embeddings_client = None
        logger.debug("Global embeddings client closed")


# Register cleanup for normal interpreter exit
atexit.register(close_embeddings_client)


def embed_text(text: str) -> list[float]:
    """Generate embedding for a single text using global client.

    Args:
        text: Text to embed

    Returns:
        Embedding vector as list of floats
    """
    return get_embeddings_client().embed(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts using global client.

    Args:
        texts: List of texts to embed

    Returns:
        List of embedding vectors
    """
    return get_embeddings_client().embed_batch(texts)
