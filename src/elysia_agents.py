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

# Skills framework — optional, degrades gracefully
try:
    from .skills import get_skill_registry
    _SKILLS_AVAILABLE = True
except ImportError:
    _SKILLS_AVAILABLE = False

# Hardcoded fallback for when skills framework is unavailable or disabled
_DEFAULT_DISTANCE_THRESHOLD = 0.5


def _get_distance_threshold() -> float:
    """Get distance threshold from rag-quality-assurance skill.

    Falls back to hardcoded default if the skill registry fails to load
    or the rag-quality-assurance skill is disabled.

    Returns:
        Distance threshold for abstention
    """
    if not _SKILLS_AVAILABLE:
        return _DEFAULT_DISTANCE_THRESHOLD
    try:
        registry = get_skill_registry()
        entry = registry.get_skill_entry("rag-quality-assurance")
        if entry is None or not entry.enabled:
            return _DEFAULT_DISTANCE_THRESHOLD
        return registry.loader.get_abstention_thresholds("rag-quality-assurance")
    except Exception:
        return _DEFAULT_DISTANCE_THRESHOLD


def _get_skill_content(query: str) -> str:
    """Get combined skill content for prompt injection.

    Returns all enabled skill content, or empty string if the skills
    framework is unavailable. The query parameter is unused — the LLM
    decides what's relevant, not keyword matching.
    """
    if not _SKILLS_AVAILABLE:
        return ""
    try:
        return get_skill_registry().get_all_skill_content()
    except Exception:
        return ""


def should_abstain(query: str, results: list) -> tuple[bool, str]:
    """Determine if the system should abstain from answering.

    Checks retrieval quality signals to prevent hallucination when
    no relevant documents are found.

    Args:
        query: The user's question
        results: List of retrieved documents with distance/score metadata

    Returns:
        Tuple of (should_abstain: bool, reason: str)
    """
    # No results at all
    if not results:
        return True, "No relevant documents found in the knowledge base."

    distance_threshold = _get_distance_threshold()

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
from .weaviate.embeddings import embed_text

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

# Monkey-patch Elysia's summarization prompts to remove hardcoded anti-list
# instructions that conflict with our skill-based formatting rules.
# The original prompts say "Do not give an itemised list" — but our
# response-formatter skill needs lists for catalog queries.
# This patch replaces the anti-list sentence with a reference to the atlas
# (where our skill content is injected), so the LLM follows our formatting.
if ELYSIA_AVAILABLE:
    try:
        from elysia.tools.text.prompt_templates import (
            CitedSummarizingPrompt,
            SummarizingPrompt,
            TextResponsePrompt,
        )

        _ANTI_LIST_SENTENCES = [
            "Do not list any of the retrieved objects in your response. "
            "Do not give an itemised list of the objects, since they will be displayed to the user anyway.",
            "Do not list any of the retrieved objects in your response. Do not give an itemised list of the objects, since they will be displayed to the user anyway.",
        ]
        _REPLACEMENT = "Format the response according to the agent description guidelines."

        _patched = False
        for prompt_cls in [CitedSummarizingPrompt, SummarizingPrompt, TextResponsePrompt]:
            if prompt_cls.__doc__:
                for anti_list in _ANTI_LIST_SENTENCES:
                    if anti_list in prompt_cls.__doc__:
                        prompt_cls.__doc__ = prompt_cls.__doc__.replace(anti_list, _REPLACEMENT)
                        _patched = True
                        break

        if _patched:
            logger.info("Patched Elysia summarization prompts to respect skill formatting rules")
        else:
            logger.warning(
                "CitedSummarizingPrompt docstring changed — "
                "skill formatting may not work. Check elysia-ai version."
            )
    except Exception as e:
        logger.warning(f"Failed to patch Elysia prompts: {e}")


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
        self._use_openai = settings.llm_provider == "openai"
        self._collection_suffix = "_OpenAI" if self._use_openai else ""
        self._register_tools()

    def _get_collection(self, base_name: str):
        """Get a Weaviate collection with the correct provider suffix.

        Args:
            base_name: Base collection name (e.g., "Vocabulary")

        Returns:
            Weaviate collection object
        """
        return self.client.collections.get(f"{base_name}{self._collection_suffix}")

    def _get_query_vector(self, query: str) -> Optional[list[float]]:
        """Compute query embedding for Ollama collections, None for OpenAI.

        OpenAI collections use server-side vectorization (text2vec-openai),
        so no client-side vector is needed. Ollama collections use
        Vectorizer.none() and require client-side embeddings.

        Args:
            query: The search query text

        Returns:
            Embedding vector for Ollama, None for OpenAI
        """
        if self._use_openai:
            return None
        try:
            return embed_text(query)
        except Exception as e:
            logger.error(f"Failed to compute query embedding: {e}")
            return None

    def _register_tools(self) -> None:
        """Register custom tools for each knowledge domain."""

        # Vocabulary/SKOS search tool
        @tool(tree=self.tree)
        async def search_vocabulary(query: str, limit: int = 5) -> list[dict]:
            """Search SKOS/OWL vocabulary concepts from energy domain standards.

            This collection contains semantic vocabulary terms from 70+ RDF/Turtle
            ontology files covering IEC energy standards and domain models:
            - IEC 61968/61970 (CIM - Common Information Model)
            - IEC 62325 (energy market), IEC 62746 (demand response)
            - ENTSOE HEMRM (European energy market model)
            - ArchiMate (enterprise architecture), ESA vocabulary
            - Dutch legal/regulatory vocabularies (energy law)

            Each concept has: pref_label (primary term), definition, broader/narrower
            hierarchy, related concepts, vocabulary_name, and URI.

            Use this tool when the user asks about:
            - Energy terminology, definitions, or "what is/does X mean"
            - CIM concepts, IEC standards, SKOS vocabularies
            - Technical terms from the energy domain
            - Ontology classes, properties, or concept hierarchies

            Do NOT use this tool for numbered documents (ADR.NN or PCP.NN) —
            use search_architecture_decisions or search_principles instead.

            Args:
                query: Search query for vocabulary concepts
                limit: Maximum number of results to return

            Returns:
                List of matching vocabulary concepts with definitions
            """
            collection = self._get_collection("Vocabulary")
            query_vector = self._get_query_vector(query)
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

        # ADR search tool
        @tool(tree=self.tree)
        async def search_architecture_decisions(query: str, limit: int = 10) -> list[dict]:
            """Search Architectural Decision Records (ADRs) for design decisions.

            ADRs are formal records of significant architecture decisions. Each has
            sections: Context (problem statement), Decision (outcome), Consequences.
            Identifier format: ADR.NN (e.g., ADR.12 = "Use CIM as default domain language").

            ADR number ranges:
            - ADR.0-2: Meta decisions (markdown format, writing conventions, DACI)
            - ADR.10-12: Standardisation (IEC standards, CIM adoption)
            - ADR.20-31: Energy system decisions (demand response, security, OAuth, TLS)

            Decision Approval Records (DARs): Files like 0029D contain the approval
            record for ADR.29. Use these for "who approved" or "when was it approved" queries.

            ID aliases — all of these refer to ADR.29:
            "ADR 29", "adr-29", "ADR.0029", "ADR-0029", "decision 29"

            IMPORTANT — Numbering overlap with Principles:
            Numbers 10-12 and 20-31 exist in BOTH ADRs and Principles. For example:
            - ADR.22 = "Use priority-based scheduling" (architecture decision)
            - PCP.22 = "Omnichannel Multibrand" (business principle)
            If the user says "document 22" or just a number without specifying ADR or PCP,
            search BOTH this collection AND search_principles to present both results.

            Query intent patterns:
            - "What does ADR.12 decide?" → lookup the ADR itself
            - "Who approved ADR.29?" → search for "0029D" to find the DAR
            - "What decisions about security?" → topic search
            - "List all ADRs" → use list_all_adrs tool instead

            Args:
                query: Search query — use the 4-digit number (e.g., "0029") for ID lookups
                limit: Maximum number of results to return

            Returns:
                List of matching ADRs with title, status, context, decision, consequences
            """
            collection = self._get_collection("ArchitecturalDecision")

            # Detect ADR number in query for filter-based lookup
            adr_match = re.search(r"(?:ADR[.\-\s]?)?(0*(\d{1,4}))\b", query, re.IGNORECASE)
            adr_filter = None
            if adr_match:
                padded = adr_match.group(2).zfill(4)
                # Check if query asks about approval/DAR — if not, exclude DARs
                is_dar_query = bool(re.search(r"\bD\b|approv|DAR|who\s+(?:accepted|approved)", query, re.IGNORECASE))
                if is_dar_query:
                    adr_filter = Filter.by_property("adr_number").equal(padded)
                else:
                    adr_filter = (
                        Filter.by_property("adr_number").equal(padded)
                        & Filter.by_property("title").not_equal("Decision Approval Record List")
                    )

            query_vector = self._get_query_vector(query)
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
                filters=adr_filter,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "status": obj.properties.get("status", ""),
                    "section_name": obj.properties.get("section_name", ""),
                    "chunk_type": obj.properties.get("chunk_type", ""),
                    "content": (obj.properties.get("content", "") or "")[:800],
                }
                for obj in results.objects
            ]

        # Principles search tool
        @tool(tree=self.tree)
        async def search_principles(query: str, limit: int = 10) -> list[dict]:
            """Search architecture and governance principles (PCPs).

            Principles are guiding statements with sections: Statement, Rationale,
            Implications. Identifier format: PCP.NN (e.g., PCP.10 = "Eventual
            Consistency by Design").

            PCP number ranges:
            - PCP.10-20: ESA Architecture Principles (data design, consistency, sovereignty)
            - PCP.21-30: Business Architecture Principles (omnichannel, customer, value streams)
            - PCP.31-40: Data Office Governance Principles (data quality, accessibility, AI)

            Decision Approval Records: Files like 0022D contain the approval record
            for PCP.22. Use these for "who approved" queries.

            ID aliases — all of these refer to PCP.22:
            "PCP 22", "pcp-22", "PCP.0022", "principle 22"

            IMPORTANT — Numbering overlap with ADRs:
            Numbers 10-12 and 20-31 exist in BOTH Principles and ADRs. For example:
            - PCP.22 = "Omnichannel Multibrand" (business principle)
            - ADR.22 = "Use priority-based scheduling" (architecture decision)
            If the user says "document 22" or just a number without specifying ADR or PCP,
            search BOTH this collection AND search_architecture_decisions to present both.

            Note: PCP.21-30 are Dutch-language Business Architecture Principles.
            PCP.31-40 are Data Office principles (mix of Dutch and English).

            Query intent patterns:
            - "What are the data governance principles?" → PCP.31-40
            - "What does PCP.10 say?" → lookup PCP.10
            - "List all principles" → use list_all_principles tool instead

            Args:
                query: Search query — use the 4-digit number (e.g., "0022") for ID lookups
                limit: Maximum number of results to return

            Returns:
                List of matching principles with title, content, doc_type
            """
            collection = self._get_collection("Principle")

            # Detect PCP number in query for filter-based lookup
            pcp_match = re.search(r"(?:PCP[.\-\s]?|principle\s+)(0*(\d{1,4}))\b", query, re.IGNORECASE)
            pcp_filter = None
            if pcp_match:
                padded = pcp_match.group(2).zfill(4)
                is_dar_query = bool(re.search(r"\bD\b|approv|DAR|who\s+(?:accepted|approved)", query, re.IGNORECASE))
                if is_dar_query:
                    pcp_filter = Filter.by_property("principle_number").equal(padded)
                else:
                    pcp_filter = (
                        Filter.by_property("principle_number").equal(padded)
                        & Filter.by_property("title").not_equal("Decision Approval Record List")
                    )

            query_vector = self._get_query_vector(query)
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
                filters=pcp_filter,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "section_name": obj.properties.get("section_name", ""),
                    "chunk_type": obj.properties.get("chunk_type", ""),
                    "content": (obj.properties.get("content", "") or "")[:800],
                }
                for obj in results.objects
            ]

        # Policy document search tool
        @tool(tree=self.tree)
        async def search_policies(query: str, limit: int = 5) -> list[dict]:
            """Search data governance and policy documents (DOCX/PDF).

            Policy documents are formal governance policies from the Data Office,
            primarily in Dutch. Topics include: data classification (BIV), information
            governance, data quality, metadata management, privacy, security, data
            lifecycle, and data product management.

            These are NOT ADRs or Principles — they are separate policy documents.
            Owned by the Data Office (DO) team, Data Management department.

            Large documents are automatically chunked (~6000 chars per chunk), so
            multiple results may come from the same document.

            Use this tool when the user asks about:
            - Data governance policies or "beleid" (Dutch for policy)
            - Data classification, BIV classification
            - Compliance, regulatory requirements
            - Data quality, metadata management policies
            - Privacy or security policies

            Do NOT use this tool for ADRs (use search_architecture_decisions) or
            Principles (use search_principles).

            Args:
                query: Search query for policy documents
                limit: Maximum number of results to return

            Returns:
                List of matching policy documents with title, content, file_type
            """
            collection = self._get_collection("PolicyDocument")
            query_vector = self._get_query_vector(query)
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
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
            """List ALL Architectural Decision Records (ADRs) in the system.

            Use this tool (not search_architecture_decisions) when the user wants
            to enumerate or count ADRs rather than search for specific content:
            - "What ADRs exist?", "List all ADRs", "Show me all ADRs"
            - "How many architecture decisions are there?"
            - "What decisions have been documented?"

            Returns all ADRs with title, status (accepted/proposed/deprecated), and filename.
            ADR numbering: ADR.0-2 (meta), ADR.10-12 (standards), ADR.20-31 (energy system).

            Returns:
                Complete list of all ADRs with titles and status
            """
            collection = self._get_collection("ArchitecturalDecision")
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
            """List ALL architecture and governance principles (PCPs) in the system.

            Use this tool (not search_principles) when the user wants to enumerate
            or count principles rather than search for specific content:
            - "What principles exist?", "List all principles"
            - "Show me the governance principles"
            - "How many principles are there?"

            Returns all principles with title and doc_type.
            PCP numbering: PCP.10-20 (ESA), PCP.21-30 (Business), PCP.31-40 (Data Office).

            Returns:
                Complete list of all principles
            """
            collection = self._get_collection("Principle")
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

        # Search documents by team/owner
        @tool(tree=self.tree)
        async def search_by_team(team_name: str, query: str = "", limit: int = 10) -> list[dict]:
            """Search all documents owned by a specific team or workgroup.

            Known teams and what they own:
            - ESA (Energy System Architecture), System Operations dept:
              Owns all ADRs (ADR.0-31) and ESA Principles (PCP.10-20)
            - DO (Data Office), Data Management dept:
              Owns all Policy documents and DO Principles (PCP.31-40)
            - Business Architecture:
              Owns Business Principles (PCP.21-30)

            Searches across ADRs, Principles, and Policies filtered by owner.

            Use this tool when the user asks:
            - "What documents does ESA own?"
            - "Show me Data Office documents"
            - "What are the ESA principles and ADRs?"

            Args:
                team_name: Team name or abbreviation (e.g., "ESA", "DO", "Data Office")
                query: Optional search query to filter within the team's documents
                limit: Maximum number of results per collection

            Returns:
                List of documents with their type, title, and owner info
            """
            results = []
            query_vector = self._get_query_vector(f"{team_name} {query}") if query else None

            # Search ADRs
            try:
                adr_collection = self._get_collection("ArchitecturalDecision")
                if query:
                    adr_results = adr_collection.query.hybrid(
                        query=f"{team_name} {query}",
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
                principle_collection = self._get_collection("Principle")
                if query:
                    principle_results = principle_collection.query.hybrid(
                        query=f"{team_name} {query}",
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
                policy_collection = self._get_collection("PolicyDocument")
                if query:
                    policy_results = policy_collection.query.hybrid(
                        query=f"{team_name} {query}",
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
            base_names = ["Vocabulary", "ArchitecturalDecision", "Principle", "PolicyDocument"]
            stats = {}
            for base_name in base_names:
                full_name = f"{base_name}{self._collection_suffix}"
                if self.client.collections.exists(full_name):
                    collection = self.client.collections.get(full_name)
                    aggregate = collection.aggregate.over_all(total_count=True)
                    stats[base_name] = aggregate.total_count
                else:
                    stats[base_name] = 0
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
        s = self._collection_suffix
        our_collections = collection_names or [
            f"Vocabulary{s}",
            f"ArchitecturalDecision{s}",
            f"Principle{s}",
            f"PolicyDocument{s}",
        ]

        # Inject active skill content into the Tree's atlas so it reaches
        # all ElysiaChainOfThought prompts, including cited_summarize
        skill_content = _get_skill_content(question)
        if skill_content:
            self.tree.tree_data.atlas.agent_description = skill_content
            logger.debug(f"Injected {len(skill_content)} chars of skill content into Tree atlas")

        try:
            response, objects = self.tree(question, collection_names=our_collections)
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

        # =====================================================================
        # LISTING_PATTERNS: Detect "list all" type queries
        # =====================================================================
        # These patterns catch questions asking to enumerate all items rather
        # than search for specific content. Such queries should bypass the
        # normal search + abstention logic because:
        #   - They don't contain searchable terms (just "what", "list", "show")
        #   - The abstention check fails with 0% coverage
        #   - The correct response is to fetch ALL items, not search
        #
        # Pattern matching is intentionally broad to catch variations like:
        #   - "What ADRs exist in the system?"
        #   - "List all ADRs"
        #   - "Show me the architecture decisions"
        #   - "What are all the ADRs?"
        # =====================================================================
        list_adr_patterns = [
            "what adr", "list adr", "list all adr", "show adr", "show all adr",
            "adrs exist", "all adrs", "all the adr", "architecture decision"
        ]
        if any(pattern in question_lower for pattern in list_adr_patterns):
            logger.info("Detected ADR listing query, using direct fetch")
            return await self._handle_list_adrs_query()

        list_principle_patterns = [
            "what principle", "list principle", "list all principle",
            "show principle", "principles exist", "all principles",
            "all the principle", "governance principle"
        ]
        if any(pattern in question_lower for pattern in list_principle_patterns):
            logger.info("Detected principles listing query, using direct fetch")
            return await self._handle_list_principles_query()

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
                    query=question, vector=query_vector, limit=5, alpha=settings.alpha_vocabulary,
                    filters=content_filter, return_metadata=metadata_request
                )
                for obj in results.objects:
                    all_results.append({
                        "type": "ADR",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("decision", "")[:500],
                        "distance": obj.metadata.distance,
                        "score": obj.metadata.score,
                    })
            except Exception as e:
                logger.warning(f"Error searching ArchitecturalDecision{suffix}: {e}")

        if any(term in question_lower for term in ["principle", "governance", "esa"]):
            try:
                collection = self.client.collections.get(f"Principle{suffix}")
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=5, alpha=settings.alpha_vocabulary,
                    filters=content_filter, return_metadata=metadata_request
                )
                for obj in results.objects:
                    all_results.append({
                        "type": "Principle",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", "")[:500],
                        "distance": obj.metadata.distance,
                        "score": obj.metadata.score,
                    })
            except Exception as e:
                logger.warning(f"Error searching Principle{suffix}: {e}")

        if any(term in question_lower for term in ["policy", "data governance", "compliance"]):
            try:
                collection = self.client.collections.get(f"PolicyDocument{suffix}")
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=5, alpha=settings.alpha_vocabulary,
                    return_metadata=metadata_request
                )
                for obj in results.objects:
                    all_results.append({
                        "type": "Policy",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", "")[:500],
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
                    query=question, vector=query_vector, limit=5, alpha=settings.alpha_vocabulary,
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
                                "content": obj.properties.get("content", obj.properties.get("decision", ""))[:300],
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
        context = "\n\n".join([
            f"[{r.get('type', 'Document')}] {r.get('title', r.get('label', 'Untitled'))}: {r.get('content', r.get('definition', ''))}"
            for r in all_results[:10]
        ])

        # Inject active skill content (domain ontology, quality rules, etc.)
        skill_content = _get_skill_content(question)

        system_prompt = f"""You are AInstein, the Energy System Architecture AI Assistant at Alliander.

Your role is to help architects, engineers, and stakeholders navigate Alliander's energy system architecture knowledge base.

{skill_content}

Guidelines:
- Base your answers strictly on the provided context
- If the information is not in the context, clearly state that you don't have that information
- Be concise but thorough
- When referencing ADRs, include the ADR identifier (e.g., ADR.12)
- When referencing Principles, include the PCP identifier (e.g., PCP.10)
- For vocabulary terms, include the source standard (e.g., from IEC 61970)
- For technical terms, provide clear explanations"""
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

    # =========================================================================
    # LISTING QUERY HANDLERS (uvloop fallback)
    # =========================================================================
    #
    # CONTEXT: On Linux systems, uvloop is commonly used as the default asyncio
    # event loop for better performance. However, the Elysia library attempts to
    # patch the event loop and does not support uvloop, causing this error:
    #
    #   "Elysia tree failed: Can't patch loop of type <class 'uvloop.Loop'>"
    #
    # When this happens, the system falls back to _direct_query(), which performs
    # keyword-based searches. However, "list all" type queries (e.g., "What ADRs
    # exist?") don't work well with keyword search because:
    #
    #   1. The query terms like "adrs", "exist", "system" are not typically
    #      found in ADR document content
    #   2. The abstention logic checks for query term coverage and finds 0%
    #   3. The system incorrectly abstains from answering
    #
    # SOLUTION: These helper methods detect "list all" type queries and handle
    # them directly by fetching all documents from the collection, bypassing
    # the search + abstention logic entirely.
    #
    # MANUAL IMPLEMENTATION: If you need to apply this fix manually:
    #   1. Add _handle_list_adrs_query() and _handle_list_principles_query()
    #   2. Modify _direct_query() to detect listing patterns at the start
    #   3. See the LISTING_PATTERNS comments for the detection logic
    # =========================================================================

    async def _handle_list_adrs_query(self) -> tuple[str, list[dict]]:
        """Handle 'list all ADRs' type queries directly.

        This method is called when the Elysia tree fails (e.g., due to uvloop
        incompatibility) and the user asks a listing question like:
        - "What ADRs exist in the system?"
        - "List all architecture decisions"
        - "Show me all ADRs"

        Instead of doing a keyword search (which fails due to 0% term coverage),
        this fetches all ADR documents directly from the collection.

        Returns:
            Tuple of (formatted response text, list of ADR objects)
        """
        suffix = "_OpenAI" if settings.llm_provider == "openai" else ""
        all_results = []

        try:
            collection = self.client.collections.get(f"ArchitecturalDecision{suffix}")
            results = collection.query.fetch_objects(
                limit=100,
                return_properties=["title", "status", "file_path"],
            )

            for obj in results.objects:
                title = obj.properties.get("title", "")
                file_path = obj.properties.get("file_path", "")
                # Skip template documents
                if "template" in title.lower() or "template" in file_path.lower():
                    continue
                all_results.append({
                    "type": "ADR",
                    "title": title,
                    "status": obj.properties.get("status", ""),
                    "file": file_path.split("/")[-1] if file_path else "",
                })

            # Sort by filename for consistent ordering
            all_results = sorted(all_results, key=lambda x: x.get("file", ""))

        except Exception as e:
            logger.warning(f"Error listing ADRs: {e}")
            return "I encountered an error while retrieving the ADR list.", []

        if not all_results:
            return "No Architectural Decision Records (ADRs) were found in the knowledge base.", []

        # Format response
        response_lines = [f"I found {len(all_results)} Architectural Decision Records (ADRs):\n"]
        for adr in all_results:
            status_badge = f"[{adr['status']}]" if adr.get('status') else ""
            response_lines.append(f"- **{adr['title']}** {status_badge}")

        return "\n".join(response_lines), all_results

    async def _handle_list_principles_query(self) -> tuple[str, list[dict]]:
        """Handle 'list all principles' type queries directly.

        This method is called when the Elysia tree fails (e.g., due to uvloop
        incompatibility) and the user asks a listing question like:
        - "What principles exist?"
        - "List all governance principles"
        - "Show me the architecture principles"

        Instead of doing a keyword search (which fails due to 0% term coverage),
        this fetches all principle documents directly from the collection.

        Returns:
            Tuple of (formatted response text, list of principle objects)
        """
        suffix = "_OpenAI" if settings.llm_provider == "openai" else ""
        all_results = []

        try:
            collection = self.client.collections.get(f"Principle{suffix}")
            results = collection.query.fetch_objects(
                limit=100,
                return_properties=["title", "doc_type"],
            )

            for obj in results.objects:
                all_results.append({
                    "type": "Principle",
                    "title": obj.properties.get("title", ""),
                    "doc_type": obj.properties.get("doc_type", ""),
                })

        except Exception as e:
            logger.warning(f"Error listing principles: {e}")
            return "I encountered an error while retrieving the principles list.", []

        if not all_results:
            return "No principles were found in the knowledge base.", []

        # Format response
        response_lines = [f"I found {len(all_results)} principles:\n"]
        for principle in all_results:
            doc_type = f"({principle['doc_type']})" if principle.get('doc_type') else ""
            response_lines.append(f"- **{principle['title']}** {doc_type}")

        return "\n".join(response_lines), all_results

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
