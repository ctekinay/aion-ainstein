"""Elysia-based agentic RAG system for AION-AINSTEIN.

Uses Weaviate's Elysia framework for decision tree-based tool selection
and agentic query processing.
"""

import logging
from typing import Optional, Any

from weaviate import WeaviateClient

from .config import settings

logger = logging.getLogger(__name__)

# Import elysia components
try:
    import elysia
    from elysia import tool, Tree
    ELYSIA_AVAILABLE = True
except ImportError as e:
    ELYSIA_AVAILABLE = False
    logger.warning(f"elysia-ai import failed: {e}")
except Exception as e:
    ELYSIA_AVAILABLE = False
    logger.warning(f"elysia-ai error: {e}")


class ElysiaRAGSystem:
    """Elysia-based agentic RAG system with custom tools for energy domain."""

    def __init__(self, client: WeaviateClient):
        """Initialize the Elysia RAG system.

        Args:
            client: Connected Weaviate client
        """
        if not ELYSIA_AVAILABLE:
            raise ImportError("elysia-ai package is required. Run: pip install elysia-ai")

        self.client = client
        self.tree = Tree()
        self._register_tools()

    def _register_tools(self) -> None:
        """Register custom tools for each knowledge domain."""

        # Vocabulary/SKOS search tool
        @tool(tree=self.tree)
        async def search_vocabulary(query: str, limit: int = 5) -> list[dict]:
            """Search SKOS vocabulary concepts from IEC standards (CIM, 61970, 61968, 62325).

            Use this tool when the user asks about:
            - Energy sector terminology and definitions
            - CIM (Common Information Model) concepts
            - IEC standards (61970, 61968, 62325, 62746)
            - SKOS concepts, vocabularies, or ontologies
            - Technical terms and their meanings

            Args:
                query: Search query for vocabulary concepts
                limit: Maximum number of results to return

            Returns:
                List of matching vocabulary concepts with definitions
            """
            collection = self.client.collections.get("Vocabulary")
            results = collection.query.hybrid(
                query=query,
                limit=limit,
                alpha=0.6,
            )
            return [
                {
                    "label": obj.properties.get("pref_label", ""),
                    "definition": obj.properties.get("definition", ""),
                    "vocabulary": obj.properties.get("vocabulary_name", ""),
                    "uri": obj.properties.get("uri", ""),
                }
                for obj in results.objects
            ]

        # ADR search tool
        @tool(tree=self.tree)
        async def search_architecture_decisions(query: str, limit: int = 5) -> list[dict]:
            """Search Architectural Decision Records (ADRs) for design decisions.

            Use this tool when the user asks about:
            - Architecture decisions and their rationale
            - Design choices and tradeoffs
            - Technical decisions and their context
            - ADRs or architectural records
            - System design patterns used

            Args:
                query: Search query for architecture decisions
                limit: Maximum number of results to return

            Returns:
                List of matching ADRs with context and decisions
            """
            collection = self.client.collections.get("ArchitecturalDecision")
            results = collection.query.hybrid(
                query=query,
                limit=limit,
                alpha=0.6,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "status": obj.properties.get("status", ""),
                    "context": obj.properties.get("context", "")[:500],
                    "decision": obj.properties.get("decision", "")[:500],
                    "consequences": obj.properties.get("consequences", "")[:300],
                }
                for obj in results.objects
            ]

        # Principles search tool
        @tool(tree=self.tree)
        async def search_principles(query: str, limit: int = 5) -> list[dict]:
            """Search architecture and governance principles.

            Use this tool when the user asks about:
            - Architecture principles and guidelines
            - Governance principles
            - Design principles and best practices
            - Standards and conventions

            Args:
                query: Search query for principles
                limit: Maximum number of results to return

            Returns:
                List of matching principles
            """
            collection = self.client.collections.get("Principle")
            results = collection.query.hybrid(
                query=query,
                limit=limit,
                alpha=0.6,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "content": obj.properties.get("content", "")[:800],
                    "doc_type": obj.properties.get("doc_type", ""),
                }
                for obj in results.objects
            ]

        # Policy document search tool
        @tool(tree=self.tree)
        async def search_policies(query: str, limit: int = 5) -> list[dict]:
            """Search data governance and policy documents.

            Use this tool when the user asks about:
            - Data governance policies
            - Data quality requirements
            - Compliance and regulatory policies
            - Data management policies
            - Security and privacy policies

            Args:
                query: Search query for policy documents
                limit: Maximum number of results to return

            Returns:
                List of matching policy documents
            """
            collection = self.client.collections.get("PolicyDocument")
            results = collection.query.hybrid(
                query=query,
                limit=limit,
                alpha=0.6,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "content": obj.properties.get("content", "")[:800],
                    "file_type": obj.properties.get("file_type", ""),
                }
                for obj in results.objects
            ]

        # List all ADRs tool
        @tool(tree=self.tree)
        async def list_all_adrs() -> list[dict]:
            """List all Architectural Decision Records in the system.

            Use this tool when the user asks:
            - What ADRs exist?
            - List all architecture decisions
            - Show me all ADRs
            - What decisions have been documented?

            Returns:
                Complete list of all ADRs with titles and status
            """
            collection = self.client.collections.get("ArchitecturalDecision")
            results = collection.query.fetch_objects(
                limit=100,
                return_properties=["title", "status", "file_path"],
            )
            adrs = []
            for obj in results.objects:
                title = obj.properties.get("title", "")
                file_path = obj.properties.get("file_path", "")
                # Skip templates
                if "template" in title.lower() or "template" in file_path.lower():
                    continue
                adrs.append({
                    "title": title,
                    "status": obj.properties.get("status", ""),
                    "file": file_path.split("/")[-1] if file_path else "",
                })
            return sorted(adrs, key=lambda x: x.get("file", ""))

        # List all principles tool
        @tool(tree=self.tree)
        async def list_all_principles() -> list[dict]:
            """List all architecture and governance principles.

            Use this tool when the user asks:
            - What principles exist?
            - List all principles
            - Show me the governance principles

            Returns:
                Complete list of all principles
            """
            collection = self.client.collections.get("Principle")
            results = collection.query.fetch_objects(
                limit=100,
                return_properties=["title", "doc_type"],
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "type": obj.properties.get("doc_type", ""),
                }
                for obj in results.objects
            ]

        # Collection statistics tool
        @tool(tree=self.tree)
        async def get_collection_stats() -> dict:
            """Get statistics about all collections in the knowledge base.

            Use this tool when the user asks:
            - How many documents are there?
            - What's in the knowledge base?
            - Show me the system status
            - Collection statistics

            Returns:
                Dictionary with collection names and document counts
            """
            collections = ["Vocabulary", "ArchitecturalDecision", "Principle", "PolicyDocument"]
            stats = {}
            for name in collections:
                if self.client.collections.exists(name):
                    collection = self.client.collections.get(name)
                    aggregate = collection.aggregate.over_all(total_count=True)
                    stats[name] = aggregate.total_count
                else:
                    stats[name] = 0
            return stats

        logger.info("Registered Elysia tools: vocabulary, ADR, principles, policies")

    async def query(self, question: str, collection_names: Optional[list[str]] = None) -> tuple[str, list[dict]]:
        """Process a query using Elysia's decision tree.

        Args:
            question: The user's question
            collection_names: Optional list of collection names to focus on

        Returns:
            Tuple of (response text, retrieved objects)
        """
        logger.info(f"Elysia processing: {question}")

        # Use Elysia's tree to process the query
        if collection_names:
            response, objects = self.tree(question, collection_names=collection_names)
        else:
            response, objects = self.tree(question)

        return response, objects

    def query_sync(self, question: str) -> str:
        """Synchronous query wrapper.

        Args:
            question: The user's question

        Returns:
            Response text from Elysia
        """
        import asyncio
        response, _ = asyncio.run(self.query(question))
        return response


def create_elysia_system(client: WeaviateClient) -> ElysiaRAGSystem:
    """Factory function to create an Elysia RAG system.

    Args:
        client: Connected Weaviate client

    Returns:
        Configured ElysiaRAGSystem instance
    """
    return ElysiaRAGSystem(client)
