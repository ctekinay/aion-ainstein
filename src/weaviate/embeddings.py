"""Client-side embedding utilities using Ollama.

Workaround for Weaviate text2vec-ollama bug (GitHub Issue #8406) where
the module ignores configured apiEndpoint and defaults to localhost:11434.

This module computes embeddings directly via Ollama's /api/embed endpoint,
bypassing Weaviate's buggy text2vec-ollama module entirely.
"""

import logging
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# Nomic embed text v2 produces 768-dimensional vectors
NOMIC_EMBEDDING_DIMENSIONS = 768


async def get_embedding_async(
    text: str,
    model: Optional[str] = None,
    ollama_url: Optional[str] = None,
) -> list[float]:
    """Get embedding vector for text using Ollama (async).

    Args:
        text: Text to embed
        model: Embedding model (default: settings.ollama_embedding_model)
        ollama_url: Ollama API URL (default: settings.ollama_url for host machine)

    Returns:
        List of floats representing the embedding vector
    """
    model = model or settings.ollama_embedding_model
    url = ollama_url or settings.ollama_url  # Use host URL, not docker URL

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{url}/api/embed",
            json={"model": model, "input": text},
        )
        response.raise_for_status()
        result = response.json()

        # Ollama returns {"embeddings": [[...]]} for single input
        embeddings = result.get("embeddings", [])
        if embeddings and len(embeddings) > 0:
            return embeddings[0]
        raise ValueError(f"No embeddings returned from Ollama: {result}")


def get_embedding_sync(
    text: str,
    model: Optional[str] = None,
    ollama_url: Optional[str] = None,
) -> list[float]:
    """Get embedding vector for text using Ollama (sync).

    Args:
        text: Text to embed
        model: Embedding model (default: settings.ollama_embedding_model)
        ollama_url: Ollama API URL (default: settings.ollama_url for host machine)

    Returns:
        List of floats representing the embedding vector
    """
    model = model or settings.ollama_embedding_model
    url = ollama_url or settings.ollama_url

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            f"{url}/api/embed",
            json={"model": model, "input": text},
        )
        response.raise_for_status()
        result = response.json()

        embeddings = result.get("embeddings", [])
        if embeddings and len(embeddings) > 0:
            return embeddings[0]
        raise ValueError(f"No embeddings returned from Ollama: {result}")


def get_embeddings_batch_sync(
    texts: list[str],
    model: Optional[str] = None,
    ollama_url: Optional[str] = None,
) -> list[list[float]]:
    """Get embedding vectors for multiple texts using Ollama (sync).

    Args:
        texts: List of texts to embed
        model: Embedding model (default: settings.ollama_embedding_model)
        ollama_url: Ollama API URL (default: settings.ollama_url)

    Returns:
        List of embedding vectors
    """
    model = model or settings.ollama_embedding_model
    url = ollama_url or settings.ollama_url

    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            f"{url}/api/embed",
            json={"model": model, "input": texts},
        )
        response.raise_for_status()
        result = response.json()

        embeddings = result.get("embeddings", [])
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Expected {len(texts)} embeddings, got {len(embeddings)}"
            )
        return embeddings


def build_searchable_text(obj: dict, collection_type: str) -> str:
    """Build searchable text from object properties for embedding.

    Args:
        obj: Object properties dictionary
        collection_type: Type of collection (vocabulary, adr, principle, policy)

    Returns:
        Combined text for embedding
    """
    if collection_type == "vocabulary":
        parts = [
            obj.get("pref_label", ""),
            obj.get("definition", ""),
            " ".join(obj.get("alt_labels", [])),
            obj.get("content", ""),
        ]
    elif collection_type == "adr":
        parts = [
            obj.get("title", ""),
            obj.get("context", ""),
            obj.get("decision", ""),
            obj.get("consequences", ""),
            obj.get("full_text", ""),
        ]
    elif collection_type == "principle":
        parts = [
            obj.get("title", ""),
            obj.get("content", ""),
            obj.get("full_text", ""),
        ]
    elif collection_type == "policy":
        parts = [
            obj.get("title", ""),
            obj.get("content", ""),
            obj.get("full_text", ""),
        ]
    else:
        # Generic fallback
        parts = [
            obj.get("title", ""),
            obj.get("content", ""),
            obj.get("full_text", ""),
        ]

    # Combine non-empty parts
    text = " ".join(p for p in parts if p)
    return text[:8000]  # Limit to avoid token overflow
