"""Agent for querying data governance policies."""

import logging
from typing import Optional, Any

from weaviate import WeaviateClient

from .base import BaseAgent, AgentResponse
from ..weaviate.collections import get_collection_name
from ..config import settings

logger = logging.getLogger(__name__)


class PolicyAgent(BaseAgent):
    """Agent specialized in data governance policies."""

    name = "PolicyAgent"
    description = (
        "Expert in data governance policies and regulations. "
        "Can answer questions about data management, data quality, "
        "metadata governance, classification, and compliance requirements."
    )
    collection_name = get_collection_name("policy")

    def __init__(self, client: WeaviateClient, llm_client: Optional[Any] = None):
        """Initialize the policy agent.

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
        **kwargs,
    ) -> AgentResponse:
        """Query the policy knowledge base.

        Args:
            question: The user's question
            limit: Maximum number of results
            include_principles: Whether to also search governance principles

        Returns:
            AgentResponse with policy information
        """
        logger.info(f"PolicyAgent processing: {question}")

        # Search policies
        policy_results = self.hybrid_search(
            query=question,
            limit=limit,
            alpha=settings.alpha_default,  # Configurable in config.py
        )

        # Optionally search governance principles
        principle_results = []
        if include_principles:
            principle_results = self._search_governance_principles(
                question, limit=limit // 2
            )

        # Combine results
        all_results = policy_results + principle_results

        # Build sources list
        sources = []
        for doc in all_results:
            doc_type = doc.get("doc_type", "policy")
            sources.append({
                "title": doc.get("title", ""),
                "type": doc_type,
                "file_type": doc.get("file_type", ""),
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

    def _search_governance_principles(self, query: str, limit: int = 3) -> list[dict]:
        """Search governance principles from the principles collection.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching principles
        """
        try:
            collection = self.client.collections.get(get_collection_name("principle"))
            results = collection.query.hybrid(
                query=query,
                limit=limit,
                alpha=settings.alpha_default,
            )

            # Filter to governance-related principles
            principles = []
            for obj in results.objects:
                props = dict(obj.properties)
                # Include if it's a governance principle (from do-artifacts)
                file_path = props.get("file_path", "")
                if "do-artifacts" in file_path or "governance" in file_path.lower():
                    principles.append(props)

            return principles
        except Exception as e:
            logger.warning(f"Failed to search governance principles: {e}")
            return []

    def list_policies(self) -> list[dict]:
        """List all available policy documents.

        Returns:
            List of policy summaries
        """
        collection = self.client.collections.get(self.collection_name)

        results = collection.query.fetch_objects(limit=100)

        policies = []
        for obj in results.objects:
            props = dict(obj.properties)
            policies.append({
                "title": props.get("title", ""),
                "file_path": props.get("file_path", ""),
                "file_type": props.get("file_type", ""),
                "page_count": props.get("page_count", 0),
            })

        return policies

    def get_policy_by_topic(self, topic: str) -> Optional[dict]:
        """Find a policy document by topic.

        Args:
            topic: The policy topic (e.g., "data quality", "metadata")

        Returns:
            Policy dictionary or None
        """
        results = self.hybrid_search(
            query=topic,
            limit=3,
            alpha=settings.alpha_default,  # Close to default
        )

        if results:
            return results[0]
        return None

    def search_regulations(self, keyword: str) -> list[dict]:
        """Search for regulatory requirements in policies.

        Args:
            keyword: Keyword to search for

        Returns:
            List of relevant policy sections
        """
        # Combine keyword with regulatory terms
        enhanced_query = f"{keyword} regulation requirement compliance"

        results = self.hybrid_search(
            query=enhanced_query,
            limit=10,
            alpha=settings.alpha_vocabulary,
        )

        return results

    def _calculate_confidence(self, results: list[dict]) -> float:
        """Calculate confidence score based on search results."""
        if not results:
            return 0.0

        scores = [r.get("_score", 0) for r in results[:3] if r.get("_score")]
        if not scores:
            return 0.5

        avg_score = sum(scores) / len(scores)
        return min(max(avg_score, 0.0), 1.0)
