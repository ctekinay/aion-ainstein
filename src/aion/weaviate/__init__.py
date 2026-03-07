"""Weaviate client and collection management."""

from src.aion.weaviate.client import WeaviateClient, get_weaviate_client
from src.aion.weaviate.collections import CollectionManager
from src.aion.weaviate.ingestion import DataIngestionPipeline

__all__ = ["get_weaviate_client", "WeaviateClient", "CollectionManager", "DataIngestionPipeline"]
