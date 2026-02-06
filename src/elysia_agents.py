"""Elysia-based agentic RAG system for AION-AINSTEIN.

Uses Weaviate's Elysia framework for decision tree-based tool selection
and agentic query processing.
"""

import logging
from typing import Optional, Any

import re
from weaviate import WeaviateClient
from weaviate.classes.query import Filter, MetadataQuery

from .config import settings
from .skills import DEFAULT_SKILL
from .skills.registry import get_skill_registry
from .weaviate.embeddings import embed_text

# Get the global singleton registry (shared across all modules)
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

        # Limit recursion to prevent infinite loops in decision tree
        # Default is 5, which can cause repeated responses when the
        # cited_summarize action doesn't signal termination properly
        self.tree.tree_data.recursion_limit = 2

        self._register_tools()

    def _register_tools(self) -> None:
        """Register custom tools for each knowledge domain."""

        # Load truncation limits from skill configuration for tool responses
        truncation = _skill_registry.loader.get_truncation(DEFAULT_SKILL)
        content_max_chars = truncation.get("content_max_chars", 800)
        content_chars = truncation.get("elysia_content_chars", 500)
        summary_chars = truncation.get("elysia_summary_chars", 300)

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
                return_properties=["title", "status", "file_path", "adr_number"],
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
                    "adr_number": obj.properties.get("adr_number", ""),
                    "status": obj.properties.get("status", ""),
                    "file_path": file_path,
                })
            return sorted(adrs, key=lambda x: x.get("adr_number", "") or x.get("file_path", ""))

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
                return_properties=["title", "doc_type", "file_path", "principle_number"],
            )
            principles = [
                {
                    "title": obj.properties.get("title", ""),
                    "principle_number": obj.properties.get("principle_number", ""),
                    "file_path": obj.properties.get("file_path", ""),
                    "type": obj.properties.get("doc_type", ""),
                }
                for obj in results.objects
            ]
            return sorted(principles, key=lambda x: x.get("principle_number", "") or x.get("file_path", ""))

        # Search documents by team/owner
        @tool(tree=self.tree)
        async def search_by_team(team_name: str, query: str = "", limit: int = 10) -> list[dict]:
            """Search all documents owned by a specific team or workgroup.

            Use this tool when the user asks about documents from a specific team:
            - What documents does ESA/Energy System Architecture have?
            - Show me Data Office documents
            - What are the ESA principles and ADRs?
            - Documents from System Operations team

            This searches across ALL collection types (ADRs, Principles, Policies)
            filtered by the owning team.

            Args:
                team_name: Team name or abbreviation (e.g., "ESA", "Energy System Architecture", "Data Office")
                query: Optional search query to filter results within the team's documents
                limit: Maximum number of results per collection

            Returns:
                List of documents with their type, title, and owner info
            """
            results = []

            # Search ADRs
            try:
                adr_collection = self.client.collections.get("ArchitecturalDecision")
                if query:
                    adr_results = adr_collection.query.hybrid(
                        query=f"{team_name} {query}",
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
                principle_collection = self.client.collections.get("Principle")
                if query:
                    principle_results = principle_collection.query.hybrid(
                        query=f"{team_name} {query}",
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
                policy_collection = self.client.collections.get("PolicyDocument")
                if query:
                    policy_results = policy_collection.query.hybrid(
                        query=f"{team_name} {query}",
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

        logger.info("Registered Elysia tools: vocabulary, ADR, principles, policies, search_by_team")

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
        ]

        try:
            response, objects = self.tree(question, collection_names=our_collections)

            # Log tree completion stats for debugging
            iterations = self.tree.tree_data.num_trees_completed
            limit = self.tree.tree_data.recursion_limit
            if iterations >= limit:
                logger.warning(f"Elysia tree hit recursion limit ({iterations}/{limit})")
            else:
                logger.debug(f"Elysia tree completed in {iterations} iteration(s)")

        except Exception as e:
            # If Elysia's tree fails, fall back to direct tool execution
            logger.warning(f"Elysia tree failed: {e}, using direct tool execution")
            response, objects = await self._direct_query(question)

        # Note: We return the raw response, but the CLI doesn't display it anymore
        # Elysia's framework already displays the answer via its "Assistant response" panels
        return response, objects

    async def _direct_query(self, question: str) -> tuple[str, list[dict]]:
        """Direct query execution bypassing Elysia tree when it fails.

        Supports both OpenAI and Ollama as LLM backends.
        Uses client-side embeddings for local collections (Ollama provider).
        Implements confidence-based abstention to prevent hallucination.

        Args:
            question: The user's question

        Returns:
            Tuple of (response text, retrieved objects)
        """
        question_lower = question.lower()
        all_results = []

        # Load retrieval limits from skill configuration
        retrieval_limits = _skill_registry.loader.get_retrieval_limits(DEFAULT_SKILL)
        adr_limit = retrieval_limits.get("adr", 8)
        principle_limit = retrieval_limits.get("principle", 6)
        policy_limit = retrieval_limits.get("policy", 4)
        vocab_limit = retrieval_limits.get("vocabulary", 4)

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

        # Filter to exclude index/template documents
        content_filter = Filter.by_property("doc_type").equal("content")

        # Request metadata for abstention decisions
        metadata_request = MetadataQuery(score=True, distance=True)

        # Search relevant collections
        if any(term in question_lower for term in ["adr", "decision", "architecture"]):
            try:
                collection = self.client.collections.get(f"ArchitecturalDecision{suffix}")
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=adr_limit, alpha=settings.alpha_vocabulary,
                    filters=content_filter, return_metadata=metadata_request
                )
                for obj in results.objects:
                    all_results.append({
                        "type": "ADR",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("decision", "")[:content_chars],
                        "distance": obj.metadata.distance,
                        "score": obj.metadata.score,
                    })
            except Exception as e:
                logger.warning(f"Error searching ArchitecturalDecision{suffix}: {e}")

        if any(term in question_lower for term in ["principle", "governance", "esa"]):
            try:
                collection = self.client.collections.get(f"Principle{suffix}")
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=principle_limit, alpha=settings.alpha_vocabulary,
                    filters=content_filter, return_metadata=metadata_request
                )
                for obj in results.objects:
                    all_results.append({
                        "type": "Principle",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", "")[:content_chars],
                        "distance": obj.metadata.distance,
                        "score": obj.metadata.score,
                    })
            except Exception as e:
                logger.warning(f"Error searching Principle{suffix}: {e}")

        if any(term in question_lower for term in ["policy", "data governance", "compliance"]):
            try:
                collection = self.client.collections.get(f"PolicyDocument{suffix}")
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=policy_limit, alpha=settings.alpha_vocabulary,
                    return_metadata=metadata_request
                )
                for obj in results.objects:
                    all_results.append({
                        "type": "Policy",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", "")[:content_chars],
                        "distance": obj.metadata.distance,
                        "score": obj.metadata.score,
                    })
            except Exception as e:
                logger.warning(f"Error searching PolicyDocument{suffix}: {e}")

        # Expanded keyword matching for vocabulary - catch "what is X" type questions
        vocab_keywords = ["vocab", "concept", "definition", "cim", "iec", "what is", "what does", "define", "meaning", "term", "standard", "archimate"]
        if any(term in question_lower for term in vocab_keywords):
            try:
                collection = self.client.collections.get(f"Vocabulary{suffix}")
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=vocab_limit, alpha=settings.alpha_vocabulary,
                    return_metadata=metadata_request
                )
                for obj in results.objects:
                    all_results.append({
                        "type": "Vocabulary",
                        "label": obj.properties.get("pref_label", ""),
                        "definition": obj.properties.get("definition", ""),
                        "distance": obj.metadata.distance,
                        "score": obj.metadata.score,
                    })
            except Exception as e:
                logger.warning(f"Error searching Vocabulary{suffix}: {e}")

        # If no specific collection matched, search all including Vocabulary
        if not all_results:
            for coll_base in ["ArchitecturalDecision", "Principle", "PolicyDocument", "Vocabulary"]:
                try:
                    collection = self.client.collections.get(f"{coll_base}{suffix}")
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
                                "distance": obj.metadata.distance,
                                "score": obj.metadata.score,
                            })
                        else:
                            all_results.append({
                                "type": coll_base,
                                "title": obj.properties.get("title", ""),
                                "content": obj.properties.get("content", obj.properties.get("decision", ""))[:summary_chars],
                                "distance": obj.metadata.distance,
                                "score": obj.metadata.score,
                            })
                except Exception as e:
                    logger.warning(f"Error searching {coll_base}{suffix}: {e}")

        # Check if we should abstain from answering
        abstain, reason = should_abstain(question, all_results)
        if abstain:
            logger.info(f"Abstaining from query: {reason}")
            return get_abstention_response(reason), all_results

        # Build context from retrieved results
        max_context_results = truncation.get("max_context_results", 10)
        context = "\n\n".join([
            f"[{r.get('type', 'Document')}] {r.get('title', r.get('label', 'Untitled'))}: {r.get('content', r.get('definition', ''))}"
            for r in all_results[:max_context_results]
        ])

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
- For technical terms, provide clear explanations"""

        # Inject skill rules if available
        if skill_content:
            system_prompt = f"{system_prompt}\n\n{skill_content}"
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

        # Generate response based on LLM provider
        if settings.llm_provider == "ollama":
            response_text = await self._generate_with_ollama(system_prompt, user_prompt)
        else:
            response_text = await self._generate_with_openai(system_prompt, user_prompt)

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
