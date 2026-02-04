"""Client-side embedding utilities using Ollama.

This module provides a workaround for Weaviate's text2vec-ollama bug (#8406)
where the module ignores the apiEndpoint configuration and always connects
to localhost:11434, which fails in Docker environments.

Instead of relying on Weaviate's vectorizer, we:
1. Generate embeddings client-side using Ollama's /api/embed endpoint
2. Store objects with pre-computed vectors in Weaviate
3. Query using near_vector with client-computed query embeddings
"""

import logging
import time
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# Ollama embedding dimensions (nomic-embed-text-v2-moe)
EMBEDDING_DIMENSION = 768

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


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
            # Return zero vector for empty text
            return [0.0] * EMBEDDING_DIMENSION

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

            logger.warning(f"No embeddings returned for text: {text[:50]}...")
            return [0.0] * EMBEDDING_DIMENSION

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
            return [[0.0] * EMBEDDING_DIMENSION for _ in texts]

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
                result = [[0.0] * EMBEDDING_DIMENSION for _ in texts]
                for i, idx in enumerate(non_empty_indices):
                    if i < len(non_empty_embeddings):
                        result[idx] = non_empty_embeddings[i]

                return result

            except (httpx.HTTPError, httpx.TimeoutException) as e:
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

        result = [[0.0] * EMBEDDING_DIMENSION for _ in texts]
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
                        logger.error(f"Failed to embed text {i}: {e}")
                        # Keep zero vector for failed embeddings

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
