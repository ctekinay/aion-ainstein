"""Elysia-based agentic RAG system for AION-AINSTEIN.

Uses Weaviate's Elysia framework for decision tree-based tool selection
and agentic query processing.

Concurrency:
    Elysia Tree calls are blocking. To prevent event loop starvation under load,
    all Tree invocations are wrapped with asyncio.to_thread() and guarded by a
    semaphore to limit concurrent calls.
"""

import asyncio
import logging
from typing import Optional, Any

import re

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
from weaviate import WeaviateClient
from weaviate.classes.query import Filter, MetadataQuery

from .config import settings
from .skills import SkillRegistry, get_skill_registry, DEFAULT_SKILL
from .skills.filters import build_document_filter
from .weaviate.embeddings import embed_text
from .response_schema import (
    ResponseParser,
    ResponseValidator,
    StructuredResponse,
    RESPONSE_SCHEMA_INSTRUCTIONS,
)

# Initialize skill registry (use singleton to share state across modules)
_skill_registry = get_skill_registry()

# Default abstention thresholds (overridden by skills if available)
_DEFAULT_DISTANCE_THRESHOLD = 0.5
_DEFAULT_MIN_QUERY_COVERAGE = 0.2


def _get_abstention_thresholds() -> tuple[float, float]:
    """Get abstention thresholds from skill configuration.

    Returns:
        Tuple of (distance_threshold, min_query_coverage)
    """
    try:
        return _skill_registry.loader.get_abstention_thresholds(DEFAULT_SKILL)
    except Exception:
        return _DEFAULT_DISTANCE_THRESHOLD, _DEFAULT_MIN_QUERY_COVERAGE


def _get_list_query_config() -> dict:
    """Get list query detection config from skill configuration.

    Returns:
        Dictionary with list_indicators, list_patterns, additional_stop_words
    """
    try:
        return _skill_registry.loader.get_list_query_config(DEFAULT_SKILL)
    except Exception:
        return {
            "list_indicators": ["list", "show", "all", "exist", "exists", "available", "have", "many", "which", "enumerate"],
            "list_patterns": [
                r"what\s+\w+s\s+(are|exist|do we have)",
                r"(list|show|give)\s+(me\s+)?(all|the)",
                r"how many\s+\w+",
                r"which\s+\w+s?\s+(are|exist|do)",
            ],
            "additional_stop_words": ["are", "there", "exist", "exists", "list", "show", "all", "me", "give"],
        }


# Cache for compiled regex patterns (performance optimization)
_compiled_list_patterns: list | None = None


def _get_compiled_list_patterns() -> list:
    """Get cached compiled regex patterns for list query detection."""
    global _compiled_list_patterns
    if _compiled_list_patterns is None:
        list_config = _get_list_query_config()
        patterns = list_config.get("list_patterns", [])
        _compiled_list_patterns = [re.compile(p) for p in patterns]
    return _compiled_list_patterns


def is_list_query(question: str) -> bool:
    """Detect if the query is asking for a comprehensive listing/catalog.

    List queries ask "what exists" rather than asking about specific content.
    For these queries, we should fetch all matching documents and be transparent
    about the total count.

    Args:
        question: The user's question

    Returns:
        True if this is a list/catalog query, False for semantic/specific queries
    """
    list_config = _get_list_query_config()
    list_indicators = set(list_config.get("list_indicators", []))

    question_lower = question.lower()
    query_words = set(question_lower.split())

    # Check keyword indicators
    if query_words & list_indicators:
        return True

    # Check regex patterns like "What ADRs..." or "What principles..."
    # Uses cached compiled patterns for performance
    for pattern in _get_compiled_list_patterns():
        if pattern.search(question_lower):
            return True

    return False


# =============================================================================
# Structured Response Post-Processing
# =============================================================================

# Enforcement policies for structured mode
ENFORCEMENT_STRICT = "strict"   # Retry once with JSON-only prompt, then fail
ENFORCEMENT_SOFT = "soft"       # Log and degrade to raw text

# Default enforcement policy (can be configured)
DEFAULT_ENFORCEMENT_POLICY = ENFORCEMENT_STRICT


def postprocess_llm_output(
    raw_response: str,
    structured_mode: bool,
    enforcement_policy: str = DEFAULT_ENFORCEMENT_POLICY,
    retry_func: callable = None,
) -> tuple[str, bool, str]:
    """Unified post-processing for LLM output with structured mode enforcement.

    This function MUST be called on ALL LLM outputs (main path and fallback path)
    to ensure consistent contract enforcement.

    In strict mode, if parsing fails and retry_func is provided, this function
    will attempt ONE retry with a JSON-only instruction before failing.

    Args:
        raw_response: The raw LLM response text
        structured_mode: Whether response-contract skill is active
        enforcement_policy: "strict" (retry + fail) or "soft" (degrade gracefully)
        retry_func: Optional function to call for retry. Receives RETRY_PROMPT
                    as input and should return the LLM's retry response.

    Returns:
        Tuple of:
        - processed_response: The final response text to display
        - was_structured: Whether structured parsing succeeded
        - reason: Reason code for debugging ("success", "fallback", "parse_failed", etc.)
    """
    from .response_gateway import RETRY_PROMPT

    logger = logging.getLogger(__name__)

    if not structured_mode:
        # Not in structured mode - return raw response as-is
        return raw_response, False, "not_structured_mode"

    # Attempt to parse structured response
    structured, fallback_used = ResponseParser.parse_with_fallbacks(raw_response)

    if structured:
        # Success! Generate processed response with transparency
        logger.info(f"Structured response parsed successfully via {fallback_used}")
        transparency = structured.generate_transparency_message()
        if transparency and transparency not in structured.answer:
            processed = f"{structured.answer}\n\n{transparency}"
        else:
            processed = structured.answer
        return processed, True, "success"

    # Parsing failed
    logger.warning(f"Structured response parsing failed: {fallback_used}")

    if enforcement_policy == ENFORCEMENT_SOFT:
        # Soft mode: log and degrade to raw text
        logger.info("Soft enforcement: degrading to raw response")
        return raw_response, False, f"soft_fallback:{fallback_used}"

    # Strict mode: attempt retry if retry_func is provided
    if retry_func is not None:
        logger.info("Strict enforcement: attempting retry with JSON-only instruction")
        try:
            # Call retry_func with the JSON-only prompt
            retry_response = retry_func(RETRY_PROMPT)

            # Attempt to parse the retry response
            retry_structured, retry_fallback = ResponseParser.parse_with_fallbacks(retry_response)

            if retry_structured:
                # Retry succeeded!
                logger.info(f"Retry succeeded via {retry_fallback}")
                transparency = retry_structured.generate_transparency_message()
                if transparency and transparency not in retry_structured.answer:
                    processed = f"{retry_structured.answer}\n\n{transparency}"
                else:
                    processed = retry_structured.answer
                return processed, True, f"retry_success:{retry_fallback}"

            # Retry parsing also failed
            logger.warning(f"Retry parsing failed: {retry_fallback}")

        except Exception as e:
            logger.error(f"Retry function raised exception: {e}")

    # Strict mode without successful retry: return controlled error message
    error_response = (
        "I was unable to format my response properly. "
        "Please try rephrasing your question."
    )
    logger.error(f"Strict enforcement failed: {fallback_used}")
    return error_response, False, f"strict_failed:{fallback_used}"


def get_collection_count(collection, content_filter=None) -> int:
    """Get the total count of documents in a collection, optionally filtered.

    Args:
        collection: Weaviate collection object
        content_filter: Optional filter to apply

    Returns:
        Total count of matching documents
    """
    try:
        aggregate = collection.aggregate.over_all(
            total_count=True,
            filters=content_filter
        )
        return aggregate.total_count
    except Exception as e:
        logger.warning(f"Failed to get collection count: {e}")
        return 0


def should_abstain(query: str, results: list) -> tuple[bool, str]:
    """Determine if the system should abstain from answering.

    Checks retrieval quality signals to prevent hallucination when
    no relevant documents are found. Thresholds are loaded from
    skill configuration.

    Args:
        query: The user's question
        results: List of retrieved documents with distance/score metadata

    Returns:
        Tuple of (should_abstain: bool, reason: str)
    """
    # Load thresholds from skill configuration
    distance_threshold, min_query_coverage = _get_abstention_thresholds()

    # No results at all
    if not results:
        return True, "No relevant documents found in the knowledge base."

    # Check if any result has acceptable distance
    distances = [r.get("distance") for r in results if r.get("distance") is not None]
    if distances:
        min_distance = min(distances)
        if min_distance > distance_threshold:
            return True, f"No sufficiently relevant documents found (best match distance: {min_distance:.2f})."

    # Check for specific ADR queries - must find the exact ADR
    adr_match = re.search(r'adr[- ]?0*(\d+)', query.lower())
    if adr_match:
        adr_num = adr_match.group(1).zfill(4)
        adr_found = any(
            f"adr-{adr_num}" in str(r.get("title", "")).lower() or
            f"adr-{adr_num}" in str(r.get("content", "")).lower()
            for r in results
        )
        if not adr_found:
            return True, f"ADR-{adr_num} was not found in the knowledge base."

    # Load list query detection config from skill
    list_config = _get_list_query_config()
    list_indicators = set(list_config.get("list_indicators", []))
    list_patterns = list_config.get("list_patterns", [])
    additional_stop_words = set(list_config.get("additional_stop_words", []))

    # Detect LIST-type queries (asking for enumeration/listing)
    # These queries ask "what exists" rather than asking about specific content
    query_lower = query.lower()
    query_words = set(query_lower.split())
    is_list_query = bool(query_words & list_indicators)

    # Also detect patterns like "What ADRs..." or "What principles..."
    if not is_list_query:
        is_list_query = any(re.search(p, query_lower) for p in list_patterns)

    # For LIST queries with good distance scores, skip coverage check
    # The query terms won't appear in documents (e.g., "exist" won't be in ADR titles)
    if is_list_query and distances and min(distances) <= distance_threshold:
        return False, "OK"

    # Check query term coverage in results
    # Extract meaningful terms (skip common words, clean punctuation)
    base_stop_words = {"what", "is", "the", "a", "an", "of", "in", "to", "for", "and", "or", "how", "does", "do", "about", "our"}
    stop_words = base_stop_words | additional_stop_words
    # Clean punctuation from terms
    query_terms = [re.sub(r'[^\w]', '', t) for t in query_lower.split()]
    query_terms = [t for t in query_terms if t not in stop_words and len(t) > 2]

    if query_terms:
        results_text = " ".join(
            str(r.get("title", "")) + " " + str(r.get("content", "")) + " " +
            str(r.get("label", "")) + " " + str(r.get("definition", ""))
            for r in results
        ).lower()

        terms_found = sum(1 for t in query_terms if t in results_text)
        coverage = terms_found / len(query_terms) if query_terms else 0

        if coverage < min_query_coverage:
            return True, f"Query terms not well covered by retrieved documents (coverage: {coverage:.0%})."

    return False, "OK"


def get_abstention_response(reason: str) -> str:
    """Generate a helpful abstention response.

    Args:
        reason: The reason for abstaining

    Returns:
        User-friendly abstention message
    """
    return f"""I don't have sufficient information to answer this question.

**Reason:** {reason}

**Suggestions:**
- Try rephrasing your question with different terms
- Check if the topic exists in our knowledge base
- For terminology questions, verify the term exists in SKOSMOS

If you believe this information should be available, please contact the ESA team to have it added to the knowledge base."""


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
    """Elysia-based agentic RAG system with custom tools for energy domain.

    Thread Safety:
        This class creates a new Tree instance per request to avoid race conditions
        when modifying agent descriptions in concurrent scenarios. The tool functions
        are stored in a registry and registered on each per-request Tree.
    """

    def __init__(self, client: WeaviateClient):
        """Initialize the Elysia RAG system.

        Args:
            client: Connected Weaviate client
        """
        if not ELYSIA_AVAILABLE:
            raise ImportError("elysia-ai package is required. Run: pip install elysia-ai")

        self.client = client
        self._recursion_limit = 2

        # Base agent description for AInstein - skills will be injected dynamically per query
        self._base_agent_description = """You are AInstein, the Energy System Architecture AI Assistant at Alliander.

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

        # Build tool registry (functions to register on per-request trees)
        self._tool_registry = self._build_tool_registry()

    def _create_tree(self, agent_description: str) -> Tree:
        """Create and configure a new Elysia Tree instance.

        Creates a fresh tree per request to avoid race conditions
        when modifying agent descriptions in concurrent scenarios.

        Args:
            agent_description: Full agent description including skill content

        Returns:
            Configured Tree instance with all tools registered
        """
        tree = Tree(
            agent_description=agent_description,
            style="Professional, concise, and informative. Use structured formatting for lists.",
            end_goal="Provide accurate, well-sourced answers based on the knowledge base."
        )

        # Limit recursion to prevent infinite loops in decision tree
        tree.tree_data.recursion_limit = self._recursion_limit

        # Register all tools on this tree instance
        for name, func in self._tool_registry.items():
            tool(tree=tree)(func)
            logger.debug(f"Registered tool on tree: {name}")

        return tree

    def _build_tool_registry(self) -> dict[str, callable]:
        """Build registry of tool functions for Elysia trees.

        Returns tool functions that can be registered on any Tree instance.
        Tools are not decorated here - they get decorated when registered on a tree.

        Returns:
            Dict mapping tool names to their async functions
        """
        registry = {}

        # Load truncation limits from skill configuration for tool responses
        truncation = _skill_registry.loader.get_truncation(DEFAULT_SKILL)
        content_max_chars = truncation.get("content_max_chars", 800)
        content_chars = truncation.get("elysia_content_chars", 500)
        summary_chars = truncation.get("elysia_summary_chars", 300)

        # Capture self.client for closures
        client = self.client

        # Vocabulary/SKOS search tool
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
            collection = client.collections.get("Vocabulary")
            query_vector = embed_text(query)
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
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

        registry["search_vocabulary"] = search_vocabulary

        # ADR search tool
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
            collection = client.collections.get("ArchitecturalDecision")
            query_vector = embed_text(query)
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "adr_number": obj.properties.get("adr_number", ""),
                    "file_path": obj.properties.get("file_path", ""),
                    "status": obj.properties.get("status", ""),
                    "context": obj.properties.get("context", "")[:content_chars],
                    "decision": obj.properties.get("decision", "")[:content_chars],
                    "consequences": obj.properties.get("consequences", "")[:summary_chars],
                }
                for obj in results.objects
            ]

        registry["search_architecture_decisions"] = search_architecture_decisions

        # Principles search tool
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
            collection = client.collections.get("Principle")
            query_vector = embed_text(query)
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "principle_number": obj.properties.get("principle_number", ""),
                    "file_path": obj.properties.get("file_path", ""),
                    "content": obj.properties.get("content", "")[:content_max_chars],
                    "doc_type": obj.properties.get("doc_type", ""),
                }
                for obj in results.objects
            ]

        registry["search_principles"] = search_principles

        # Policy document search tool
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
            collection = client.collections.get("PolicyDocument")
            query_vector = embed_text(query)
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "file_path": obj.properties.get("file_path", ""),
                    "content": obj.properties.get("content", "")[:content_max_chars],
                    "file_type": obj.properties.get("file_type", ""),
                }
                for obj in results.objects
            ]

        registry["search_policies"] = search_policies

        # List all ADRs tool
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
            collection = client.collections.get("ArchitecturalDecision")

            # Use positive filter (doc_type == "content") for reliable filtering
            # The old NOT_EQUAL approach failed with null/missing doc_type values
            content_filter = build_document_filter("list all ADRs", _skill_registry, DEFAULT_SKILL)

            # Debug: Get unfiltered count to compare
            unfiltered_count = get_collection_count(collection, None)
            filtered_count = get_collection_count(collection, content_filter)
            logger.debug(
                f"list_all_adrs filter debug: unfiltered={unfiltered_count}, "
                f"filtered={filtered_count}, filter_applied={content_filter is not None}"
            )

            results = collection.query.fetch_objects(
                limit=100,
                filters=content_filter,
                return_properties=["title", "status", "file_path", "adr_number", "doc_type"],
            )

            # Debug: Log doc_type distribution
            doc_type_counts = {}
            for obj in results.objects:
                dt = obj.properties.get("doc_type", "None/missing")
                doc_type_counts[dt] = doc_type_counts.get(dt, 0) + 1
            if doc_type_counts:
                logger.debug(f"list_all_adrs doc_type distribution: {doc_type_counts}")

            adrs = []
            for obj in results.objects:
                title = obj.properties.get("title", "")
                file_path = obj.properties.get("file_path", "")
                doc_type = obj.properties.get("doc_type", "")
                if "template" in title.lower() or "template" in file_path.lower():
                    continue
                adrs.append({
                    "title": title,
                    "adr_number": obj.properties.get("adr_number", ""),
                    "status": obj.properties.get("status", ""),
                    "file_path": file_path,
                    "doc_type": doc_type,
                })

            logger.info(
                f"list_all_adrs: Returning {len(adrs)} ADRs "
                f"(collection total: {unfiltered_count}, after filter: {filtered_count})"
            )
            return sorted(adrs, key=lambda x: x.get("adr_number", "") or x.get("file_path", ""))

        registry["list_all_adrs"] = list_all_adrs

        # List all principles tool
        async def list_all_principles() -> list[dict]:
            """List all architecture and governance principles.

            Use this tool when the user asks:
            - What principles exist?
            - List all principles
            - Show me the governance principles

            Returns:
                Complete list of all principles
            """
            collection = client.collections.get("Principle")
            content_filter = build_document_filter("list all principles", _skill_registry, DEFAULT_SKILL)

            results = collection.query.fetch_objects(
                limit=100,
                filters=content_filter,
                return_properties=["title", "doc_type", "file_path", "principle_number"],
            )

            total_count = get_collection_count(collection, content_filter)

            principles = []
            for obj in results.objects:
                title = obj.properties.get("title", "")
                doc_type = obj.properties.get("doc_type", "")
                if "template" in title.lower():
                    continue
                principles.append({
                    "title": title,
                    "principle_number": obj.properties.get("principle_number", ""),
                    "file_path": obj.properties.get("file_path", ""),
                    "type": doc_type,
                })

            logger.info(f"list_all_principles: Returning {len(principles)} of {total_count} total principles (filtered)")
            return sorted(principles, key=lambda x: x.get("principle_number", "") or x.get("file_path", ""))

        registry["list_all_principles"] = list_all_principles

        # Search documents by team/owner
        async def search_by_team(team_name: str, query: str = "", limit: int = 10) -> list[dict]:
            """Search all documents owned by a specific team or workgroup.

            Use this tool when the user asks about documents from a specific team:
            - What documents does ESA/Energy System Architecture have?
            - Show me Data Office documents
            - What are the ESA principles and ADRs?
            - Documents from System Operations team

            Args:
                team_name: Team name or abbreviation
                query: Optional search query to filter results
                limit: Maximum number of results per collection

            Returns:
                List of documents with their type, title, and owner info
            """
            results = []

            # Search ADRs
            try:
                adr_collection = client.collections.get("ArchitecturalDecision")
                if query:
                    search_query = f"{team_name} {query}"
                    query_vector = embed_text(search_query)
                    adr_results = adr_collection.query.hybrid(
                        query=search_query,
                        vector=query_vector,
                        limit=limit,
                        alpha=settings.alpha_default,
                    )
                else:
                    adr_results = adr_collection.query.fetch_objects(
                        limit=limit * 2,
                        return_properties=["title", "status", "owner_team", "owner_team_abbr", "owner_display"],
                    )

                for obj in adr_results.objects:
                    owner = obj.properties.get("owner_team", "") or obj.properties.get("owner_team_abbr", "")
                    owner_display = obj.properties.get("owner_display", "")
                    if team_name.lower() in owner.lower() or team_name.lower() in owner_display.lower():
                        results.append({
                            "type": "ADR",
                            "title": obj.properties.get("title", ""),
                            "status": obj.properties.get("status", ""),
                            "owner": owner_display or owner,
                        })
            except Exception as e:
                logger.warning(f"Error searching ADRs by team: {e}")

            # Search Principles
            try:
                principle_collection = client.collections.get("Principle")
                if query:
                    search_query = f"{team_name} {query}"
                    query_vector = embed_text(search_query)
                    principle_results = principle_collection.query.hybrid(
                        query=search_query,
                        vector=query_vector,
                        limit=limit,
                        alpha=settings.alpha_default,
                    )
                else:
                    principle_results = principle_collection.query.fetch_objects(
                        limit=limit * 2,
                        return_properties=["title", "doc_type", "owner_team", "owner_team_abbr", "owner_display"],
                    )

                for obj in principle_results.objects:
                    owner = obj.properties.get("owner_team", "") or obj.properties.get("owner_team_abbr", "")
                    owner_display = obj.properties.get("owner_display", "")
                    if team_name.lower() in owner.lower() or team_name.lower() in owner_display.lower():
                        results.append({
                            "type": "Principle",
                            "title": obj.properties.get("title", ""),
                            "doc_type": obj.properties.get("doc_type", ""),
                            "owner": owner_display or owner,
                        })
            except Exception as e:
                logger.warning(f"Error searching Principles by team: {e}")

            # Search Policies
            try:
                policy_collection = client.collections.get("PolicyDocument")
                if query:
                    search_query = f"{team_name} {query}"
                    query_vector = embed_text(search_query)
                    policy_results = policy_collection.query.hybrid(
                        query=search_query,
                        vector=query_vector,
                        limit=limit,
                        alpha=settings.alpha_default,
                    )
                else:
                    policy_results = policy_collection.query.fetch_objects(
                        limit=limit * 2,
                        return_properties=["title", "file_type", "owner_team", "owner_team_abbr", "owner_display"],
                    )

                for obj in policy_results.objects:
                    owner = obj.properties.get("owner_team", "") or obj.properties.get("owner_team_abbr", "")
                    owner_display = obj.properties.get("owner_display", "")
                    if team_name.lower() in owner.lower() or team_name.lower() in owner_display.lower():
                        results.append({
                            "type": "Policy",
                            "title": obj.properties.get("title", ""),
                            "file_type": obj.properties.get("file_type", ""),
                            "owner": owner_display or owner,
                        })
            except Exception as e:
                logger.warning(f"Error searching Policies by team: {e}")

            return results

        registry["search_by_team"] = search_by_team

        # Collection statistics tool
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
                if client.collections.exists(name):
                    collection = client.collections.get(name)
                    aggregate = collection.aggregate.over_all(total_count=True)
                    stats[name] = aggregate.total_count
                else:
                    stats[name] = 0
            return stats

        registry["get_collection_stats"] = get_collection_stats

        # Dedicated counting tool for accurate document counts
        async def count_documents(collection_type: str = "all") -> dict:
            """Get accurate document counts with proper filtering.

            Use this tool when the user asks:
            - How many ADRs are there?
            - How many principles exist?
            - Count the policies
            - Total documents in the system

            Args:
                collection_type: Type to count - "adr", "principle", "policy", "vocabulary", or "all"

            Returns:
                Dictionary with accurate counts
            """
            counts = {}

            type_mapping = {
                "adr": "ArchitecturalDecision",
                "adrs": "ArchitecturalDecision",
                "principle": "Principle",
                "principles": "Principle",
                "policy": "PolicyDocument",
                "policies": "PolicyDocument",
                "vocabulary": "Vocabulary",
                "vocab": "Vocabulary",
            }

            collections_to_check = []
            if collection_type.lower() == "all":
                collections_to_check = ["ArchitecturalDecision", "Principle", "PolicyDocument", "Vocabulary"]
            else:
                coll_name = type_mapping.get(collection_type.lower())
                if coll_name:
                    collections_to_check = [coll_name]
                else:
                    return {"error": f"Unknown collection type: {collection_type}"}

            for name in collections_to_check:
                try:
                    collection = client.collections.get(name)

                    if name != "Vocabulary":
                        content_filter = build_document_filter(f"count {name}", _skill_registry, DEFAULT_SKILL)
                        aggregate = collection.aggregate.over_all(
                            total_count=True,
                            filters=content_filter
                        )
                    else:
                        aggregate = collection.aggregate.over_all(total_count=True)

                    friendly_names = {
                        "ArchitecturalDecision": "ADRs",
                        "Principle": "Principles",
                        "PolicyDocument": "Policies",
                        "Vocabulary": "Vocabulary Terms"
                    }
                    counts[friendly_names.get(name, name)] = aggregate.total_count
                except Exception as e:
                    logger.warning(f"Error counting {name}: {e}")
                    counts[name] = 0

            return counts

        registry["count_documents"] = count_documents

        logger.info(f"Built tool registry with {len(registry)} tools: {list(registry.keys())}")
        return registry

    async def query(self, question: str, collection_names: Optional[list[str]] = None) -> tuple[str, list[dict]]:
        """Process a query using Elysia's decision tree.

        Creates a fresh Tree instance per request to ensure thread safety
        when processing concurrent requests.

        Args:
            question: The user's question
            collection_names: Optional list of collection names to focus on

        Returns:
            Tuple of (response text, retrieved objects)
        """
        logger.info(f"Elysia processing: {question}")

        # Determine structured mode FIRST - this affects both prompt injection and post-processing
        # response-contract skill enforces JSON output format
        structured_mode = _skill_registry.is_skill_active("response-contract", question)
        if structured_mode:
            logger.info(f"Structured mode ACTIVE for query: {question[:50]}...")

        # Always specify our collection names to bypass Elysia's metadata collection discovery
        # This avoids gRPC errors from Elysia's internal collections
        our_collections = collection_names or [
            "Vocabulary",
            "ArchitecturalDecision",
            "Principle",
            "PolicyDocument",
        ]

        # Build agent description with injected skills
        skill_content = _skill_registry.get_all_skill_content(question)
        if skill_content:
            agent_description = f"{self._base_agent_description}\n\n{skill_content}"
            logger.debug("Injected skills into agent description")
        else:
            agent_description = self._base_agent_description

        # Create per-request tree instance (thread-safe: no shared mutable state)
        request_tree = self._create_tree(agent_description)

        try:
            # Use semaphore to limit concurrent Elysia calls (prevents thread explosion)
            # Use asyncio.to_thread to offload blocking Tree call (prevents event loop blocking)
            # Use wait_for to add timeout and enable cancellation
            semaphore = _get_elysia_semaphore()
            async with semaphore:
                response, objects = await asyncio.wait_for(
                    asyncio.to_thread(
                        request_tree, question, collection_names=our_collections
                    ),
                    timeout=settings.elysia_query_timeout_seconds
                )

                # Log tree completion stats for debugging (must be done after call completes)
                iterations = request_tree.tree_data.num_trees_completed
                limit = request_tree.tree_data.recursion_limit

            if iterations >= limit:
                logger.warning(f"Elysia tree hit recursion limit ({iterations}/{limit})")
            else:
                logger.debug(f"Elysia tree completed in {iterations} iteration(s)")

        except asyncio.TimeoutError:
            # Query exceeded timeout - log and fallback
            logger.warning(
                f"Elysia tree timed out after {settings.elysia_query_timeout_seconds}s, "
                "using direct tool execution"
            )
            response, objects = await self._direct_query(question, structured_mode=structured_mode)
            return response, objects

        except Exception as e:
            # If Elysia's tree fails, fall back to direct tool execution
            logger.warning(f"Elysia tree failed: {e}, using direct tool execution")
            # _direct_query handles its own post-processing, pass structured_mode
            response, objects = await self._direct_query(question, structured_mode=structured_mode)
            # Return directly since _direct_query already post-processed
            return response, objects

        # POST-PROCESS the Elysia tree response through unified contract enforcement
        # This is the critical fix: main path must also enforce structured response contract
        processed_response, was_structured, reason = postprocess_llm_output(
            raw_response=response,
            structured_mode=structured_mode,
            enforcement_policy=DEFAULT_ENFORCEMENT_POLICY,
        )

        if structured_mode:
            logger.info(f"Main path post-processing: was_structured={was_structured}, reason={reason}")

        return processed_response, objects

    async def _direct_query(self, question: str, structured_mode: bool = None) -> tuple[str, list[dict]]:
        """Direct query execution bypassing Elysia tree when it fails.

        Supports both OpenAI and Ollama as LLM backends.
        Uses client-side embeddings for local collections (Ollama provider).
        Implements confidence-based abstention to prevent hallucination.

        Args:
            question: The user's question
            structured_mode: Whether response-contract is active (auto-detected if None)

        Returns:
            Tuple of (response text, retrieved objects)
        """
        # Auto-detect structured mode if not provided
        if structured_mode is None:
            structured_mode = _skill_registry.is_skill_active("response-contract", question)
        question_lower = question.lower()
        all_results = []
        collection_counts = {}  # Track total counts for transparency

        # Detect query type: list/catalog vs semantic/specific
        is_catalog_query = is_list_query(question)
        if is_catalog_query:
            logger.info(f"Catalog query detected: {question}")

        # Load retrieval limits from skill configuration
        retrieval_limits = _skill_registry.loader.get_retrieval_limits(DEFAULT_SKILL)
        adr_limit = retrieval_limits.get("adr", 20)
        principle_limit = retrieval_limits.get("principle", 12)
        policy_limit = retrieval_limits.get("policy", 8)
        vocab_limit = retrieval_limits.get("vocabulary", 8)
        catalog_fetch_limit = retrieval_limits.get("catalog_fetch_limit", 100)

        # Load truncation limits from skill configuration
        truncation = _skill_registry.loader.get_truncation(DEFAULT_SKILL)
        content_max_chars = truncation.get("content_max_chars", 800)
        content_chars = truncation.get("elysia_content_chars", 500)
        summary_chars = truncation.get("elysia_summary_chars", 300)

        # Determine collection suffix based on provider
        # Local collections use client-side embeddings (Nomic via Ollama)
        # OpenAI collections use Weaviate's text2vec-openai vectorizer
        use_openai_collections = settings.llm_provider == "openai"
        suffix = "_OpenAI" if use_openai_collections else ""

        # For local collections, compute query embedding client-side
        # This is a workaround for Weaviate text2vec-ollama bug (#8406)
        query_vector = None
        if not use_openai_collections:
            try:
                query_vector = embed_text(question)
            except Exception as e:
                logger.error(f"Failed to compute query embedding: {e}")

        # Build document filter based on skill configuration and query intent
        content_filter = build_document_filter(question, _skill_registry, DEFAULT_SKILL)

        # Request metadata for abstention decisions
        metadata_request = MetadataQuery(score=True, distance=True)

        # Search relevant collections
        if any(term in question_lower for term in ["adr", "decision", "architecture"]):
            try:
                collection = self.client.collections.get(f"ArchitecturalDecision{suffix}")

                # Always get total count first for transparency
                total_count = get_collection_count(collection, content_filter)
                collection_counts["ADR"] = total_count

                if is_catalog_query:
                    # Catalog query: fetch all matching documents
                    results = collection.query.fetch_objects(
                        filters=content_filter,
                        limit=catalog_fetch_limit,
                        return_metadata=metadata_request
                    )
                    logger.info(f"Fetched {len(results.objects)} of {total_count} total ADRs")
                else:
                    # Semantic query: use hybrid search for relevance
                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=adr_limit, alpha=settings.alpha_vocabulary,
                        filters=content_filter, return_metadata=metadata_request
                    )

                for obj in results.objects:
                    all_results.append({
                        "type": "ADR",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("decision", "")[:content_chars],
                        "distance": getattr(obj.metadata, 'distance', None),
                        "score": getattr(obj.metadata, 'score', None),
                    })
            except Exception as e:
                logger.warning(f"Error searching ArchitecturalDecision{suffix}: {e}")

        if any(term in question_lower for term in ["principle", "governance", "esa"]):
            try:
                collection = self.client.collections.get(f"Principle{suffix}")

                # Always get total count first for transparency
                total_count = get_collection_count(collection, content_filter)
                collection_counts["Principle"] = total_count

                if is_catalog_query:
                    results = collection.query.fetch_objects(
                        filters=content_filter,
                        limit=catalog_fetch_limit,
                        return_metadata=metadata_request
                    )
                    logger.info(f"Fetched {len(results.objects)} of {total_count} total Principles")
                else:
                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=principle_limit, alpha=settings.alpha_vocabulary,
                        filters=content_filter, return_metadata=metadata_request
                    )

                for obj in results.objects:
                    all_results.append({
                        "type": "Principle",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", "")[:content_chars],
                        "distance": getattr(obj.metadata, 'distance', None),
                        "score": getattr(obj.metadata, 'score', None),
                    })
            except Exception as e:
                logger.warning(f"Error searching Principle{suffix}: {e}")

        if any(term in question_lower for term in ["policy", "data governance", "compliance"]):
            try:
                collection = self.client.collections.get(f"PolicyDocument{suffix}")

                # Always get total count first for transparency
                total_count = get_collection_count(collection, content_filter)
                collection_counts["Policy"] = total_count

                if is_catalog_query:
                    results = collection.query.fetch_objects(
                        filters=content_filter,
                        limit=catalog_fetch_limit,
                        return_metadata=metadata_request
                    )
                    logger.info(f"Fetched {len(results.objects)} of {total_count} total Policies")
                else:
                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=policy_limit, alpha=settings.alpha_vocabulary,
                        return_metadata=metadata_request
                    )

                for obj in results.objects:
                    all_results.append({
                        "type": "Policy",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", "")[:content_chars],
                        "distance": getattr(obj.metadata, 'distance', None),
                        "score": getattr(obj.metadata, 'score', None),
                    })
            except Exception as e:
                logger.warning(f"Error searching PolicyDocument{suffix}: {e}")

        # Expanded keyword matching for vocabulary - catch "what is X" type questions
        vocab_keywords = ["vocab", "concept", "definition", "cim", "iec", "what is", "what does", "define", "meaning", "term", "standard", "archimate"]
        if any(term in question_lower for term in vocab_keywords):
            try:
                collection = self.client.collections.get(f"Vocabulary{suffix}")

                # Always get total count first for transparency
                # Note: Vocabulary doesn't use content_filter (no doc_type field)
                total_count = get_collection_count(collection, None)
                collection_counts["Vocabulary"] = total_count

                if is_catalog_query:
                    results = collection.query.fetch_objects(
                        limit=catalog_fetch_limit,
                        return_metadata=metadata_request
                    )
                    logger.info(f"Fetched {len(results.objects)} of {total_count} total Vocabulary terms")
                else:
                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=vocab_limit, alpha=settings.alpha_vocabulary,
                        return_metadata=metadata_request
                    )

                for obj in results.objects:
                    all_results.append({
                        "type": "Vocabulary",
                        "label": obj.properties.get("pref_label", ""),
                        "definition": obj.properties.get("definition", ""),
                        "distance": getattr(obj.metadata, 'distance', None),
                        "score": getattr(obj.metadata, 'score', None),
                    })
            except Exception as e:
                logger.warning(f"Error searching Vocabulary{suffix}: {e}")

        # If no specific collection matched, search all including Vocabulary
        if not all_results:
            # Map collection base names to display types
            type_map = {
                "ArchitecturalDecision": "ADR",
                "Principle": "Principle",
                "PolicyDocument": "Policy",
                "Vocabulary": "Vocabulary"
            }
            for coll_base in ["ArchitecturalDecision", "Principle", "PolicyDocument", "Vocabulary"]:
                try:
                    collection = self.client.collections.get(f"{coll_base}{suffix}")

                    # Get total count for transparency (even in fallback)
                    total_count = get_collection_count(collection, content_filter if coll_base != "Vocabulary" else None)
                    display_type = type_map.get(coll_base, coll_base)
                    if total_count > 0 and display_type not in collection_counts:
                        collection_counts[display_type] = total_count

                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=3, alpha=settings.alpha_vocabulary,
                        return_metadata=metadata_request
                    )
                    for obj in results.objects:
                        if coll_base == "Vocabulary":
                            all_results.append({
                                "type": "Vocabulary",
                                "label": obj.properties.get("pref_label", ""),
                                "definition": obj.properties.get("definition", ""),
                                "distance": getattr(obj.metadata, 'distance', None),
                                "score": getattr(obj.metadata, 'score', None),
                            })
                        else:
                            all_results.append({
                                "type": display_type,
                                "title": obj.properties.get("title", ""),
                                "content": obj.properties.get("content", obj.properties.get("decision", ""))[:summary_chars],
                                "distance": getattr(obj.metadata, 'distance', None),
                                "score": getattr(obj.metadata, 'score', None),
                            })
                except Exception as e:
                    logger.warning(f"Error searching {coll_base}{suffix}: {e}")

        # Check if we should abstain from answering
        abstain, reason = should_abstain(question, all_results)
        if abstain:
            logger.info(f"Abstaining from query: {reason}")
            return get_abstention_response(reason), all_results

        # Build context from retrieved results with transparency about totals
        max_context_results = truncation.get("max_context_results", 10)

        # Add transparency header with collection counts
        context_parts = []
        if collection_counts:
            count_info = []
            # Count how many of each type are in the truncated results (what LLM actually sees)
            truncated_results = all_results[:max_context_results]
            for doc_type, total in collection_counts.items():
                # Count shown items in the TRUNCATED results, not all_results
                shown = sum(1 for r in truncated_results if r.get("type") == doc_type)
                if shown < total:
                    count_info.append(f"{doc_type}: showing {shown} of {total} total")
                else:
                    count_info.append(f"{doc_type}: {total} total (all shown)")
            context_parts.append("--- COLLECTION COUNTS (be transparent about these!) ---")
            context_parts.append("\n".join(count_info))
            context_parts.append("--- END COUNTS ---\n")

        # Add document contents
        context_parts.append("\n\n".join([
            f"[{r.get('type', 'Document')}] {r.get('title', r.get('label', 'Untitled'))}: {r.get('content', r.get('definition', ''))}"
            for r in all_results[:max_context_results]
        ]))

        context = "\n".join(context_parts)

        # Get skill content for prompt injection
        skill_content = _skill_registry.get_all_skill_content(question)

        system_prompt = """You are AInstein, the Energy System Architecture AI Assistant at Alliander.

Your role is to help architects, engineers, and stakeholders navigate Alliander's energy system architecture knowledge base, including:
- Architectural Decision Records (ADRs)
- Data governance principles and policies
- IEC/CIM vocabulary and standards
- Energy domain concepts and terminology

Guidelines:
- Base your answers strictly on the provided context
- If the information is not in the context, clearly state that you don't have that information
- Be concise but thorough
- When referencing ADRs, use the format ADR.XX (e.g., ADR.21)
- When referencing Principles, use the format PCP.XX (e.g., PCP.10)
- For technical terms, provide clear explanations

""" + RESPONSE_SCHEMA_INSTRUCTIONS

        # Inject skill rules if available
        if skill_content:
            system_prompt = f"{system_prompt}\n\n{skill_content}"
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

        # Generate response based on LLM provider
        if settings.llm_provider == "ollama":
            raw_response = await self._generate_with_ollama(system_prompt, user_prompt)
        else:
            raw_response = await self._generate_with_openai(system_prompt, user_prompt)

        # POST-PROCESS through unified contract enforcement
        # This ensures consistent behavior between main path and fallback path
        response_text, was_structured, reason = postprocess_llm_output(
            raw_response=raw_response,
            structured_mode=structured_mode,
            enforcement_policy=DEFAULT_ENFORCEMENT_POLICY,
        )

        if structured_mode:
            logger.info(f"Fallback path post-processing: was_structured={was_structured}, reason={reason}")

        return response_text, all_results

    async def _generate_with_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using Ollama API.

        Args:
            system_prompt: System instruction
            user_prompt: User's message with context

        Returns:
            Generated response text
        """
        import httpx
        import re
        import time

        start_time = time.time()
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min for slow local models
                response = await client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model": settings.ollama_model,
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {"num_predict": 1000},
                    },
                )
                response.raise_for_status()
                result = response.json()
                response_text = result.get("response", "")

                # Strip <think>...</think> tags from responses
                response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
                response_text = re.sub(r'</?think>', '', response_text)
                response_text = re.sub(r'\n{3,}', '\n\n', response_text)

                return response_text.strip()

        except httpx.TimeoutException:
            latency_ms = int((time.time() - start_time) * 1000)
            raise Exception(f"Ollama generation timed out after {latency_ms}ms.")

        except httpx.HTTPStatusError as e:
            latency_ms = int((time.time() - start_time) * 1000)
            raise Exception(f"Ollama HTTP error after {latency_ms}ms: {str(e)}")

    async def _generate_with_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using OpenAI API.

        Args:
            system_prompt: System instruction
            user_prompt: User's message with context

        Returns:
            Generated response text
        """
        from openai import OpenAI

        openai_client = OpenAI(api_key=settings.openai_api_key)

        # GPT-5.x models use max_completion_tokens instead of max_tokens
        model = settings.openai_chat_model
        completion_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if model.startswith("gpt-5"):
            completion_kwargs["max_completion_tokens"] = 1000
        else:
            completion_kwargs["max_tokens"] = 1000

        response = openai_client.chat.completions.create(**completion_kwargs)

        return response.choices[0].message.content

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
