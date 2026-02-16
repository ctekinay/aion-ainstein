"""Agent for querying SKOS/OWL vocabulary concepts."""

import logging
from typing import Optional, Any

from weaviate import WeaviateClient

from .base import BaseAgent, AgentResponse
from ..weaviate.collections import get_collection_name
from ..config import settings

logger = logging.getLogger(__name__)


class VocabularyAgent(BaseAgent):
    """Agent specialized in querying semantic vocabularies (SKOS/OWL)."""

    name = "VocabularyAgent"
    description = (
        "Expert in energy sector vocabularies, ontologies, and semantic concepts. "
        "Can answer questions about IEC standards (61970, 61968, 62325), CIM models, "
        "SKOS concept hierarchies, and domain terminology."
    )
    collection_name = get_collection_name("vocabulary")

    def __init__(self, client: WeaviateClient, llm_client: Optional[Any] = None):
        """Initialize the vocabulary agent.

        Args:
            client: Connected Weaviate client
            llm_client: Optional LLM client for generation
        """
        super().__init__(client, llm_client)

    async def query(
        self,
        question: str,
        limit: int = 10,
        vocabulary_filter: Optional[str] = None,
        **kwargs,
    ) -> AgentResponse:
        """Query the vocabulary knowledge base.

        Args:
            question: The user's question
            limit: Maximum number of results
            vocabulary_filter: Optional filter for specific vocabulary

        Returns:
            AgentResponse with vocabulary information
        """
        logger.info(f"VocabularyAgent processing: {question}")

        # Use hybrid search for better results on terminology
        results = self.hybrid_search(
            query=question,
            limit=limit,
            alpha=settings.alpha_semantic,  # Configurable in config.py
        )

        if vocabulary_filter:
            results = [
                r for r in results
                if r.get("vocabulary_name", "").lower() == vocabulary_filter.lower()
            ]

        # Build sources list
        sources = []
        for doc in results:
            sources.append({
                "uri": doc.get("uri", ""),
                "label": doc.get("pref_label", ""),
                "vocabulary": doc.get("vocabulary_name", ""),
                "definition": doc.get("definition", "")[:200] if doc.get("definition") else "",
            })

        # Generate answer
        answer = self.generate_answer(question, results)

        # Calculate confidence based on search scores
        confidence = self._calculate_confidence(results)

        return AgentResponse(
            answer=answer,
            sources=sources,
            confidence=confidence,
            agent_name=self.name,
            raw_results=results,
        )

    def find_concept(self, label: str) -> Optional[dict]:
        """Find a specific concept by its label.

        Args:
            label: The concept label to find

        Returns:
            Concept dictionary or None
        """
        results = self.hybrid_search(
            query=label,
            limit=5,
            alpha=settings.alpha_exact_match,  # Configurable in config.py
        )

        # Look for exact match
        for doc in results:
            if doc.get("pref_label", "").lower() == label.lower():
                return doc
            if label.lower() in [l.lower() for l in doc.get("alt_labels", [])]:
                return doc

        return results[0] if results else None

    def get_related_concepts(self, uri: str, relationship: str = "all") -> list[dict]:
        """Get concepts related to a given concept.

        Args:
            uri: URI of the concept
            relationship: Type of relationship (broader, narrower, related, all)

        Returns:
            List of related concepts
        """
        collection = self.client.collections.get(self.collection_name)

        # Find the concept
        results = collection.query.fetch_objects(
            filters={"path": ["uri"], "operator": "Equal", "valueText": uri},
            limit=1,
        )

        if not results.objects:
            return []

        concept = dict(results.objects[0].properties)
        related_uris = []

        if relationship in ("broader", "all"):
            related_uris.extend(concept.get("broader", []))
        if relationship in ("narrower", "all"):
            related_uris.extend(concept.get("narrower", []))
        if relationship in ("related", "all"):
            related_uris.extend(concept.get("related", []))

        # Fetch related concepts
        related = []
        for related_uri in related_uris[:20]:  # Limit to prevent too many queries
            rel_results = collection.query.fetch_objects(
                filters={"path": ["uri"], "operator": "Equal", "valueText": related_uri},
                limit=1,
            )
            if rel_results.objects:
                related.append(dict(rel_results.objects[0].properties))

        return related

    def list_vocabularies(self) -> list[str]:
        """List all available vocabularies.

        Returns:
            List of vocabulary names
        """
        collection = self.client.collections.get(self.collection_name)

        # Aggregate by vocabulary_name
        results = collection.aggregate.over_all(
            group_by="vocabulary_name",
            total_count=True,
        )

        vocabularies = []
        for group in results.groups:
            if group.grouped_by and group.grouped_by.value:
                vocabularies.append({
                    "name": group.grouped_by.value,
                    "count": group.total_count,
                })

        return vocabularies

    def _calculate_confidence(self, results: list[dict]) -> float:
        """Calculate confidence score based on search results.

        Args:
            results: Search results

        Returns:
            Confidence score between 0 and 1
        """
        if not results:
            return 0.0

        # Use average of top scores
        scores = [r.get("_score", 0) for r in results[:3] if r.get("_score")]
        if not scores:
            return 0.5

        avg_score = sum(scores) / len(scores)
        # Normalize to 0-1 range (scores are typically 0-1 for hybrid search)
        return min(max(avg_score, 0.0), 1.0)
