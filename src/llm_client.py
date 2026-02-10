"""Vendor-agnostic LLM client abstraction for AION-AINSTEIN.

This module provides:
- LLMClientProtocol: Abstract interface for any LLM backend
- ElysiaClient: Concrete implementation wrapping Elysia Tree
- DirectLLMClient: Fallback implementation using direct LLM calls

Architecture:
    The abstraction allows swapping LLM backends without changing consuming code.
    All clients implement the same query() interface and return standardized results.

    UI/CLI → LLMClientProtocol.query() → (response, objects, metadata)
                    ↓
    ┌───────────────┼───────────────┐
    │               │               │
    ElysiaClient  DirectLLMClient  FutureClient
    (Elysia Tree)  (OpenAI/Ollama)  (...)

Concurrency:
    Elysia Tree calls are blocking. To prevent event loop starvation under load,
    all Tree invocations are wrapped with asyncio.to_thread() and guarded by a
    semaphore to limit concurrent calls.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from weaviate import WeaviateClient

from .weaviate.collections import get_all_collection_names

# =============================================================================
# Concurrency Control
# =============================================================================

# Module-level semaphore for Elysia call concurrency control
_elysia_semaphore: asyncio.Semaphore | None = None
_elysia_semaphore_size: int | None = None


def _get_elysia_semaphore() -> asyncio.Semaphore:
    """Get or create the Elysia concurrency semaphore.

    Lazily initialized to work with any event loop.
    Uses settings.max_concurrent_elysia_calls for the limit.
    """
    global _elysia_semaphore, _elysia_semaphore_size
    from .config import settings

    # Reinitialize if settings changed (for testing/reconfiguration)
    if (_elysia_semaphore is None or
            _elysia_semaphore_size != settings.max_concurrent_elysia_calls):
        _elysia_semaphore = asyncio.Semaphore(settings.max_concurrent_elysia_calls)
        _elysia_semaphore_size = settings.max_concurrent_elysia_calls
    return _elysia_semaphore

logger = logging.getLogger(__name__)


# =============================================================================
# Query Result Types
# =============================================================================

@dataclass
class QueryMetadata:
    """Metadata from query execution for observability."""
    client_type: str
    iterations: int = 0
    recursion_limit: int = 0
    hit_limit: bool = False
    fallback_used: bool = False
    structured_mode: bool = False
    skills_applied: list[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/API responses."""
        return {
            "client_type": self.client_type,
            "iterations": self.iterations,
            "recursion_limit": self.recursion_limit,
            "hit_limit": self.hit_limit,
            "fallback_used": self.fallback_used,
            "structured_mode": self.structured_mode,
            "skills_applied": self.skills_applied,
            "error": self.error,
        }


@dataclass
class QueryResult:
    """Standardized result from LLM query execution."""
    response: str
    objects: list[dict]
    metadata: QueryMetadata

    @property
    def success(self) -> bool:
        """Check if query completed without errors."""
        return self.metadata.error is None


# =============================================================================
# LLM Client Protocol (Abstract Interface)
# =============================================================================

@runtime_checkable
class LLMClientProtocol(Protocol):
    """Protocol defining the interface for LLM clients.

    Any LLM backend (Elysia, direct OpenAI, Ollama, etc.) must implement
    this interface to be usable by the AION-AINSTEIN system.
    """

    async def query(
        self,
        question: str,
        collection_names: Optional[list[str]] = None,
    ) -> QueryResult:
        """Process a query and return structured results.

        Args:
            question: The user's question
            collection_names: Optional list of collections to search

        Returns:
            QueryResult with response, objects, and metadata
        """
        ...

    def get_client_type(self) -> str:
        """Return identifier for this client type."""
        ...

    def is_available(self) -> bool:
        """Check if this client is available and properly configured."""
        ...


# =============================================================================
# Base Client Implementation
# =============================================================================

class BaseLLMClient(ABC):
    """Base class for LLM client implementations.

    Provides common functionality like Weaviate client management
    and skill registry access.
    """

    def __init__(self, weaviate_client: WeaviateClient):
        """Initialize with Weaviate client.

        Args:
            weaviate_client: Connected Weaviate client for retrieval
        """
        self.weaviate_client = weaviate_client
        self._skill_registry = None

    @property
    def skill_registry(self):
        """Lazy-load skill registry."""
        if self._skill_registry is None:
            from .skills import get_skill_registry
            self._skill_registry = get_skill_registry()
        return self._skill_registry

    def get_default_collections(self) -> list[str]:
        """Return default collection names for queries."""
        return get_all_collection_names()

    def is_structured_mode(self, question: str) -> bool:
        """Check if structured response mode is active for this question."""
        return self.skill_registry.is_skill_active("response-contract", question)

    def get_active_skills(self, question: str) -> list[str]:
        """Get list of skills active for this question."""
        active = []
        for entry in self.skill_registry.list_skills():
            # list_skills returns SkillRegistryEntry dataclass objects
            skill_name = entry.name
            if self.skill_registry.is_skill_active(skill_name, question):
                active.append(skill_name)
        return active

    @abstractmethod
    async def query(
        self,
        question: str,
        collection_names: Optional[list[str]] = None,
    ) -> QueryResult:
        """Process a query - must be implemented by subclasses."""
        pass

    @abstractmethod
    def get_client_type(self) -> str:
        """Return client type identifier."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if client is available."""
        pass


# =============================================================================
# Elysia Client Implementation
# =============================================================================

# Check Elysia availability at module load
try:
    from elysia import Tree, tool
    ELYSIA_AVAILABLE = True
except ImportError:
    ELYSIA_AVAILABLE = False
    Tree = None
    tool = None


class ElysiaClient(BaseLLMClient):
    """LLM client implementation using Elysia decision tree.

    Wraps the Elysia Tree for agentic RAG with tool selection.
    This is the primary client for production use.

    Thread Safety:
        This client creates a new Tree instance per request to avoid
        race conditions when mutating agent descriptions. The base
        description and tool registry are shared (read-only after init).
    """

    def __init__(self, weaviate_client: WeaviateClient):
        """Initialize Elysia client.

        Args:
            weaviate_client: Connected Weaviate client

        Raises:
            ImportError: If elysia-ai package is not installed
        """
        super().__init__(weaviate_client)

        if not ELYSIA_AVAILABLE:
            raise ImportError(
                "elysia-ai package is required for ElysiaClient. "
                "Run: pip install elysia-ai"
            )

        self._base_description = self._get_base_description()
        self._tool_registry: dict[str, callable] = {}
        self._recursion_limit = 2

    def _get_base_description(self) -> str:
        """Get base agent description."""
        return """You are AInstein, the Energy System Architecture AI Assistant at Alliander.

Your role is to help architects, engineers, and stakeholders navigate Alliander's energy system architecture knowledge base, including:
- Architectural Decision Records (ADRs)
- Data governance principles and policies
- IEC/CIM vocabulary and standards

IMPORTANT GUIDELINES:
- When referencing ADRs, use the format ADR.XX (e.g., ADR.21)
- When referencing Principles, use the format PCP.XX (e.g., PCP.10)
- For technical terms, provide clear explanations
- Be transparent about the data: always indicate how many items exist vs. how many are shown
- Never hallucinate - if you're not confident, say so"""

    def _create_tree(self, agent_description: str) -> "Tree":
        """Create and configure a new Elysia Tree instance.

        Creates a fresh tree per request to avoid race conditions
        when modifying agent descriptions in concurrent scenarios.

        Args:
            agent_description: Full agent description including skill content

        Returns:
            Configured Tree instance
        """
        tree = Tree(
            agent_description=agent_description,
            style="Professional, concise, and informative. Use structured formatting for lists.",
            end_goal="Provide accurate, well-sourced answers based on the knowledge base.",
        )
        # Limit recursion to prevent infinite loops
        tree.tree_data.recursion_limit = self._recursion_limit

        # Register tools with this tree instance
        for name, func in self._tool_registry.items():
            tool(tree=tree)(func)
            logger.debug(f"Registered tool on tree: {name}")

        return tree

    def register_tools(self, tool_registry: dict[str, callable]) -> None:
        """Register tools to be applied to all tree instances.

        Args:
            tool_registry: Dict mapping tool names to tool functions
        """
        self._tool_registry.update(tool_registry)
        logger.info(f"Registered {len(tool_registry)} tools for future tree instances")

    def get_client_type(self) -> str:
        """Return client type identifier."""
        return "elysia"

    def is_available(self) -> bool:
        """Check if Elysia is available and configured."""
        return ELYSIA_AVAILABLE

    async def query(
        self,
        question: str,
        collection_names: Optional[list[str]] = None,
    ) -> QueryResult:
        """Process query using Elysia decision tree.

        Creates a fresh Tree instance per request to ensure thread safety
        when processing concurrent requests.

        Args:
            question: The user's question
            collection_names: Optional collections to search

        Returns:
            QueryResult with response, objects, and metadata
        """
        from .elysia_agents import postprocess_llm_output, DEFAULT_ENFORCEMENT_POLICY
        from .response_gateway import RETRY_PROMPT

        logger.info(f"ElysiaClient processing: {question[:50]}...")

        # Determine mode and skills
        structured_mode = self.is_structured_mode(question)
        active_skills = self.get_active_skills(question)
        collections = collection_names or self.get_default_collections()

        # Build agent description with injected skills
        skill_content = self.skill_registry.get_all_skill_content(question)
        if skill_content:
            agent_description = f"{self._base_description}\n\n{skill_content}"
        else:
            agent_description = self._base_description

        # Create per-request tree instance (thread-safe: no shared mutable state)
        request_tree = self._create_tree(agent_description)

        # Execute query
        metadata = QueryMetadata(
            client_type=self.get_client_type(),
            structured_mode=structured_mode,
            skills_applied=active_skills,
            recursion_limit=self._recursion_limit,
        )

        # Capture tree and collections for retry closure
        def create_retry_func(tree: "Tree", cols: list[str]) -> callable:
            """Create a retry function that re-asks the tree with strict JSON instructions.

            The retry function is called by the response gateway when strict mode
            fails to extract/validate JSON. It sends RETRY_PROMPT to get a
            properly formatted response.
            """
            def retry_func(retry_prompt: str) -> str:
                logger.info("Executing retry with JSON-only instruction")
                retry_response, _ = tree(retry_prompt, collection_names=cols)
                return retry_response
            return retry_func

        retry_func = create_retry_func(request_tree, collections) if structured_mode else None

        try:
            # Use semaphore to limit concurrent Elysia calls (prevents thread explosion)
            # Use asyncio.to_thread to offload blocking Tree call (prevents event loop blocking)
            # Use wait_for to add timeout and enable cancellation
            from .config import settings

            semaphore = _get_elysia_semaphore()
            async with semaphore:
                response, objects = await asyncio.wait_for(
                    asyncio.to_thread(
                        request_tree, question, collection_names=collections
                    ),
                    timeout=settings.elysia_query_timeout_seconds
                )

                # Capture iteration stats (must be done after call completes)
                iterations = request_tree.tree_data.num_trees_completed
                metadata.iterations = iterations
                metadata.hit_limit = iterations >= metadata.recursion_limit

            if metadata.hit_limit:
                logger.warning(
                    f"Elysia tree hit recursion limit "
                    f"({iterations}/{metadata.recursion_limit})"
                )

        except asyncio.TimeoutError:
            logger.warning(
                f"Elysia tree timed out after {settings.elysia_query_timeout_seconds}s"
            )
            metadata.error = "Query timed out"
            metadata.fallback_used = True

            return QueryResult(
                response="",
                objects=[],
                metadata=metadata,
            )

        except Exception as e:
            logger.warning(f"Elysia tree failed: {e}")
            metadata.error = str(e)
            metadata.fallback_used = True

            # Return error result - caller should handle fallback
            return QueryResult(
                response="",
                objects=[],
                metadata=metadata,
            )

        # Post-process through contract enforcement with retry support
        processed, was_structured, reason = postprocess_llm_output(
            raw_response=response,
            structured_mode=structured_mode,
            enforcement_policy=DEFAULT_ENFORCEMENT_POLICY,
            retry_func=retry_func,
        )

        logger.info(
            f"ElysiaClient complete: structured={was_structured}, reason={reason}"
        )

        return QueryResult(
            response=processed,
            objects=objects if isinstance(objects, list) else [],
            metadata=metadata,
        )


# =============================================================================
# Direct LLM Client (Fallback Implementation)
# =============================================================================

class DirectLLMClient(BaseLLMClient):
    """Fallback LLM client using direct API calls.

    Used when Elysia is unavailable or fails. Performs direct
    Weaviate hybrid search + LLM generation.
    """

    def __init__(self, weaviate_client: WeaviateClient):
        """Initialize direct LLM client."""
        super().__init__(weaviate_client)

    def get_client_type(self) -> str:
        """Return client type identifier."""
        return "direct"

    def is_available(self) -> bool:
        """Direct client is always available if Weaviate is connected."""
        return self.weaviate_client is not None

    async def query(
        self,
        question: str,
        collection_names: Optional[list[str]] = None,
    ) -> QueryResult:
        """Process query using direct Weaviate search + LLM.

        This delegates to the existing _direct_query implementation
        in elysia_agents.py for now.
        """
        from .elysia_agents import ElysiaRAGSystem

        logger.info(f"DirectLLMClient processing: {question[:50]}...")

        metadata = QueryMetadata(
            client_type=self.get_client_type(),
            structured_mode=self.is_structured_mode(question),
            skills_applied=self.get_active_skills(question),
            fallback_used=True,  # This IS the fallback
        )

        try:
            # Use existing direct query implementation
            # This is a temporary bridge until we refactor _direct_query
            rag_system = ElysiaRAGSystem(self.weaviate_client)
            response, objects = await rag_system._direct_query(
                question,
                structured_mode=metadata.structured_mode,
            )

            return QueryResult(
                response=response,
                objects=objects,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"DirectLLMClient failed: {e}")
            metadata.error = str(e)

            return QueryResult(
                response=f"I encountered an error processing your query: {e}",
                objects=[],
                metadata=metadata,
            )


# =============================================================================
# Client Factory
# =============================================================================

def create_llm_client(
    weaviate_client: WeaviateClient,
    prefer_elysia: bool = True,
) -> BaseLLMClient:
    """Factory function to create appropriate LLM client.

    Args:
        weaviate_client: Connected Weaviate client
        prefer_elysia: If True, use Elysia when available

    Returns:
        LLM client instance (ElysiaClient or DirectLLMClient)
    """
    if prefer_elysia and ELYSIA_AVAILABLE:
        try:
            client = ElysiaClient(weaviate_client)
            logger.info("Created ElysiaClient")
            return client
        except Exception as e:
            logger.warning(f"Failed to create ElysiaClient: {e}")

    client = DirectLLMClient(weaviate_client)
    logger.info("Created DirectLLMClient (fallback)")
    return client


# =============================================================================
# Async Client Wrapper with Fallback
# =============================================================================

class ResilientLLMClient:
    """Wrapper that provides automatic fallback between clients.

    Tries primary client first, falls back to secondary on failure.
    """

    def __init__(
        self,
        primary: BaseLLMClient,
        fallback: Optional[BaseLLMClient] = None,
    ):
        """Initialize with primary and optional fallback client.

        Args:
            primary: Primary LLM client to use
            fallback: Optional fallback client if primary fails
        """
        self.primary = primary
        self.fallback = fallback

    async def query(
        self,
        question: str,
        collection_names: Optional[list[str]] = None,
    ) -> QueryResult:
        """Query with automatic fallback on failure.

        Args:
            question: The user's question
            collection_names: Optional collections to search

        Returns:
            QueryResult from primary or fallback client
        """
        # Try primary
        result = await self.primary.query(question, collection_names)

        # If primary succeeded or no fallback, return result
        if result.success or self.fallback is None:
            return result

        # Try fallback
        logger.info(
            f"Primary client ({self.primary.get_client_type()}) failed, "
            f"trying fallback ({self.fallback.get_client_type()})"
        )

        fallback_result = await self.fallback.query(question, collection_names)
        fallback_result.metadata.fallback_used = True

        return fallback_result
