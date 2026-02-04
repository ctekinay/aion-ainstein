"""Agent for querying Architectural Decision Records and principles."""

import logging
from enum import Enum
from typing import Optional, Any

from weaviate import WeaviateClient

from .base import BaseAgent, AgentResponse
from ..weaviate.collections import CollectionManager
from ..config import settings

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    """Types of query intents for the architecture agent."""
    LIST = "list"           # User wants to see all items (e.g., "What ADRs exist?")
    SEARCH = "search"       # User is looking for specific information
    SUMMARY = "summary"     # User wants an overview or summary
    COUNT = "count"         # User wants to know how many items exist


class IntentClassifier:
    """LLM-based intent classifier for query routing.

    Supports both OpenAI and Ollama as LLM backends.
    """

    INTENT_PROMPT = """Classify the user's query into one of these intents:
- LIST: User wants to see all items or enumerate everything (e.g., "What ADRs exist?", "Show me all decisions", "List the principles")
- SEARCH: User is looking for specific information about a topic (e.g., "What decisions were made about security?", "Tell me about CIM")
- SUMMARY: User wants an overview or summary (e.g., "Summarize the architecture decisions", "Give me an overview")
- COUNT: User wants to know how many items exist (e.g., "How many ADRs are there?")

Query: {query}

Respond with only one word: LIST, SEARCH, SUMMARY, or COUNT"""

    def __init__(self):
        """Initialize the intent classifier."""
        self._llm_client = None

    def _get_llm_client(self):
        """Get LLM client based on provider setting."""
        if self._llm_client is not None:
            return self._llm_client

        if settings.llm_provider == "ollama":
            try:
                import httpx
                self._llm_client = ("ollama", httpx.Client(timeout=30.0))
                return self._llm_client
            except ImportError:
                logger.warning("httpx not available for Ollama")
        else:
            try:
                from openai import OpenAI
                self._llm_client = ("openai", OpenAI(api_key=settings.openai_api_key))
                return self._llm_client
            except ImportError:
                logger.warning("OpenAI not available for intent classification")

        return None

    def classify(self, query: str) -> QueryIntent:
        """Classify the intent of a query using LLM.

        Args:
            query: The user's query

        Returns:
            Classified QueryIntent
        """
        client_info = self._get_llm_client()
        if not client_info:
            return QueryIntent.SEARCH

        provider, client = client_info

        try:
            if provider == "ollama":
                # Use Ollama API
                response = client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model": settings.ollama_model,
                        "prompt": self.INTENT_PROMPT.format(query=query),
                        "stream": False,
                        "options": {"temperature": 0, "num_predict": 20},
                    },
                )
                response.raise_for_status()
                result = response.json()
                intent_str = result.get("response", "").strip().upper()
            else:
                # Use OpenAI API
                response = client.chat.completions.create(
                    model=settings.openai_chat_model,
                    messages=[
                        {"role": "user", "content": self.INTENT_PROMPT.format(query=query)}
                    ],
                    max_tokens=10,
                    temperature=0,
                )
                intent_str = response.choices[0].message.content.strip().upper()

            # Map response to intent
            intent_map = {
                "LIST": QueryIntent.LIST,
                "SEARCH": QueryIntent.SEARCH,
                "SUMMARY": QueryIntent.SUMMARY,
                "COUNT": QueryIntent.COUNT,
            }

            # Handle potential extra text in response
            for key in intent_map:
                if key in intent_str:
                    intent = intent_map[key]
                    logger.info(f"Classified intent for '{query[:50]}...' as {intent.value}")
                    return intent

            logger.info(f"Classified intent for '{query[:50]}...' as SEARCH (default)")
            return QueryIntent.SEARCH

        except Exception as e:
            logger.warning(f"Intent classification failed: {e}, defaulting to SEARCH")
            return QueryIntent.SEARCH


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
        self.intent_classifier = IntentClassifier()

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

        # Use LLM to classify the query intent
        intent = self.intent_classifier.classify(question)
        logger.info(f"Query intent: {intent.value}")

        # Route based on intent
        if intent == QueryIntent.LIST:
            return await self._handle_listing_query(question, include_principles)
        elif intent == QueryIntent.COUNT:
            return await self._handle_count_query(question)
        elif intent == QueryIntent.SUMMARY:
            return await self._handle_summary_query(question, include_principles)
        # Default: SEARCH intent

        # Search ADRs
        adr_results = self.hybrid_search(
            query=question,
            limit=limit,
            alpha=settings.alpha_vocabulary,
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
                alpha=settings.alpha_vocabulary,
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
            alpha=settings.alpha_exact_match,  # Favor keyword matching
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
            alpha=settings.alpha_semantic,
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

    def list_all_adrs(self) -> list[dict]:
        """List all ADRs in the collection.

        Returns:
            List of all ADR documents with title, status, and file info
        """
        collection = self.client.collections.get(self.collection_name)

        results = collection.query.fetch_objects(
            limit=100,
            return_properties=["title", "status", "file_path", "context", "decision"],
        )

        adrs = []
        for obj in results.objects:
            props = dict(obj.properties)
            # Skip template files
            title = props.get("title", "")
            file_path = props.get("file_path", "")
            if "template" in title.lower() or "template" in file_path.lower():
                continue
            adrs.append(props)

        return adrs

    def list_all_principles(self) -> list[dict]:
        """List all principles in the collection.

        Returns:
            List of all principle documents
        """
        collection = self.client.collections.get(CollectionManager.PRINCIPLE_COLLECTION)

        results = collection.query.fetch_objects(
            limit=100,
            return_properties=["title", "file_path", "doc_type"],
        )

        return [dict(obj.properties) for obj in results.objects]

    async def _handle_listing_query(self, question: str, include_principles: bool) -> AgentResponse:
        """Handle queries that ask for a list of ADRs or principles.

        Args:
            question: The user's question
            include_principles: Whether to include principles in listing

        Returns:
            AgentResponse with list of documents
        """
        adrs = self.list_all_adrs()
        principles = self.list_all_principles() if include_principles else []

        # Build formatted answer
        answer_parts = []

        if adrs:
            answer_parts.append(f"## Architectural Decision Records ({len(adrs)} ADRs)\n")
            for adr in sorted(adrs, key=lambda x: x.get("file_path", "")):
                title = adr.get("title", "Untitled")
                status = adr.get("status", "unknown")
                file_name = adr.get("file_path", "").split("/")[-1] if adr.get("file_path") else ""
                answer_parts.append(f"- **{title}** [{status}] - {file_name}")
        else:
            answer_parts.append("No ADRs found in the system.")

        if principles and "principle" in question.lower():
            answer_parts.append(f"\n\n## Principles ({len(principles)} documents)\n")
            for p in principles:
                title = p.get("title", "Untitled")
                answer_parts.append(f"- {title}")

        answer = "\n".join(answer_parts)

        # Build sources
        sources = [
            {
                "title": adr.get("title", ""),
                "type": "ADR",
                "status": adr.get("status", ""),
                "file": adr.get("file_path", "").split("/")[-1] if adr.get("file_path") else "",
            }
            for adr in adrs
        ]

        return AgentResponse(
            answer=answer,
            sources=sources,
            confidence=0.95,  # High confidence for listing queries
            agent_name=self.name,
            raw_results=adrs + principles,
        )

    async def _handle_count_query(self, question: str) -> AgentResponse:
        """Handle queries that ask for counts of ADRs or principles.

        Args:
            question: The user's question

        Returns:
            AgentResponse with count information
        """
        adrs = self.list_all_adrs()
        principles = self.list_all_principles()

        # Count by status
        status_counts = {}
        for adr in adrs:
            status = adr.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        answer_parts = [
            f"## Document Counts\n",
            f"- **Total ADRs**: {len(adrs)}",
        ]

        if status_counts:
            answer_parts.append("\n### ADRs by Status:")
            for status, count in sorted(status_counts.items()):
                answer_parts.append(f"  - {status}: {count}")

        answer_parts.append(f"\n- **Total Principles**: {len(principles)}")

        return AgentResponse(
            answer="\n".join(answer_parts),
            sources=[],
            confidence=0.98,
            agent_name=self.name,
            raw_results={"adr_count": len(adrs), "principle_count": len(principles), "status_counts": status_counts},
        )

    async def _handle_summary_query(self, question: str, include_principles: bool) -> AgentResponse:
        """Handle queries that ask for a summary or overview.

        Args:
            question: The user's question
            include_principles: Whether to include principles

        Returns:
            AgentResponse with summary
        """
        # Get all documents for summary
        adrs = self.list_all_adrs()
        principles = self.list_all_principles() if include_principles else []

        # Use LLM to generate a summary
        summary_context = []
        for adr in adrs[:10]:  # Limit to first 10 for context
            summary_context.append({
                "title": adr.get("title", ""),
                "status": adr.get("status", ""),
                "context": adr.get("context", "")[:200],
                "decision": adr.get("decision", "")[:200],
            })

        # Generate summary using Weaviate's generative search
        answer = self.generate_answer(
            f"Provide a high-level summary of the architecture decisions. {question}",
            summary_context
        )

        return AgentResponse(
            answer=answer,
            sources=[{"title": adr.get("title", ""), "type": "ADR"} for adr in adrs[:5]],
            confidence=0.85,
            agent_name=self.name,
            raw_results=adrs + principles,
        )
