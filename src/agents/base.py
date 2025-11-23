"""Base agent class for the multi-agent system."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any

from weaviate import WeaviateClient
from weaviate.classes.query import MetadataQuery

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Response from an agent."""

    answer: str
    sources: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    agent_name: str = ""
    raw_results: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "answer": self.answer,
            "sources": self.sources,
            "confidence": self.confidence,
            "agent_name": self.agent_name,
        }


class BaseAgent(ABC):
    """Base class for all agents in the system."""

    name: str = "BaseAgent"
    description: str = "Base agent"
    collection_name: str = ""

    def __init__(self, client: WeaviateClient, llm_client: Optional[Any] = None):
        """Initialize the agent.

        Args:
            client: Connected Weaviate client
            llm_client: Optional LLM client for generation
        """
        self.client = client
        self.llm_client = llm_client

    @abstractmethod
    async def query(self, question: str, **kwargs) -> AgentResponse:
        """Process a query and return a response.

        Args:
            question: The user's question
            **kwargs: Additional parameters

        Returns:
            AgentResponse with the answer
        """
        pass

    def search(
        self,
        query: str,
        limit: int = 5,
        return_properties: Optional[list[str]] = None,
        filters: Optional[Any] = None,
    ) -> list[dict]:
        """Perform a semantic search on the agent's collection.

        Args:
            query: Search query
            limit: Maximum number of results
            return_properties: Properties to return
            filters: Optional Weaviate filters

        Returns:
            List of matching documents
        """
        if not self.collection_name:
            raise ValueError("Collection name not set for this agent")

        collection = self.client.collections.get(self.collection_name)

        # Build query
        query_builder = collection.query.near_text(
            query=query,
            limit=limit,
            return_metadata=MetadataQuery(distance=True, score=True),
        )

        if filters:
            query_builder = query_builder.with_where(filters)

        results = query_builder

        # Convert to list of dicts
        documents = []
        for obj in results.objects:
            doc = dict(obj.properties)
            doc["_distance"] = obj.metadata.distance if obj.metadata else None
            doc["_score"] = obj.metadata.score if obj.metadata else None
            documents.append(doc)

        return documents

    def hybrid_search(
        self,
        query: str,
        limit: int = 5,
        alpha: float = 0.5,
        return_properties: Optional[list[str]] = None,
    ) -> list[dict]:
        """Perform a hybrid search (semantic + keyword) on the collection.

        Args:
            query: Search query
            limit: Maximum number of results
            alpha: Weight between vector (1.0) and keyword (0.0) search
            return_properties: Properties to return

        Returns:
            List of matching documents
        """
        if not self.collection_name:
            raise ValueError("Collection name not set for this agent")

        collection = self.client.collections.get(self.collection_name)

        results = collection.query.hybrid(
            query=query,
            limit=limit,
            alpha=alpha,
            return_metadata=MetadataQuery(score=True),
        )

        # Convert to list of dicts
        documents = []
        for obj in results.objects:
            doc = dict(obj.properties)
            doc["_score"] = obj.metadata.score if obj.metadata else None
            documents.append(doc)

        return documents

    def generate_answer(
        self,
        question: str,
        context: list[dict],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate an answer using the LLM with RAG context.

        Args:
            question: The user's question
            context: Retrieved documents for context
            system_prompt: Optional system prompt

        Returns:
            Generated answer string
        """
        if not self.llm_client:
            # Return a simple concatenation if no LLM available
            return self._format_context_as_answer(context)

        # Build context string
        context_str = self._format_context(context)

        # Use Weaviate's generative search if available
        if not self.collection_name:
            return self._format_context_as_answer(context)

        collection = self.client.collections.get(self.collection_name)

        prompt = f"""Based on the following context, answer the question.

Context:
{context_str}

Question: {question}

Provide a clear, concise answer based only on the information in the context. If the context doesn't contain enough information, say so."""

        try:
            results = collection.generate.near_text(
                query=question,
                limit=len(context) if context else 5,
                single_prompt=prompt,
            )
            if results.generated:
                return results.generated
        except Exception as e:
            logger.warning(f"Generative search failed: {e}")

        return self._format_context_as_answer(context)

    def _format_context(self, context: list[dict]) -> str:
        """Format context documents as a string.

        Args:
            context: List of context documents

        Returns:
            Formatted context string
        """
        parts = []
        for i, doc in enumerate(context, 1):
            title = doc.get("title") or doc.get("pref_label") or f"Document {i}"
            content = doc.get("content") or doc.get("full_text") or doc.get("definition") or ""
            parts.append(f"[{i}] {title}\n{content[:1000]}")
        return "\n\n".join(parts)

    def _format_context_as_answer(self, context: list[dict]) -> str:
        """Format context as a simple answer when no LLM is available.

        Args:
            context: List of context documents

        Returns:
            Formatted answer string
        """
        if not context:
            return "No relevant information found."

        parts = ["Based on the available information:\n"]
        for doc in context[:3]:
            title = doc.get("title") or doc.get("pref_label") or "Document"
            content = doc.get("content") or doc.get("full_text") or doc.get("definition") or ""
            if content:
                parts.append(f"- **{title}**: {content[:500]}...")
        return "\n".join(parts)
