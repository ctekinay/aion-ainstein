"""Orchestrator agent that coordinates between specialized agents."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Any

from weaviate import WeaviateClient

from .base import BaseAgent, AgentResponse
from .vocabulary_agent import VocabularyAgent
from .architecture_agent import ArchitectureAgent
from .policy_agent import PolicyAgent

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResponse:
    """Response from the orchestrator combining multiple agent responses."""

    answer: str
    agent_responses: list[AgentResponse] = field(default_factory=list)
    routing_decision: dict = field(default_factory=dict)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "answer": self.answer,
            "routing_decision": self.routing_decision,
            "confidence": self.confidence,
            "agent_responses": [r.to_dict() for r in self.agent_responses],
        }


class OrchestratorAgent:
    """Orchestrator that routes queries to appropriate specialized agents."""

    name = "OrchestratorAgent"
    description = (
        "Coordinates between specialized agents to answer complex questions "
        "about energy system architecture, vocabularies, and governance."
    )

    # Keywords for routing
    VOCABULARY_KEYWORDS = [
        "concept", "term", "definition", "vocabulary", "ontology", "skos",
        "iec", "cim", "standard", "meaning", "semantic", "taxonomy",
        "class", "property", "owl", "rdf", "uri", "61970", "61968", "62325",
    ]

    ARCHITECTURE_KEYWORDS = [
        "decision", "adr", "architecture", "design", "pattern", "principle",
        "rationale", "consequence", "tradeoff", "approach", "why", "how",
        "system", "component", "integration", "api", "protocol", "oauth",
        "tls", "security", "communication",
    ]

    POLICY_KEYWORDS = [
        "policy", "governance", "compliance", "regulation", "data quality",
        "metadata", "classification", "privacy", "security", "access",
        "management", "lifecycle", "retention", "biv", "asset", "ownership",
    ]

    def __init__(self, client: WeaviateClient, llm_client: Optional[Any] = None):
        """Initialize the orchestrator with all specialized agents.

        Args:
            client: Connected Weaviate client
            llm_client: Optional LLM client for generation
        """
        self.client = client
        self.llm_client = llm_client

        # Initialize specialized agents
        self.vocabulary_agent = VocabularyAgent(client, llm_client)
        self.architecture_agent = ArchitectureAgent(client, llm_client)
        self.policy_agent = PolicyAgent(client, llm_client)

        self.agents = {
            "vocabulary": self.vocabulary_agent,
            "architecture": self.architecture_agent,
            "policy": self.policy_agent,
        }

    async def query(
        self,
        question: str,
        use_all_agents: bool = False,
        agent_names: Optional[list[str]] = None,
        **kwargs,
    ) -> OrchestratorResponse:
        """Process a query by routing to appropriate agents.

        Args:
            question: The user's question
            use_all_agents: If True, query all agents and combine results
            agent_names: Specific agents to use (overrides routing)
            **kwargs: Additional parameters passed to agents

        Returns:
            OrchestratorResponse with combined answers
        """
        logger.info(f"Orchestrator processing: {question}")

        # Determine which agents to use
        if agent_names:
            selected_agents = [
                self.agents[name] for name in agent_names if name in self.agents
            ]
            routing_reason = "explicitly specified"
        elif use_all_agents:
            selected_agents = list(self.agents.values())
            routing_reason = "all agents requested"
        else:
            selected_agents, routing_reason = self._route_query(question)

        routing_decision = {
            "agents": [a.name for a in selected_agents],
            "reason": routing_reason,
        }

        logger.info(f"Routing to agents: {[a.name for a in selected_agents]}")

        # Query selected agents in parallel
        agent_responses = await self._query_agents(selected_agents, question, **kwargs)

        # Combine responses
        combined_answer = self._combine_responses(question, agent_responses)

        # Calculate overall confidence
        confidence = self._calculate_overall_confidence(agent_responses)

        return OrchestratorResponse(
            answer=combined_answer,
            agent_responses=agent_responses,
            routing_decision=routing_decision,
            confidence=confidence,
        )

    def _route_query(self, question: str) -> tuple[list[BaseAgent], str]:
        """Route a query to the most appropriate agents.

        Args:
            question: The user's question

        Returns:
            Tuple of (selected agents, routing reason)
        """
        question_lower = question.lower()

        # Score each agent type
        scores = {
            "vocabulary": sum(
                1 for kw in self.VOCABULARY_KEYWORDS if kw in question_lower
            ),
            "architecture": sum(
                1 for kw in self.ARCHITECTURE_KEYWORDS if kw in question_lower
            ),
            "policy": sum(
                1 for kw in self.POLICY_KEYWORDS if kw in question_lower
            ),
        }

        # Get agents with non-zero scores, sorted by score
        scored_agents = sorted(
            [(name, score) for name, score in scores.items() if score > 0],
            key=lambda x: x[1],
            reverse=True,
        )

        if not scored_agents:
            # Default to all agents for general questions
            return (
                list(self.agents.values()),
                "no specific keywords matched, using all agents",
            )

        # Select top-scoring agents (up to 2)
        selected_names = [name for name, _ in scored_agents[:2]]
        selected_agents = [self.agents[name] for name in selected_names]

        reason = f"keyword matching: {', '.join(f'{n}({s})' for n, s in scored_agents[:2])}"
        return selected_agents, reason

    async def _query_agents(
        self,
        agents: list[BaseAgent],
        question: str,
        **kwargs,
    ) -> list[AgentResponse]:
        """Query multiple agents in parallel.

        Args:
            agents: List of agents to query
            question: The question to ask
            **kwargs: Additional parameters

        Returns:
            List of agent responses
        """
        tasks = [agent.query(question, **kwargs) for agent in agents]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        valid_responses = []
        for response in responses:
            if isinstance(response, Exception):
                logger.error(f"Agent query failed: {response}")
            else:
                valid_responses.append(response)

        return valid_responses

    def _combine_responses(
        self,
        question: str,
        responses: list[AgentResponse],
    ) -> str:
        """Combine multiple agent responses into a coherent answer.

        Args:
            question: Original question
            responses: List of agent responses

        Returns:
            Combined answer string
        """
        if not responses:
            return "I couldn't find relevant information to answer your question."

        if len(responses) == 1:
            return responses[0].answer

        # Combine answers from multiple agents
        parts = []

        for response in responses:
            if response.answer and response.answer.strip():
                parts.append(f"**{response.agent_name}**:\n{response.answer}")

        if not parts:
            return "I found some related information but couldn't formulate a complete answer."

        combined = "\n\n---\n\n".join(parts)

        # Add a synthesis if we have multiple responses
        if len(parts) > 1:
            synthesis = (
                "\n\n**Summary**: The above information comes from multiple knowledge domains "
                f"({', '.join(r.agent_name for r in responses)}). "
                "Consider the context of each source when applying this information."
            )
            combined += synthesis

        return combined

    def _calculate_overall_confidence(self, responses: list[AgentResponse]) -> float:
        """Calculate overall confidence from agent responses.

        Args:
            responses: List of agent responses

        Returns:
            Overall confidence score
        """
        if not responses:
            return 0.0

        # Use weighted average based on individual confidences
        confidences = [r.confidence for r in responses if r.confidence > 0]
        if not confidences:
            return 0.5

        return sum(confidences) / len(confidences)

    async def search_all(self, query: str, limit: int = 5) -> dict:
        """Search across all knowledge bases.

        Args:
            query: Search query
            limit: Maximum results per collection

        Returns:
            Dictionary with results from each agent
        """
        results = {}

        for name, agent in self.agents.items():
            try:
                search_results = agent.hybrid_search(query, limit=limit)
                results[name] = search_results
            except Exception as e:
                logger.error(f"Search failed for {name}: {e}")
                results[name] = []

        return results

    def get_agent_info(self) -> list[dict]:
        """Get information about all available agents.

        Returns:
            List of agent info dictionaries
        """
        return [
            {
                "name": agent.name,
                "description": agent.description,
                "collection": agent.collection_name,
            }
            for agent in self.agents.values()
        ]
