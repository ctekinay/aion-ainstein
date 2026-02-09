"""Weaviate client and collection management."""

from .client import get_weaviate_client, WeaviateClient
from .collections import CollectionManager
from .ingestion import DataIngestionPipeline
from .skosmos_client import (
    SKOSMOSClient,
    get_skosmos_client,
    reset_skosmos_client,
    TermLookupResult,
    TermDefinition,
)

__all__ = [
    "get_weaviate_client",
    "WeaviateClient",
    "CollectionManager",
    "DataIngestionPipeline",
    "SKOSMOSClient",
    "get_skosmos_client",
    "reset_skosmos_client",
    "TermLookupResult",
    "TermDefinition",
]
