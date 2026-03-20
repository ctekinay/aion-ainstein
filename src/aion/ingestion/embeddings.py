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

import httpx

from aion.config import settings

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

    # Probe only works for Ollama models (direct HTTP endpoint)
    if settings.effective_embedding_provider == "ollama":
        try:
            client = httpx.Client(timeout=settings.timeout_llm_call)
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
            logger.warning(f"Could not probe embedding dimension for '{model}': {e}")

    raise ValueError(
        f"Unknown embedding dimension for model '{model}'. "
        f"Add it to _EMBEDDING_DIMENSIONS in embeddings.py."
    )


class OllamaEmbeddings:
    """Client-side embedding generator using Ollama."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = settings.timeout_long_running,
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

        Raises:
            ValueError: If text is empty or whitespace-only
        """
        if not text or not text.strip():
            raise ValueError("Cannot embed empty or whitespace-only text")

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

            raise RuntimeError(
                f"Ollama returned no embeddings for text (len={len(text)}): {text[:50]}..."
            )

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
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"Batch embedding attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {RETRY_DELAY_SECONDS}s..."
                    )
                    time.sleep(RETRY_DELAY_SECONDS)
                continue
            except Exception:
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


class OpenAIEmbeddings:
    """Client-side embedding generator using OpenAI's API.

    Same interface as OllamaEmbeddings (embed / embed_batch / close).
    Does NOT include one-at-a-time fallback in embed_batch — OpenAI batch
    failures are typically auth/rate-limit issues that affect all items
    equally, so retrying individually wouldn't help.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        batch_size: int = 100,
    ):
        self.model = model or settings.openai_embedding_model
        self._api_key = api_key or settings.openai_api_key
        self._client = None
        self.batch_size = batch_size

    @property
    def _dimension(self) -> int:
        return get_embedding_dimension(self.model)

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            from aion.config import _OPENAI_CLIENT_DEFAULTS
            self._client = OpenAI(
                api_key=self._api_key, **_OPENAI_CLIENT_DEFAULTS
            )
        return self._client

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Raises:
            ValueError: If text is empty or whitespace-only
        """
        if not text or not text.strip():
            raise ValueError("Cannot embed empty or whitespace-only text")

        for attempt in range(MAX_RETRIES):
            try:
                resp = self.client.embeddings.create(model=self.model, input=text)
                return resp.data[0].embedding
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                logger.warning(
                    f"Embedding retry {attempt + 1}/{MAX_RETRIES}: {e}"
                )
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts in batches."""
        if not texts:
            return []

        results: list[list[float]] = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]

            # Separate empty vs non-empty, tracking original indices
            non_empty = [(j, t) for j, t in enumerate(batch) if t and t.strip()]
            batch_results: list[list[float] | None] = [None] * len(batch)

            # Fill empties with zero vectors
            for j in range(len(batch)):
                if not batch[j] or not batch[j].strip():
                    batch_results[j] = [0.0] * self._dimension

            if non_empty:
                for attempt in range(MAX_RETRIES):
                    try:
                        resp = self.client.embeddings.create(
                            model=self.model,
                            input=[t for _, t in non_empty],
                        )
                        for k, (j, _) in enumerate(non_empty):
                            batch_results[j] = resp.data[k].embedding
                        break
                    except Exception as e:
                        if attempt == MAX_RETRIES - 1:
                            raise
                        logger.warning(
                            f"Batch embedding retry {attempt + 1}/{MAX_RETRIES}: {e}"
                        )
                        time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))

            results.extend(batch_results)

        return results

    def close(self):
        """Release the OpenAI client."""
        self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Global instance for convenience
_embeddings_client: OllamaEmbeddings | OpenAIEmbeddings | None = None


def get_embeddings_client() -> OllamaEmbeddings | OpenAIEmbeddings:
    """Get the global embeddings client instance.

    Provider is determined by settings.effective_embedding_provider.
    Singleton — provider changes at runtime require app restart
    (and re-ingestion).
    """
    global _embeddings_client
    if _embeddings_client is None:
        provider = settings.effective_embedding_provider
        if provider == "ollama":
            _embeddings_client = OllamaEmbeddings()
        elif provider == "openai":
            _embeddings_client = OpenAIEmbeddings()
        else:
            raise ValueError(
                f"Embedding provider '{provider}' does not support embeddings. "
                "Set EMBEDDING_PROVIDER=ollama or EMBEDDING_PROVIDER=openai."
            )
        logger.info(
            "Embeddings client: %s (%s)",
            type(_embeddings_client).__name__, settings.embedding_model,
        )
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
