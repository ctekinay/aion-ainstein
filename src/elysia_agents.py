"""Elysia-based agentic RAG system for AION-AINSTEIN.

Uses Weaviate's Elysia framework for decision tree-based tool selection
and agentic query processing.
"""

import logging
import time
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

# Hardcoded fallbacks for when skills framework is unavailable or disabled
_DEFAULT_DISTANCE_THRESHOLD = 0.5
_DEFAULT_RETRIEVAL_LIMITS = {"adr": 8, "principle": 6, "policy": 4, "vocabulary": 4}
_DEFAULT_TRUNCATION = {"content_max_chars": 800, "elysia_content_chars": 500,
                       "elysia_summary_chars": 300, "max_context_results": 10}


def _get_skill_config(getter_name: str, default):
    """Read a config value from rag-quality-assurance thresholds.

    Falls back to the provided default if the skill registry fails to load
    or the rag-quality-assurance skill is disabled.
    """
    if not _SKILLS_AVAILABLE:
        return default
    try:
        registry = get_skill_registry()
        entry = registry.get_skill_entry("rag-quality-assurance")
        if entry is None or not entry.enabled:
            return default
        return getattr(registry.loader, getter_name)("rag-quality-assurance")
    except Exception:
        return default


def _get_distance_threshold() -> float:
    return _get_skill_config("get_abstention_thresholds", _DEFAULT_DISTANCE_THRESHOLD)


def _get_retrieval_limits() -> dict[str, int]:
    return _get_skill_config("get_retrieval_limits", _DEFAULT_RETRIEVAL_LIMITS)


def _get_truncation() -> dict[str, int]:
    return _get_skill_config("get_truncation", _DEFAULT_TRUNCATION)


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

        # Limit: 4 iterations covers the most complex realistic pattern
        # (search 3 collections + summarize). Default 5 allows the Tree
        # to loop on the same tool when cited_summarize doesn't signal
        # termination. 4 allows all legitimate multi-collection queries
        # while preventing the 5th repetition that's always a loop.
        self.tree.tree_data.recursion_limit = 4

        self._configure_tree_provider()
        self._prop_cache: dict[str, list[str]] = {}
        self._collection_cache: dict[str, object] = {}
        self._register_tools()

    @property
    def _use_openai(self) -> bool:
        """Read Tree's provider at call time so UI switches take effect."""
        return settings.effective_tree_provider == "openai"

    @property
    def _use_openai_collections(self) -> bool:
        """Whether to use OpenAI-embedded Weaviate collections.

        OpenAI collections use Weaviate's text2vec-openai module for
        server-side vectorization, which requires a real OpenAI API key.
        Custom endpoints (GitHub Models, Azure OpenAI) can't be used by
        Weaviate's vectorizer, so we fall back to local collections with
        client-side embeddings.
        """
        return self._use_openai and not settings.openai_base_url

    @property
    def _collection_suffix(self) -> str:
        """Collection name suffix — based on embedding provider, not LLM."""
        return "_OpenAI" if self._use_openai_collections else ""

    def _configure_tree_provider(self):
        """Force Elysia Tree to use AInstein's configured LLM provider/model.

        Elysia's smart_setup() auto-detects OPENAI_API_KEY and defaults to
        gpt-4.1/gpt-4.1-mini, ignoring AInstein's config. This overrides
        Elysia's settings so the Tree uses whatever settings.llm_provider
        and settings.openai_chat_model/ollama_model say.

        Called at init and before each query() to handle runtime provider
        switches from the UI.

        See docs/MONKEY_PATCHES.md #3 for upgrade notes.
        """
        ts = self.tree.settings

        if self._use_openai:
            provider = "openai"
            model = settings.effective_tree_model
            api_base = getattr(settings, 'openai_base_url', None)
        else:
            # Use ollama_chat (not ollama) so litellm routes to /api/chat
            # instead of /api/generate. The completion endpoint enforces
            # JSON parsing that fails with models like gpt-oss:20b.
            provider = "ollama_chat"
            model = settings.effective_tree_model
            api_base = settings.ollama_url

        current = (provider, model, api_base)
        if getattr(self, '_last_tree_config', None) == current:
            return

        ts.BASE_PROVIDER = provider
        ts.BASE_MODEL = model
        ts.COMPLEX_PROVIDER = provider
        ts.COMPLEX_MODEL = model
        if api_base:
            ts.MODEL_API_BASE = api_base

        # Reset Elysia's cached LM objects so they reload from new settings.
        # These are private lazy-loaded attributes — see MONKEY_PATCHES.md #3.
        self.tree._base_lm = None
        self.tree._complex_lm = None

        # Invalidate collection cache — provider change may change _collection_suffix
        if hasattr(self, '_collection_cache'):
            self._collection_cache.clear()

        self._last_tree_config = current
        logger.info(
            f"Tree provider configured: {provider}/{model}"
            + (f" via {api_base}" if api_base else "")
        )

    # Properties that are never useful in tool results: full_text is a
    # redundant copy of the entire document, content_hash is an internal
    # deduplication key.
    _EXCLUDED_PROPS = frozenset({"full_text", "content_hash"})

    def _get_collection(self, base_name: str):
        """Get a Weaviate collection with the correct provider suffix.

        Checks existence and falls back to base collection (without suffix)
        if the suffixed version doesn't exist. Caches validated handles.

        Args:
            base_name: Base collection name (e.g., "Vocabulary")

        Returns:
            Weaviate collection object
        """
        full_name = f"{base_name}{self._collection_suffix}"

        if full_name in self._collection_cache:
            return self._collection_cache[full_name]

        if self.client.collections.exists(full_name):
            coll = self.client.collections.get(full_name)
        elif self._collection_suffix and self.client.collections.exists(base_name):
            logger.warning(
                f"Collection {full_name} not found, falling back to {base_name}"
            )
            coll = self.client.collections.get(base_name)
        else:
            raise ValueError(f"Collection {full_name} does not exist in Weaviate")

        self._collection_cache[full_name] = coll
        return coll

    def _get_return_props(self, collection) -> list[str]:
        """Get returnable property names from a collection's schema.

        Discovers properties dynamically from the Weaviate schema and caches
        them per collection. Excludes internal fields (full_text, content_hash)
        that are never useful in tool results.
        """
        name = collection.name
        if name not in self._prop_cache:
            schema_props = collection.config.get().properties
            self._prop_cache[name] = [
                p.name for p in schema_props
                if p.name not in self._EXCLUDED_PROPS
            ]
        return self._prop_cache[name]

    def _build_result(self, obj, props: list[str], content_limit: int = 0) -> dict:
        """Build a result dict from a Weaviate object using dynamic properties.

        Returns all schema properties. Applies content_max_chars truncation
        to the 'content' field only; everything else is returned as-is.
        """
        result = {}
        for key in props:
            val = obj.properties.get(key, "")
            if key == "content" and content_limit and isinstance(val, str):
                val = val[:content_limit]
            result[key] = val
        return result

    def _get_query_vector(self, query: str) -> Optional[list[float]]:
        """Compute query embedding for local collections, None for OpenAI collections.

        OpenAI collections use server-side vectorization (text2vec-openai),
        so no client-side vector is needed. Local collections use
        Vectorizer.none() and require client-side embeddings.

        Args:
            query: The search query text

        Returns:
            Embedding vector for local collections, None for OpenAI collections
        """
        if self._use_openai_collections:
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
                List of matching vocabulary concepts with all available metadata
            """
            # Config overrides the LLM's limit parameter — see thresholds.yaml
            limit = _get_retrieval_limits().get("vocabulary", limit)
            collection = self._get_collection("Vocabulary")
            props = self._get_return_props(collection)
            query_vector = self._get_query_vector(query)
            content_limit = _get_truncation().get("content_max_chars", 800)
            t0 = time.perf_counter()
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
                return_properties=props,
            )
            wv_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"[timing] search_vocabulary: weaviate={wv_ms}ms, results={len(results.objects)}")
            return [
                self._build_result(obj, props, content_limit)
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
                List of matching ADRs with all available metadata and truncated content
            """
            # Config overrides the LLM's limit parameter — see thresholds.yaml
            limit = _get_retrieval_limits().get("adr", limit)
            collection = self._get_collection("ArchitecturalDecision")
            props = self._get_return_props(collection)
            content_limit = _get_truncation().get("content_max_chars", 800)
            is_dar_query = bool(re.search(r"\bD\b|approv|DAR|who\s+(?:accepted|approved)", query, re.IGNORECASE))

            # Extract ALL ADR numbers from the query. Handles both:
            # - "ADR.20 through ADR.25" (range with keyword)
            # - "ADR.20 ADR.21 ADR.22 ..." (Tree-expanded list)
            all_adr_numbers = re.findall(
                r"(?:ADR|decision)[.\-\s]?0*(\d{1,4})", query, re.IGNORECASE
            )
            unique_adr_numbers = sorted(set(int(n) for n in all_adr_numbers))

            if len(unique_adr_numbers) >= 2:
                # Multiple ADR numbers — use range filter from min to max.
                # Caveat: "Compare ADR.10 and ADR.35" produces a range that
                # includes all 26 ADRs in between, not just the two asked
                # about. The LLM still sees the original query and should
                # focus on the mentioned documents; the extra data is noise
                # but not harmful.
                start = str(min(unique_adr_numbers)).zfill(4)
                end = str(max(unique_adr_numbers)).zfill(4)
                # WEAVIATE BUG: combining range operators (greater_or_equal /
                # less_or_equal) with not_equal on a *different* property
                # silently drops results. Observed: 80 chunks → 6 when adding
                # title.not_equal("Decision Approval Record List") alongside
                # adr_number range filters. Workaround: apply range filter in
                # Weaviate, do DAR/template exclusion in the Python loop below.
                adr_filter = (
                    Filter.by_property("adr_number").greater_or_equal(start)
                    & Filter.by_property("adr_number").less_or_equal(end)
                )
                t0 = time.perf_counter()
                results = collection.query.fetch_objects(
                    filters=adr_filter, limit=500, return_properties=props,
                )
                wv_ms = int((time.perf_counter() - t0) * 1000)
                logger.info(f"[timing] search_architecture_decisions(range): weaviate={wv_ms}ms, results={len(results.objects)}")
                seen = {}
                for obj in results.objects:
                    fp = obj.properties.get("file_path", "")
                    doc_type = obj.properties.get("doc_type", "")
                    title = obj.properties.get("title", "")
                    if not fp or fp in seen:
                        continue
                    if not is_dar_query:
                        if doc_type in ("adr_approval", "template", "index"):
                            continue
                        if title.startswith("Decision Approval Record"):
                            continue
                    seen[fp] = self._build_result(obj, props, content_limit)
                return sorted(seen.values(), key=lambda x: x.get("file_path", ""))

            # Detect single ADR number (e.g., "ADR.29", "decision 12")
            adr_match = re.search(r"(?:ADR[.\-\s]?)?(0*(\d{1,4}))\b", query, re.IGNORECASE)
            adr_filter = None
            if adr_match:
                padded = adr_match.group(2).zfill(4)
                if is_dar_query:
                    adr_filter = Filter.by_property("adr_number").equal(padded)
                else:
                    adr_filter = (
                        Filter.by_property("adr_number").equal(padded)
                        & Filter.by_property("title").not_equal("Decision Approval Record List")
                    )
            else:
                # No specific ADR number — exclude DARs, templates, and index
                # pages by default. Without this, generic queries like "What ADRs
                # exist?" return approval records alongside actual decisions.
                if not is_dar_query:
                    adr_filter = (
                        Filter.by_property("doc_type").not_equal("adr_approval")
                        & Filter.by_property("doc_type").not_equal("template")
                        & Filter.by_property("doc_type").not_equal("index")
                    )

            query_vector = self._get_query_vector(query)
            t0 = time.perf_counter()
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
                filters=adr_filter,
                return_properties=props,
            )
            wv_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"[timing] search_architecture_decisions(hybrid): weaviate={wv_ms}ms, results={len(results.objects)}")
            return [
                self._build_result(obj, props, content_limit)
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
                List of matching principles with all available metadata and truncated content
            """
            # Config overrides the LLM's limit parameter — see thresholds.yaml
            limit = _get_retrieval_limits().get("principle", limit)
            collection = self._get_collection("Principle")
            props = self._get_return_props(collection)
            content_limit = _get_truncation().get("content_max_chars", 800)
            is_dar_query = bool(re.search(r"\bD\b|approv|DAR|who\s+(?:accepted|approved)", query, re.IGNORECASE))

            # Extract ALL PCP numbers from the query. Handles both:
            # - "PCP.10 through PCP.18" (range with keyword)
            # - "PCP.10 PCP.11 PCP.12 ..." (Tree-expanded list)
            all_pcp_numbers = re.findall(
                r"(?:PCP|principle)[.\-\s]?0*(\d{1,4})", query, re.IGNORECASE
            )
            unique_numbers = sorted(set(int(n) for n in all_pcp_numbers))

            if len(unique_numbers) >= 2:
                # Multiple PCP numbers — use range filter from min to max.
                # Caveat: "Compare PCP.10 and PCP.35" produces a range that
                # includes all 26 PCPs in between, not just the two asked
                # about. The LLM still sees the original query and should
                # focus on the mentioned documents; the extra data is noise
                # but not harmful.
                start = str(min(unique_numbers)).zfill(4)
                end = str(max(unique_numbers)).zfill(4)
                # WEAVIATE BUG: combining range operators (greater_or_equal /
                # less_or_equal) with not_equal on a *different* property
                # silently drops results. Observed: 80 chunks → 6 when adding
                # title.not_equal("Principle Approval Record List") alongside
                # principle_number range filters. Workaround: apply range
                # filter in Weaviate, do DAR exclusion in the Python loop below.
                pcp_filter = (
                    Filter.by_property("principle_number").greater_or_equal(start)
                    & Filter.by_property("principle_number").less_or_equal(end)
                )
                t0 = time.perf_counter()
                results = collection.query.fetch_objects(
                    filters=pcp_filter, limit=500, return_properties=props,
                )
                wv_ms = int((time.perf_counter() - t0) * 1000)
                logger.info(f"[timing] search_principles(range): weaviate={wv_ms}ms, results={len(results.objects)}")
                seen = {}
                for obj in results.objects:
                    pn = obj.properties.get("principle_number", "")
                    title = obj.properties.get("title", "")
                    if not pn or pn in seen:
                        continue
                    if not is_dar_query and title.startswith("Principle Approval Record"):
                        continue
                    seen[pn] = self._build_result(obj, props, content_limit)
                return sorted(seen.values(), key=lambda x: x.get("principle_number", ""))

            # Detect single PCP number (e.g., "PCP.10", "principle 22")
            pcp_match = re.search(r"(?:PCP[.\-\s]?|principle\s+)(0*(\d{1,4}))\b", query, re.IGNORECASE)
            pcp_filter = None
            if pcp_match:
                padded = pcp_match.group(2).zfill(4)
                if is_dar_query:
                    pcp_filter = Filter.by_property("principle_number").equal(padded)
                else:
                    pcp_filter = (
                        Filter.by_property("principle_number").equal(padded)
                        & Filter.by_property("title").not_equal("Decision Approval Record List")
                    )
            else:
                # No specific PCP number — exclude DAR chunks by default.
                # doc_type is unreliable in Principle collection (DARs tagged
                # as "principle"), so use title-based filtering.
                if not is_dar_query:
                    pcp_filter = Filter.by_property("title").not_equal("Principle Approval Record List")

            query_vector = self._get_query_vector(query)
            t0 = time.perf_counter()
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
                filters=pcp_filter,
                return_properties=props,
            )
            wv_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"[timing] search_principles(hybrid): weaviate={wv_ms}ms, results={len(results.objects)}")
            return [
                self._build_result(obj, props, content_limit)
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
                List of matching policy documents with all available metadata and truncated content
            """
            # Config overrides the LLM's limit parameter — see thresholds.yaml
            limit = _get_retrieval_limits().get("policy", limit)
            collection = self._get_collection("PolicyDocument")
            props = self._get_return_props(collection)
            query_vector = self._get_query_vector(query)
            content_limit = _get_truncation().get("content_max_chars", 800)
            t0 = time.perf_counter()
            results = collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=limit,
                alpha=settings.alpha_vocabulary,
                return_properties=props,
            )
            wv_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"[timing] search_policies: weaviate={wv_ms}ms, results={len(results.objects)}")
            return [
                self._build_result(obj, props, content_limit)
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

            Returns all ADRs with all available metadata.
            ADR numbering: ADR.0-2 (meta), ADR.10-12 (standards), ADR.20-31 (energy system).

            Returns:
                Complete list of all ADRs with all available metadata
            """
            collection = self._get_collection("ArchitecturalDecision")
            props = self._get_return_props(collection)
            t0 = time.perf_counter()
            results = collection.query.fetch_objects(
                limit=500,  # High enough to get all chunks
                return_properties=props,
            )
            wv_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"[timing] list_all_adrs: weaviate={wv_ms}ms, chunks={len(results.objects)}")

            # Deduplicate by file_path — each ADR may have multiple chunks.
            # Skip approval records (DARs), templates, and index pages.
            # Uses both doc_type AND title-based filtering as safety net
            # (doc_type can be unreliable — same pattern as list_all_principles).
            content_limit = _get_truncation().get("content_max_chars", 800)
            seen = {}
            for obj in results.objects:
                file_path = obj.properties.get("file_path", "")
                doc_type = obj.properties.get("doc_type", "")
                title = obj.properties.get("title", "")
                if not file_path or file_path in seen:
                    continue
                if doc_type in ("adr_approval", "template", "index"):
                    continue
                if title.startswith("Decision Approval Record"):
                    continue
                seen[file_path] = self._build_result(obj, props, content_limit)

            return sorted(seen.values(), key=lambda x: x.get("file_path", ""))

        # List all principles tool
        @tool(tree=self.tree)
        async def list_all_principles() -> list[dict]:
            """List ALL architecture and governance principles (PCPs) in the system.

            ALWAYS use this tool (never search_principles) when the user wants to see,
            enumerate, or count principles rather than search for specific content:
            - "What principles exist?", "List all principles", "Show all principles"
            - "Show me the governance principles", "Please show them all"
            - "How many principles are there?", "Display all PCPs"

            Returns all principles with all available metadata.
            PCP numbering: PCP.10-20 (ESA), PCP.21-30 (Business), PCP.31-40 (Data Office).

            Returns:
                Complete list of all principles with all available metadata
            """
            collection = self._get_collection("Principle")
            props = self._get_return_props(collection)
            t0 = time.perf_counter()
            results = collection.query.fetch_objects(
                limit=500,  # High enough to get all chunks
                return_properties=props,
            )
            wv_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"[timing] list_all_principles: weaviate={wv_ms}ms, chunks={len(results.objects)}")

            # Deduplicate by principle_number — each PCP may have multiple chunks.
            # Skip approval record (DAR) chunks — they share the same
            # principle_number but have titles starting with
            # "Principle Approval Record List". doc_type is unreliable
            # (ingestion tags them all as "principle").
            content_limit = _get_truncation().get("content_max_chars", 800)
            seen = {}
            for obj in results.objects:
                pn = obj.properties.get("principle_number", "")
                title = obj.properties.get("title", "")
                if not pn or pn in seen:
                    continue
                if title.startswith("Principle Approval Record List"):
                    continue
                seen[pn] = self._build_result(obj, props, content_limit)

            return sorted(seen.values(), key=lambda x: x.get("principle_number", ""))

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
                List of documents with all available metadata filtered by owner
            """
            results = []
            query_vector = self._get_query_vector(f"{team_name} {query}") if query else None
            content_limit = _get_truncation().get("content_max_chars", 800)

            for collection_type, base_name in [
                ("ADR", "ArchitecturalDecision"),
                ("Principle", "Principle"),
                ("Policy", "PolicyDocument"),
            ]:
                try:
                    collection = self._get_collection(base_name)
                    props = self._get_return_props(collection)
                    if query:
                        coll_results = collection.query.hybrid(
                            query=f"{team_name} {query}",
                            vector=query_vector,
                            limit=limit,
                            alpha=settings.alpha_default,
                            return_properties=props,
                        )
                    else:
                        coll_results = collection.query.fetch_objects(
                            limit=limit * 2,
                            return_properties=props,
                        )

                    for obj in coll_results.objects:
                        owner = obj.properties.get("owner_team", "") or obj.properties.get("owner_team_abbr", "")
                        owner_display = obj.properties.get("owner_display", "")
                        if team_name.lower() in owner.lower() or team_name.lower() in owner_display.lower():
                            item = self._build_result(obj, props, content_limit)
                            item["type"] = collection_type
                            results.append(item)
                except Exception as e:
                    logger.warning(f"Error searching {base_name} by team: {e}")

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
            t0 = time.perf_counter()
            for base_name in base_names:
                full_name = f"{base_name}{self._collection_suffix}"
                if self.client.collections.exists(full_name):
                    collection = self.client.collections.get(full_name)
                    aggregate = collection.aggregate.over_all(total_count=True)
                    stats[base_name] = aggregate.total_count
                else:
                    stats[base_name] = 0
            wv_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"[timing] get_collection_stats: weaviate={wv_ms}ms")
            return stats

        logger.info("Registered Elysia tools: vocabulary, ADR, principles, policies, search_by_team")

    async def query(self, question: str, collection_names: Optional[list[str]] = None,
                    event_queue=None) -> tuple[str, list[dict]]:
        """Process a query using Elysia's decision tree.

        Iterates Tree.async_run() directly (bypassing tree.run() which wraps
        it with Rich console rendering). Each yielded result is mapped to a
        typed SSE event and placed on event_queue for real-time streaming.

        Args:
            question: The user's question
            collection_names: Optional list of collection names to focus on
            event_queue: Optional Queue for streaming typed SSE events

        Returns:
            Tuple of (response text, retrieved objects)
        """
        logger.info(f"Elysia processing: {question}")

        # Always specify our collection names to bypass Elysia's metadata collection discovery
        # This avoids gRPC errors from Elysia's internal collections
        s = self._collection_suffix
        requested = collection_names or [
            f"Vocabulary{s}",
            f"ArchitecturalDecision{s}",
            f"Principle{s}",
            f"PolicyDocument{s}",
        ]
        # Validate collections exist — fall back to base name if suffixed missing
        our_collections = []
        for name in requested:
            if self.client.collections.exists(name):
                our_collections.append(name)
            elif s and self.client.collections.exists(name.replace(s, "")):
                fallback = name.replace(s, "")
                logger.warning(f"Collection {name} not found, using {fallback}")
                our_collections.append(fallback)
            else:
                logger.warning(f"Collection {name} not found, skipping")
        if not our_collections:
            raise ValueError("No valid collections found in Weaviate")

        # Inject active skill content into the Tree's atlas so it reaches
        # all ElysiaChainOfThought prompts, including cited_summarize
        skill_content = _get_skill_content(question)
        if skill_content:
            self.tree.tree_data.atlas.agent_description = skill_content
            logger.debug(f"Injected {len(skill_content)} chars of skill content into Tree atlas")

        # Sync Tree's LLM with AInstein's config (handles runtime provider switches)
        self._configure_tree_provider()

        try:
            # Replicate the one setup step from tree.run()
            # See docs/MONKEY_PATCHES.md #2 for upgrade notes
            self.tree.store_retrieved_objects = True

            # Suppress Rich console printing from _evaluate_result() —
            # we get typed data directly from the yielded results
            original_log_level = self.tree.settings.LOGGING_LEVEL_INT
            self.tree.settings.LOGGING_LEVEL_INT = 30

            # Track the last text result — its raw content preserves newlines,
            # unlike conversation_history which joins everything with spaces.
            last_text_content = None

            # Per-iteration timing: track query start and iteration boundaries
            query_start = time.perf_counter()
            iteration_start = query_start
            iteration_num = 0

            async for result in self.tree.async_run(
                question, collection_names=our_collections
            ):
                if result is None:
                    continue

                # Log per-iteration timing on decision boundaries
                rtype = result.get("type")
                if rtype == "tree_update":
                    now = time.perf_counter()
                    if iteration_num > 0:
                        iter_ms = int((now - iteration_start) * 1000)
                        logger.info(f"[timing] tree iteration {iteration_num}: {iter_ms}ms")
                    iteration_num += 1
                    iteration_start = now

                # Capture text from the last text result for the final response
                if rtype == "text":
                    payload = result.get("payload", {})
                    objects_list = payload.get("objects", [])
                    text_parts = [
                        o["text"] for o in objects_list
                        if isinstance(o, dict) and "text" in o
                    ]
                    if text_parts:
                        last_text_content = "\n\n".join(text_parts)

                event = self._map_tree_result_to_event(result)
                if event and event_queue:
                    # Enrich every SSE event with elapsed_ms from query start
                    event["elapsed_ms"] = int((time.perf_counter() - query_start) * 1000)
                    event_queue.put(event)

            # Log final iteration timing
            if iteration_num > 0:
                iter_ms = int((time.perf_counter() - iteration_start) * 1000)
                logger.info(f"[timing] tree iteration {iteration_num}: {iter_ms}ms")

            total_tree_ms = int((time.perf_counter() - query_start) * 1000)
            logger.info(f"[timing] tree total: {total_tree_ms}ms ({iteration_num} iterations)")

            # Restore logging level
            self.tree.settings.LOGGING_LEVEL_INT = original_log_level

            iterations = self.tree.tree_data.num_trees_completed
            limit = self.tree.tree_data.recursion_limit
            if iterations >= limit:
                logger.warning(f"Elysia tree hit recursion limit ({iterations}/{limit})")
            else:
                logger.debug(f"Elysia tree completed in {iterations} iteration(s)")

            objects = self.tree.retrieved_objects

            # Use the last text result directly — it preserves formatting.
            # Fall back to conversation_history only if no text was captured.
            if last_text_content and len(last_text_content) > 20:
                final_response = last_text_content
                logger.debug(f"Using last text result ({len(final_response)} chars)")
            else:
                response = self.tree.tree_data.conversation_history[-1]["content"]
                final_response = response
                logger.debug("Fell back to conversation_history")

        except Exception as e:
            # If Elysia's tree fails, fall back to direct tool execution
            logger.warning(f"Elysia tree failed: {e}, using direct tool execution")
            final_response, objects = await self._direct_query(question)

        return final_response, objects

    def _map_tree_result_to_event(self, result: dict) -> Optional[dict]:
        """Map a Tree async_run() result to an SSE event dict.

        The Tree yields typed dicts with 'type' and 'payload' fields.
        We map these to the SSE event types the frontend expects.
        """
        rtype = result.get("type")
        payload = result.get("payload", {})

        if rtype == "tree_update":
            decision = payload.get("decision", "")
            reasoning = payload.get("reasoning", "")
            return {
                "type": "decision",
                "content": f"Decision: {decision} Reasoning: {reasoning}",
            }

        if rtype == "status":
            text = payload.get("text", "")
            if text:
                return {"type": "status", "content": text}
            return None

        if rtype == "text":
            payload_type = payload.get("type", "")

            # Only show intermediate narration ("response") as thinking steps.
            # Skip "text_with_citations" and "text_with_title" — those are
            # final/structured responses that belong in the answer panel, not
            # the thinking container.  (Showing them caused the "1." bug:
            # the full response was truncated to its first sentence by the
            # frontend, and "1." from a numbered list matched as a sentence.)
            if payload_type != "response":
                return None

            objects_list = payload.get("objects", [])
            text_parts = [
                o["text"] for o in objects_list
                if isinstance(o, dict) and "text" in o
            ]
            content = " ".join(text_parts) if text_parts else ""
            if content:
                return {"type": "assistant", "content": content}
            return None

        # result, completed, etc. — no SSE event needed
        return None

    def _extract_final_response(self, concatenated_response: str) -> str:
        """Extract the final answer from the Tree's retrieved objects.

        Elysia's conversation_history concatenates all intermediate assistant
        responses with the final answer into one string. We scan retrieved_objects
        for the last text-type result (text_with_citations, text_with_title, or
        response) and return just its text content.

        Falls back to the full concatenated response if extraction fails.
        """
        try:
            text_types = {"text_with_citations", "text_with_title", "response"}
            last_text = None

            for obj in self.tree.retrieved_objects:
                if isinstance(obj, dict) and obj.get("type") in text_types:
                    # Reconstruct text from objects list
                    text_parts = []
                    for item in obj.get("objects", []):
                        if isinstance(item, dict) and "text" in item:
                            text_parts.append(item["text"])
                    if text_parts:
                        last_text = " ".join(text_parts)

            if last_text and len(last_text) > 20:
                logger.debug(f"Extracted final response ({len(last_text)} chars) from retrieved_objects")
                return last_text

        except Exception as e:
            logger.warning(f"Failed to extract final response: {e}")

        return concatenated_response

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

        # Determine collection suffix based on embedding provider (not LLM).
        # OpenAI collections need a real OpenAI API key for text2vec-openai.
        # Custom endpoints (GitHub Models) can't be used by Weaviate's vectorizer.
        suffix = self._collection_suffix

        # Single source of truth for embedding logic — see _get_query_vector()
        query_vector = self._get_query_vector(question)

        # Filter to exclude index/template documents
        content_filter = Filter.by_property("doc_type").equal("content")

        # Request metadata for abstention decisions
        metadata_request = MetadataQuery(score=True, distance=True)

        content_limit = _get_truncation().get("content_max_chars", 800)

        # Map collection base names to keyword triggers and type labels
        collection_map = [
            ("ArchitecturalDecision", "ADR", ["adr", "decision", "architecture"]),
            ("Principle", "Principle", ["principle", "governance", "esa"]),
            ("PolicyDocument", "Policy", ["policy", "data governance", "compliance"]),
            ("Vocabulary", "Vocabulary", ["vocab", "concept", "definition", "cim", "iec",
             "what is", "what does", "define", "meaning", "term", "standard", "archimate"]),
        ]

        # Search relevant collections based on keyword triggers
        for base_name, type_label, keywords in collection_map:
            if not any(term in question_lower for term in keywords):
                continue
            try:
                collection = self.client.collections.get(f"{base_name}{suffix}")
                props = self._get_return_props(collection)
                coll_filter = content_filter if base_name != "PolicyDocument" else None
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=5,
                    alpha=settings.alpha_vocabulary,
                    filters=coll_filter, return_metadata=metadata_request,
                    return_properties=props,
                )
                for obj in results.objects:
                    item = self._build_result(obj, props, content_limit)
                    item["type"] = type_label
                    item["distance"] = obj.metadata.distance
                    item["score"] = obj.metadata.score
                    all_results.append(item)
            except Exception as e:
                logger.warning(f"Error searching {base_name}{suffix}: {e}")

        # If no specific collection matched, search all
        if not all_results:
            for base_name, type_label, _ in collection_map:
                try:
                    collection = self.client.collections.get(f"{base_name}{suffix}")
                    props = self._get_return_props(collection)
                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=3,
                        alpha=settings.alpha_vocabulary,
                        return_metadata=metadata_request,
                        return_properties=props,
                    )
                    for obj in results.objects:
                        item = self._build_result(obj, props, content_limit)
                        item["type"] = type_label
                        item["distance"] = obj.metadata.distance
                        item["score"] = obj.metadata.score
                        all_results.append(item)
                except Exception as e:
                    logger.warning(f"Error searching {base_name}{suffix}: {e}")

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

        # Generate response based on Tree's LLM provider
        if settings.effective_tree_provider == "ollama":
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
                        "model": settings.effective_tree_model,
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

        openai_client = OpenAI(**settings.get_openai_client_kwargs())

        # GPT-5.x models use max_completion_tokens instead of max_tokens
        model = settings.effective_tree_model
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
        try:
            collection = self._get_collection("ArchitecturalDecision")
            props = self._get_return_props(collection)
            results = collection.query.fetch_objects(
                limit=500,  # High enough to get all chunks
                return_properties=props,
            )

            # Deduplicate by file_path — each ADR may have multiple chunks.
            # Skip approval records (DARs), templates, and index pages.
            # Uses both doc_type AND title-based filtering as safety net.
            content_limit = _get_truncation().get("content_max_chars", 800)
            seen = {}
            for obj in results.objects:
                file_path = obj.properties.get("file_path", "")
                doc_type = obj.properties.get("doc_type", "")
                title = obj.properties.get("title", "")
                if not file_path or file_path in seen:
                    continue
                if doc_type in ("adr_approval", "template", "index"):
                    continue
                if title.startswith("Decision Approval Record"):
                    continue
                seen[file_path] = self._build_result(obj, props, content_limit)

            all_results = sorted(seen.values(), key=lambda x: x.get("file_path", ""))

        except Exception as e:
            logger.warning(f"Error listing ADRs: {e}")
            return "I encountered an error while retrieving the ADR list.", []

        if not all_results:
            return "No Architectural Decision Records (ADRs) were found in the knowledge base.", []

        # Format response
        response_lines = [f"I found {len(all_results)} Architectural Decision Records (ADRs):\n"]
        for adr in all_results:
            status_badge = f"[{adr.get('status', '')}]" if adr.get('status') else ""
            title = (adr.get('title', '') or '').split(' - ')[0]
            response_lines.append(f"- **{title}** {status_badge}")

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
        try:
            collection = self._get_collection("Principle")
            props = self._get_return_props(collection)
            results = collection.query.fetch_objects(
                limit=500,  # High enough to get all chunks
                return_properties=props,
            )

            # Deduplicate by principle_number — each PCP may have multiple chunks.
            # Skip approval record (DAR) chunks by title (doc_type is unreliable).
            content_limit = _get_truncation().get("content_max_chars", 800)
            seen = {}
            for obj in results.objects:
                pn = obj.properties.get("principle_number", "")
                title = obj.properties.get("title", "")
                if not pn or pn in seen:
                    continue
                if title.startswith("Principle Approval Record List"):
                    continue
                seen[pn] = self._build_result(obj, props, content_limit)

            all_results = sorted(seen.values(), key=lambda x: x.get("principle_number", ""))

        except Exception as e:
            logger.warning(f"Error listing principles: {e}")
            return "I encountered an error while retrieving the principles list.", []

        if not all_results:
            return "No principles were found in the knowledge base.", []

        # Format response
        response_lines = [f"I found {len(all_results)} principles:\n"]
        for principle in all_results:
            pn = principle.get('principle_number', '')
            pcp = f"PCP.{int(pn)}" if pn else ""
            title = (principle.get('title', '') or '').split(' - ')[0]
            status_badge = f"[{principle.get('status', '')}]" if principle.get('status') else ""
            response_lines.append(f"- **{pcp} {title}** {status_badge}")

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
