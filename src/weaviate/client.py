"""Weaviate client configuration and connection management."""

import logging
from contextlib import contextmanager
from typing import Optional, Generator

import weaviate
from weaviate import WeaviateClient
from weaviate.classes.init import Auth, AdditionalConfig, Timeout

from ..config import settings

logger = logging.getLogger(__name__)


def get_weaviate_client() -> WeaviateClient:
    """Create and return a Weaviate client based on configuration.

    Returns:
        Connected WeaviateClient instance
    """
    # Send Weaviate's OpenAI API key header if available — needed for
    # text2vec-openai collections. Uses dedicated WEAVIATE_OPENAI_API_KEY
    # if set, otherwise falls back to OPENAI_API_KEY.
    headers = {}
    wv_key = settings.effective_weaviate_openai_api_key
    if wv_key:
        headers["X-OpenAI-Api-Key"] = wv_key

    if settings.weaviate_is_local:
        logger.info(f"Connecting to local Weaviate at {settings.weaviate_url}")
        client = weaviate.connect_to_local(
            host=settings.weaviate_url.replace("http://", "").replace("https://", "").split(":")[0],
            port=int(settings.weaviate_url.split(":")[-1]) if ":" in settings.weaviate_url else 8080,
            grpc_port=int(settings.weaviate_grpc_url.split(":")[-1]) if settings.weaviate_grpc_url else 50051,
            headers=headers,
        )
    else:
        if not settings.wcd_url or not settings.wcd_api_key:
            raise ValueError(
                "WCD_URL and WCD_API_KEY are required for cloud Weaviate connection"
            )
        logger.info(f"Connecting to Weaviate Cloud at {settings.wcd_url}")
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=settings.wcd_url,
            auth_credentials=Auth.api_key(settings.wcd_api_key),
            headers=headers,
        )

    # Verify connection
    if not client.is_ready():
        raise ConnectionError("Failed to connect to Weaviate")

    logger.info("Successfully connected to Weaviate")
    return client


@contextmanager
def weaviate_client() -> Generator[WeaviateClient, None, None]:
    """Context manager for Weaviate client.

    Yields:
        Connected WeaviateClient instance

    Example:
        with weaviate_client() as client:
            # Use client
            pass
    """
    client = get_weaviate_client()
    try:
        yield client
    finally:
        client.close()
        logger.info("Weaviate connection closed")
