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

        # List policy files tool (document-level, not chunks)
        @tool(tree=self.tree)
        async def list_policy_files(department: str = None) -> list[dict]:
            """List all policy source files with their metadata.

            Use this tool when the user asks:
            - How many policy files/PDFs/documents are there?
            - What policy documents exist?
            - List all policies
            - Which files are from Data Office / Security / etc?
            - Show me policy file details

            This returns actual source files (not chunks), with metadata like
            department, version, date, and page count.

            Args:
                department: Optional filter by department (e.g., "Data Office", "General")

            Returns:
                List of policy files with metadata
            """
            if not self.client.collections.exists("PolicyFile"):
                # Fallback: aggregate from PolicyDocument chunks
                collection = self.client.collections.get("PolicyDocument")
                results = collection.query.fetch_objects(
                    limit=200,
                    return_properties=["file_path", "title", "file_type", "department", "page_count", "total_chunks"],
                )
                # Deduplicate by file_path
                seen = {}
                for obj in results.objects:
                    fp = obj.properties.get("file_path", "")
                    if fp and fp not in seen:
                        seen[fp] = {
                            "file_name": fp.split("/")[-1].split("\\")[-1],
                            "title": obj.properties.get("title", "").split(" (Part ")[0],
                            "department": obj.properties.get("department", "Unknown"),
                            "file_type": obj.properties.get("file_type", ""),
                            "page_count": obj.properties.get("page_count", 0),
                            "chunk_count": obj.properties.get("total_chunks", 1),
                        }
                files = list(seen.values())
            else:
                collection = self.client.collections.get("PolicyFile")
                results = collection.query.fetch_objects(
                    limit=100,
                    return_properties=[
                        "file_name", "title", "department", "file_type",
                        "page_count", "chunk_count", "document_version", "document_date"
                    ],
                )
                files = [
                    {
                        "file_name": obj.properties.get("file_name", ""),
                        "title": obj.properties.get("title", ""),
                        "department": obj.properties.get("department", "Unknown"),
                        "file_type": obj.properties.get("file_type", ""),
                        "page_count": obj.properties.get("page_count", 0),
                        "chunk_count": obj.properties.get("chunk_count", 1),
                        "version": obj.properties.get("document_version", ""),
                        "date": obj.properties.get("document_date", ""),
                    }
                    for obj in results.objects
                ]

            # Filter by department if specified
            if department:
                files = [f for f in files if department.lower() in f.get("department", "").lower()]

            return files

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
            collections = ["Vocabulary", "ArchitecturalDecision", "Principle", "PolicyDocument", "PolicyFile"]
            stats = {}
            for name in collections:
                if self.client.collections.exists(name):
                    collection = self.client.collections.get(name)
                    aggregate = collection.aggregate.over_all(total_count=True)
                    stats[name] = aggregate.total_count
                else:
                    stats[name] = 0
            return stats

        logger.info("Registered Elysia tools: vocabulary, ADR, principles, policies, list_policy_files")

    async def query(self, question: str, collection_names: Optional[list[str]] = None) -> tuple[str, list[dict]]:
        """Process a query using Elysia's decision tree.

        Args:
            question: The user's question
            collection_names: Optional list of collection names to focus on

        Returns:
            Tuple of (response text, retrieved objects)
        """
        logger.info(f"Elysia processing: {question}")

        # Always specify our collection names to bypass Elysia's metadata collection discovery
        # This avoids gRPC errors from Elysia's internal collections
        our_collections = collection_names or [
            "Vocabulary",
            "ArchitecturalDecision",
            "Principle",
            "PolicyDocument",
            "PolicyFile",
        ]

        try:
            response, objects = self.tree(question, collection_names=our_collections)
        except Exception as e:
            # If Elysia's tree fails, fall back to direct tool execution
            logger.warning(f"Elysia tree failed: {e}, using direct tool execution")
            response, objects = await self._direct_query(question)

        return response, objects

    async def _direct_query(self, question: str) -> tuple[str, list[dict]]:
        """Direct query execution bypassing Elysia tree when it fails.

        Args:
            question: The user's question

        Returns:
            Tuple of (response text, retrieved objects)
        """
        from openai import OpenAI

        # Determine which collections to search based on the question
        question_lower = question.lower()
        all_results = []

        # Search relevant collections
        if any(term in question_lower for term in ["adr", "decision", "architecture"]):
            collection = self.client.collections.get("ArchitecturalDecision")
            results = collection.query.hybrid(query=question, limit=5, alpha=0.6)
            for obj in results.objects:
                all_results.append({
                    "type": "ADR",
                    "title": obj.properties.get("title", ""),
                    "content": obj.properties.get("decision", "")[:500],
                })

        if any(term in question_lower for term in ["principle", "governance", "esa"]):
            collection = self.client.collections.get("Principle")
            results = collection.query.hybrid(query=question, limit=5, alpha=0.6)
            for obj in results.objects:
                all_results.append({
                    "type": "Principle",
                    "title": obj.properties.get("title", ""),
                    "content": obj.properties.get("content", "")[:500],
                })

        if any(term in question_lower for term in ["policy", "data governance", "compliance"]):
            collection = self.client.collections.get("PolicyDocument")
            results = collection.query.hybrid(query=question, limit=5, alpha=0.6)
            for obj in results.objects:
                all_results.append({
                    "type": "Policy",
                    "title": obj.properties.get("title", ""),
                    "content": obj.properties.get("content", "")[:500],
                })

        if any(term in question_lower for term in ["vocab", "concept", "definition", "cim", "iec"]):
            collection = self.client.collections.get("Vocabulary")
            results = collection.query.hybrid(query=question, limit=5, alpha=0.6)
            for obj in results.objects:
                all_results.append({
                    "type": "Vocabulary",
                    "label": obj.properties.get("pref_label", ""),
                    "definition": obj.properties.get("definition", ""),
                })

        # If no specific collection matched, search all
        if not all_results:
            for coll_name in ["ArchitecturalDecision", "Principle", "PolicyDocument"]:
                collection = self.client.collections.get(coll_name)
                results = collection.query.hybrid(query=question, limit=3, alpha=0.6)
                for obj in results.objects:
                    all_results.append({
                        "type": coll_name,
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", obj.properties.get("decision", ""))[:300],
                    })

        # Generate response using OpenAI
        openai_client = OpenAI(api_key=settings.openai_api_key)

        context = "\n\n".join([
            f"[{r.get('type', 'Document')}] {r.get('title', r.get('label', 'Untitled'))}: {r.get('content', r.get('definition', ''))}"
            for r in all_results[:10]
        ])

        response = openai_client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant answering questions about architecture decisions, principles, policies, and vocabulary. Base your answers on the provided context."},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
            max_tokens=1000,
        )

        return response.choices[0].message.content, all_results

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
