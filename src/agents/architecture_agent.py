"""Agent for querying Architectural Decision Records and principles."""

import logging
from typing import Optional, Any

from weaviate import WeaviateClient

from .base import BaseAgent, AgentResponse
from ..weaviate.collections import CollectionManager

logger = logging.getLogger(__name__)


class ArchitectureAgent(BaseAgent):
    """Agent specialized in architecture decisions and principles."""

    name = "ArchitectureAgent"
    description = (
        "Expert in Energy System Architecture decisions and principles. "
        "Can answer questions about architectural patterns, design decisions, "
        "standards adoption, and system design rationale documented in ADRs."
    )
    collection_name = CollectionManager.ADR_COLLECTION

    def __init__(self, client: WeaviateClient, llm_client: Optional[Any] = None):
        """Initialize the architecture agent.

        Args:
            client: Connected Weaviate client
            llm_client: Optional LLM client for generation
        """
        super().__init__(client, llm_client)

    async def query(
        self,
        question: str,
        limit: int = 5,
        include_principles: bool = True,
        status_filter: Optional[str] = None,
        **kwargs,
    ) -> AgentResponse:
        """Query the architecture knowledge base.

        Args:
            question: The user's question
            limit: Maximum number of results
            include_principles: Whether to also search principles
            status_filter: Filter by ADR status (accepted, proposed, deprecated)

        Returns:
            AgentResponse with architecture information
        """
        logger.info(f"ArchitectureAgent processing: {question}")

        # Search ADRs
        adr_results = self.hybrid_search(
            query=question,
            limit=limit,
            alpha=0.6,
        )

        # Apply status filter if provided
        if status_filter:
            adr_results = [
                r for r in adr_results
                if status_filter.lower() in r.get("status", "").lower()
            ]

        # Optionally search principles
        principle_results = []
        if include_principles:
            principle_results = self._search_principles(question, limit=limit // 2)

        # Combine results
        all_results = adr_results + principle_results

        # Build sources list
        sources = []
        for doc in all_results:
            doc_type = "ADR" if doc.get("context") else "Principle"
            sources.append({
                "title": doc.get("title", ""),
                "type": doc_type,
                "status": doc.get("status", ""),
                "file": doc.get("file_path", "").split("/")[-1] if doc.get("file_path") else "",
            })

        # Generate answer
        answer = self.generate_answer(question, all_results)

        # Calculate confidence
        confidence = self._calculate_confidence(all_results)

        return AgentResponse(
            answer=answer,
            sources=sources,
            confidence=confidence,
            agent_name=self.name,
            raw_results=all_results,
        )

    def _search_principles(self, query: str, limit: int = 3) -> list[dict]:
        """Search principles collection.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching principles
        """
        try:
            collection = self.client.collections.get(CollectionManager.PRINCIPLE_COLLECTION)
            results = collection.query.hybrid(
                query=query,
                limit=limit,
                alpha=0.6,
            )
            return [dict(obj.properties) for obj in results.objects]
        except Exception as e:
            logger.warning(f"Failed to search principles: {e}")
            return []

    def find_adr_by_number(self, number: int) -> Optional[dict]:
        """Find an ADR by its number.

        Args:
            number: The ADR number (e.g., 1 for ADR-0001)

        Returns:
            ADR dictionary or None
        """
        # Format the number with leading zeros
        formatted = f"{number:04d}"

        results = self.hybrid_search(
            query=formatted,
            limit=10,
            alpha=0.2,  # Favor keyword matching
        )

        for doc in results:
            file_path = doc.get("file_path", "")
            if formatted in file_path:
                return doc

        return None

    def list_adrs_by_status(self, status: str) -> list[dict]:
        """List all ADRs with a specific status.

        Args:
            status: The status to filter by

        Returns:
            List of matching ADRs
        """
        collection = self.client.collections.get(self.collection_name)

        results = collection.query.fetch_objects(
            filters={"path": ["status"], "operator": "ContainsAny", "valueTextArray": [status]},
            limit=100,
        )

        return [dict(obj.properties) for obj in results.objects]

    def get_decision_summary(self, question: str) -> dict:
        """Get a summary of relevant decisions for a topic.

        Args:
            question: The topic to summarize

        Returns:
            Dictionary with decision summary
        """
        results = self.hybrid_search(
            query=question,
            limit=5,
            alpha=0.7,
        )

        summary = {
            "topic": question,
            "decisions": [],
            "key_points": [],
        }

        for doc in results:
            summary["decisions"].append({
                "title": doc.get("title", ""),
                "decision": doc.get("decision", "")[:300],
                "status": doc.get("status", ""),
            })

            # Extract key points from consequences
            consequences = doc.get("consequences", "")
            if consequences:
                summary["key_points"].append(consequences[:200])

        return summary

    def _calculate_confidence(self, results: list[dict]) -> float:
        """Calculate confidence score based on search results."""
        if not results:
            return 0.0

        scores = [r.get("_score", 0) for r in results[:3] if r.get("_score")]
        if not scores:
            return 0.5

        avg_score = sum(scores) / len(scores)
        return min(max(avg_score, 0.0), 1.0)
