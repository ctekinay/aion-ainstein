"""Weaviate client and collection management."""

from .client import get_weaviate_client, WeaviateClient
from .collections import CollectionManager
from .ingestion import DataIngestionPipeline

__all__ = ["get_weaviate_client", "WeaviateClient", "CollectionManager", "DataIngestionPipeline"]
