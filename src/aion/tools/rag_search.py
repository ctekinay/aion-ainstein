"""RAG search toolkit for Weaviate knowledge base queries.

Contains the 9 Weaviate search tools (search_architecture_decisions,
search_principles, search_policies, list_adrs, list_principles,
list_policies, list_dars, search_by_team, get_collection_stats) plus all
supporting helper functions, constants, and config accessors.

All methods are synchronous (Weaviate v4 client is synchronous).
"""

import logging
import re
import time

from weaviate import WeaviateClient
from weaviate.classes.query import Filter

from aion.config import settings
from aion.ingestion.embeddings import embed_text
from aion.text_utils import elapsed_ms

# Skills framework — optional, degrades gracefully
try:
    from aion.skills import get_skill_registry

    _SKILLS_AVAILABLE = True
except ImportError:
    _SKILLS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Hardcoded fallbacks for when skills framework is unavailable or disabled
DEFAULT_DISTANCE_THRESHOLD = 0.5
_DEFAULT_RETRIEVAL_LIMITS = {
    "adr": 8,
    "principle": 6,
    "policy": 4,
    "vocabulary": 4,
}
_DEFAULT_TRUNCATION = {
    "content_max_chars": 800,
    "tool_content_chars": 500,
    "tool_summary_chars": 300,
    "max_context_results": 50,
    "consequences_max_chars": 4000,
    "direct_doc_max_chars": 12000,
    "source_display_limit": 35,
}

# ── Config accessors (read at call time, not registration time) ──


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
        logger.warning("Failed to read skill config '%s', using default", getter_name)
        return default


def _get_distance_threshold() -> float:
    return _get_skill_config("get_abstention_thresholds", DEFAULT_DISTANCE_THRESHOLD)


def _get_retrieval_limits() -> dict[str, int]:
    return _get_skill_config("get_retrieval_limits", _DEFAULT_RETRIEVAL_LIMITS)


def _get_truncation() -> dict[str, int]:
    return _get_skill_config("get_truncation", _DEFAULT_TRUNCATION)


def _get_tree_config() -> dict[str, int]:
    return _get_skill_config("get_tree_config", {"recursion_limit": 6})


def _get_skill_content(query: str, skill_tags: list[str] | None = None) -> str:
    """Get combined skill content for prompt injection.

    Returns all "always" skills. When skill_tags is provided (from the
    Persona), also includes "on_demand" skills whose tags match.
    """
    if not _SKILLS_AVAILABLE:
        return ""
    try:
        return get_skill_registry().get_skill_content(active_tags=skill_tags)
    except Exception:
        logger.warning("Failed to load skill content, running without skills")
        return ""


def _is_permanent_llm_error(exc: Exception) -> bool:
    """Check if an exception represents a permanent LLM configuration error.

    Detects model-not-found (404) and auth failures (401) from OpenAI SDK,
    httpx, and litellm by type name and status code. Uses string-based type
    checking to avoid requiring litellm as a direct import.
    """
    type_name = type(exc).__name__
    if type_name in ("NotFoundError", "AuthenticationError"):
        return True
    # httpx HTTP errors
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 404):
        return True
    # litellm puts status in .status_code directly
    status = getattr(exc, "status_code", None)
    if status in (401, 404):
        return True
    # Check cause chain (litellm wraps the original error)
    if exc.__cause__ and exc.__cause__ is not exc:
        return _is_permanent_llm_error(exc.__cause__)
    return False


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
    if not results:
        return True, "No relevant documents found in the knowledge base."

    distance_threshold = _get_distance_threshold()

    distances = [r.get("distance") for r in results if r.get("distance") is not None]
    if distances:
        min_distance = min(distances)
        if min_distance > distance_threshold:
            return True, (
                f"No sufficiently relevant documents found "
                f"(best match distance: {min_distance:.2f})."
            )

    # Check for specific ADR queries - must find the exact ADR
    adr_match = re.search(r"adr[- ]?0*(\d+)", query.lower())
    if adr_match:
        adr_num = adr_match.group(1).zfill(4)
        adr_found = any(
            f"adr-{adr_num}" in str(r.get("title", "")).lower()
            or f"adr-{adr_num}" in str(r.get("content", "")).lower()
            for r in results
        )
        if not adr_found:
            return True, f"ADR-{adr_num} was not found in the knowledge base."

    # Check for specific PCP queries - must find the exact principle
    pcp_match = re.search(r"pcp[.-]?0*(\d+)", query.lower())
    if pcp_match:
        pcp_num = pcp_match.group(1).zfill(4)
        pcp_found = any(
            str(r.get("principle_number", "")).zfill(4) == pcp_num
            for r in results
        )
        if not pcp_found:
            return True, f"PCP.{int(pcp_num)} was not found in the knowledge base."

    return False, "OK"


def is_general_knowledge_eligible(query: str) -> bool:
    """Check if a query could reasonably be answered from general LLM knowledge.

    Returns True for broad conceptual/methodology questions that don't
    reference specific KB documents or organization-specific context.
    """
    query_lower = query.lower()
    # Specific doc references → NOT eligible (need KB)
    if re.search(r"adr[. -]?\d+|pcp[. -]?\d+|dar[. -]?\d+", query_lower):
        return False
    # Org-specific or first-person org references → NOT eligible
    org_terms = (
        "alliander", "esa ", "esa's", "esa-", "esav",
        "our ", "do we ", "should we ", "can we ",
        "we use", "we have", "we follow", "we recommend", "we decided",
    )
    if any(term in query_lower for term in org_terms):
        return False
    return True


def get_abstention_response(reason: str) -> str:
    """Generate a helpful abstention response."""
    return f"""I couldn't find relevant documents in the knowledge base for this question.

**Reason:** {reason}

**Suggestions:**
- This might be a general best-practices question that doesn't require specific documents — try asking it more broadly.
- Ask about specific ADRs or principles (e.g., "What does ADR.29 say?" or "List all principles").
- For terminology questions, try asking "What is [term]?" to check both the knowledge base and SKOSMOS vocabulary.

If you believe this information should be available, please contact the ESA team to have it added to the knowledge base."""


# ── RAGToolkit class ──

# Max objects for fetch_objects calls (range and exact lookups).
# Higher than typical retrieval limits because chunked documents
# produce multiple objects per logical document.
_FETCH_OBJECTS_LIMIT = 500

# Doc types and title prefixes to exclude from ADR results
_ADR_EXCLUDED_DOC_TYPES = ("adr_approval", "template", "index")
_ADR_EXCLUDED_TITLE_PREFIX = "Decision Approval Record"

# Title prefix to exclude from PCP results
_PCP_EXCLUDED_TITLE_PREFIX = "Principle Approval Record"


def _filter_adr_results(objects, props, content_limit, is_dar_query, build_result_fn):
    """Deduplicate ADR results by file_path and filter out DARs/templates/index."""
    seen = {}
    for obj in objects:
        fp = obj.properties.get("file_path", "")
        if not fp or fp in seen:
            continue
        if not is_dar_query:
            doc_type = obj.properties.get("doc_type", "")
            title = obj.properties.get("title", "")
            if doc_type in _ADR_EXCLUDED_DOC_TYPES:
                continue
            if title.startswith(_ADR_EXCLUDED_TITLE_PREFIX):
                continue
        seen[fp] = build_result_fn(obj, props, content_limit)
    return sorted(seen.values(), key=lambda x: x.get("file_path", ""))


def _filter_pcp_results(objects, props, content_limit, is_dar_query, build_result_fn):
    """Deduplicate PCP results by principle_number and filter out DARs."""
    seen = {}
    for obj in objects:
        pn = obj.properties.get("principle_number", "")
        if not pn or pn in seen:
            continue
        if not is_dar_query:
            title = obj.properties.get("title", "")
            if title.startswith(_PCP_EXCLUDED_TITLE_PREFIX):
                continue
        seen[pn] = build_result_fn(obj, props, content_limit)
    return sorted(seen.values(), key=lambda x: x.get("principle_number", ""))


class RAGToolkit:
    """Weaviate search operations for the 8 RAG tools.

    Holds a WeaviateClient reference plus property/collection caches.
    All methods are synchronous (Weaviate v4 client is synchronous).
    """

    # Properties never useful in tool results
    _EXCLUDED_PROPS = frozenset({"full_text", "content_hash"})

    def __init__(self, client: WeaviateClient):
        self.client = client
        self._prop_cache: dict[str, list[str]] = {}
        self._collection_cache: dict[str, object] = {}

    def _get_collection(self, base_name: str):
        """Get a Weaviate collection by name. Caches validated handles."""
        if base_name in self._collection_cache:
            return self._collection_cache[base_name]

        if not self.client.collections.exists(base_name):
            raise ValueError(
                f"Collection {base_name} does not exist in Weaviate"
            )

        coll = self.client.collections.get(base_name)
        self._collection_cache[base_name] = coll
        return coll

    def _get_return_props(self, collection) -> list[str]:
        """Get returnable property names from a collection's schema.

        Discovers properties dynamically and caches per collection.
        Excludes internal fields (full_text, content_hash).
        """
        name = collection.name
        if name not in self._prop_cache:
            schema_props = collection.config.get().properties
            self._prop_cache[name] = [
                p.name
                for p in schema_props
                if p.name not in self._EXCLUDED_PROPS
            ]
        return self._prop_cache[name]

    def _build_result(
        self, obj, props: list[str], content_limit: int = 0
    ) -> dict:
        """Build a result dict from a Weaviate object using dynamic properties.

        Applies content_max_chars truncation to 'content' only.
        Ownership is authoritative in Weaviate — corrected at ingestion time
        by the ingestion pipeline (see ingestion.py:_override_principle_ownership).
        """
        result = {}
        for key in props:
            val = obj.properties.get(key, "")
            if key == "content" and content_limit and isinstance(val, str):
                val = val[:content_limit]
            result[key] = val
        return result

    def _get_query_vector(self, query: str) -> list[float] | None:
        """Compute query embedding for hybrid search."""
        try:
            return embed_text(query)
        except Exception as e:
            logger.error(f"Failed to compute query embedding: {e}")
            return None

    # ── 8 RAG tool methods ──

    def search_architecture_decisions(
        self, query: str, limit: int = 10, doc_refs: list[str] | None = None
    ) -> list[dict]:
        """Search Architectural Decision Records (ADRs)."""
        doc_refs = doc_refs or []
        limit = _get_retrieval_limits().get("adr", limit)
        collection = self._get_collection("ArchitecturalDecision")
        props = self._get_return_props(collection)
        content_limit = _get_truncation().get("content_max_chars", 800)

        # Use structured doc_refs from the Persona
        adr_refs = [r for r in doc_refs if r.startswith("ADR.")]
        is_dar_query = any(r.endswith("D") for r in adr_refs)
        # DARs are structured approval tables — useless when truncated to 800 chars.
        if is_dar_query:
            content_limit = _get_truncation().get("direct_doc_max_chars", 12000)
        adr_numbers = []
        for ref in adr_refs:
            parts = ref.split(".")
            if len(parts) < 2:
                continue
            num_str = parts[1].replace("D", "")
            try:
                adr_numbers.append(int(num_str))
            except ValueError:
                pass

        if len(adr_numbers) >= 2:
            # Multiple ADR numbers — range filter
            start = str(min(adr_numbers)).zfill(4)
            end = str(max(adr_numbers)).zfill(4)
            adr_filter = (
                Filter.by_property("adr_number").greater_or_equal(start)
                & Filter.by_property("adr_number").less_or_equal(end)
            )
            t0 = time.perf_counter()
            results = collection.query.fetch_objects(
                filters=adr_filter,
                limit=_FETCH_OBJECTS_LIMIT,
                return_properties=props,
            )
            wv_ms = elapsed_ms(t0)
            logger.info(
                f"[timing] search_architecture_decisions(range): "
                f"weaviate={wv_ms}ms, results={len(results.objects)}"
            )
            return _filter_adr_results(
                results.objects, props, content_limit, is_dar_query, self._build_result,
            )

        if len(adr_numbers) == 1:
            # Single ADR number — use fetch_objects (pure filter, no hybrid
            # scoring). Hybrid search with a bare number like "0000" as query
            # text produces zero-relevance results that Weaviate drops.
            # Use direct_doc_max_chars (not content_max_chars) — single-doc
            # lookups should return full content, not a truncated snippet.
            padded = str(adr_numbers[0]).zfill(4)
            adr_filter = Filter.by_property("adr_number").equal(padded)
            direct_limit = _get_truncation().get("direct_doc_max_chars", 12000)
            t0 = time.perf_counter()
            results = collection.query.fetch_objects(
                filters=adr_filter,
                limit=_FETCH_OBJECTS_LIMIT,
                return_properties=props,
            )
            wv_ms = elapsed_ms(t0)
            logger.info(
                f"[timing] search_architecture_decisions(exact): "
                f"weaviate={wv_ms}ms, results={len(results.objects)}"
            )
            return _filter_adr_results(
                results.objects, props, direct_limit, is_dar_query, self._build_result,
            )

        # No specific ADR number — exclude DARs, templates, index
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
        wv_ms = elapsed_ms(t0)
        logger.info(
            f"[timing] search_architecture_decisions(hybrid): "
            f"weaviate={wv_ms}ms, results={len(results.objects)}"
        )
        return [
            self._build_result(obj, props, content_limit)
            for obj in results.objects
        ]

    def search_principles(
        self, query: str, limit: int = 10, doc_refs: list[str] | None = None
    ) -> list[dict]:
        """Search architecture and governance principles (PCPs)."""
        doc_refs = doc_refs or []
        limit = _get_retrieval_limits().get("principle", limit)
        collection = self._get_collection("Principle")
        props = self._get_return_props(collection)
        content_limit = _get_truncation().get("content_max_chars", 800)

        pcp_refs = [r for r in doc_refs if r.startswith("PCP.")]
        is_dar_query = any(r.endswith("D") for r in pcp_refs)
        if is_dar_query:
            content_limit = _get_truncation().get("direct_doc_max_chars", 12000)
        pcp_numbers = []
        for ref in pcp_refs:
            parts = ref.split(".")
            if len(parts) < 2:
                continue
            num_str = parts[1].replace("D", "")
            try:
                pcp_numbers.append(int(num_str))
            except ValueError:
                pass

        if len(pcp_numbers) >= 2:
            start = str(min(pcp_numbers)).zfill(4)
            end = str(max(pcp_numbers)).zfill(4)
            pcp_filter = (
                Filter.by_property("principle_number").greater_or_equal(start)
                & Filter.by_property("principle_number").less_or_equal(end)
            )
            t0 = time.perf_counter()
            results = collection.query.fetch_objects(
                filters=pcp_filter,
                limit=_FETCH_OBJECTS_LIMIT,
                return_properties=props,
            )
            wv_ms = elapsed_ms(t0)
            logger.info(
                f"[timing] search_principles(range): "
                f"weaviate={wv_ms}ms, results={len(results.objects)}"
            )
            return _filter_pcp_results(
                results.objects, props, content_limit, is_dar_query, self._build_result,
            )

        if len(pcp_numbers) == 1:
            # Single PCP number — use fetch_objects (pure filter, no hybrid
            # scoring). Same fix as search_architecture_decisions.
            # Use direct_doc_max_chars for full content on single-doc lookups.
            padded = str(pcp_numbers[0]).zfill(4)
            pcp_filter = Filter.by_property("principle_number").equal(padded)
            direct_limit = _get_truncation().get("direct_doc_max_chars", 12000)
            t0 = time.perf_counter()
            results = collection.query.fetch_objects(
                filters=pcp_filter,
                limit=_FETCH_OBJECTS_LIMIT,
                return_properties=props,
            )
            wv_ms = elapsed_ms(t0)
            logger.info(
                f"[timing] search_principles(exact): "
                f"weaviate={wv_ms}ms, results={len(results.objects)}"
            )
            return _filter_pcp_results(
                results.objects, props, direct_limit, is_dar_query, self._build_result,
            )

        # No specific PCP number — exclude DARs
        pcp_filter = Filter.by_property("title").not_equal(
            "Principle Approval Record List"
        )

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
        wv_ms = elapsed_ms(t0)
        logger.info(
            f"[timing] search_principles(hybrid): "
            f"weaviate={wv_ms}ms, results={len(results.objects)}"
        )
        return [
            self._build_result(obj, props, content_limit)
            for obj in results.objects
        ]

    def search_policies(self, query: str, limit: int = 5) -> list[dict]:
        """Search data governance and policy documents."""
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
        wv_ms = elapsed_ms(t0)
        logger.info(
            f"[timing] search_policies: "
            f"weaviate={wv_ms}ms, results={len(results.objects)}"
        )
        return [
            self._build_result(obj, props, content_limit)
            for obj in results.objects
        ]

    def list_adrs(self) -> list[dict]:
        """List ALL ADRs in the system."""
        collection = self._get_collection("ArchitecturalDecision")
        props = self._get_return_props(collection)
        t0 = time.perf_counter()
        results = collection.query.fetch_objects(
            limit=_FETCH_OBJECTS_LIMIT,
            return_properties=props,
        )
        wv_ms = elapsed_ms(t0)
        logger.info(
            f"[timing] list_adrs: "
            f"weaviate={wv_ms}ms, chunks={len(results.objects)}"
        )

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

    def list_principles(self) -> list[dict]:
        """List ALL principles (PCPs) in the system."""
        collection = self._get_collection("Principle")
        props = self._get_return_props(collection)
        t0 = time.perf_counter()
        results = collection.query.fetch_objects(
            limit=_FETCH_OBJECTS_LIMIT,
            return_properties=props,
        )
        wv_ms = elapsed_ms(t0)
        logger.info(
            f"[timing] list_principles: "
            f"weaviate={wv_ms}ms, chunks={len(results.objects)}"
        )

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

        return sorted(
            seen.values(), key=lambda x: x.get("principle_number", "")
        )

    def list_policies(self) -> list[dict]:
        """List ALL policy documents in the system."""
        collection = self._get_collection("PolicyDocument")
        props = self._get_return_props(collection)
        t0 = time.perf_counter()
        results = collection.query.fetch_objects(
            limit=_FETCH_OBJECTS_LIMIT,
            return_properties=props,
        )
        wv_ms = elapsed_ms(t0)
        logger.info(
            f"[timing] list_policies: "
            f"weaviate={wv_ms}ms, chunks={len(results.objects)}"
        )

        content_limit = _get_truncation().get("content_max_chars", 800)
        seen = {}
        for obj in results.objects:
            file_path = obj.properties.get("file_path", "")
            if not file_path or file_path in seen:
                continue
            result = self._build_result(obj, props, content_limit)
            result.pop("file_path", None)
            result.pop("file_type", None)
            seen[file_path] = result

        return sorted(seen.values(), key=lambda x: x.get("title", ""))

    def list_dars(self) -> list[dict]:
        """List all Decision Approval Records (DARs) from both collections.

        ADR DARs use server-side filter (doc_type == "adr_approval") since the
        ADR collection tags DARs correctly. PCP DARs use client-side title
        filtering because the Principle collection has an ingestion bug where
        DARs are tagged doc_type: "principle" (see CLAUDE.md §6).

        Returns combined list with dar_source field ("ADR" or "PCP").
        """
        # Use direct_doc_max_chars — DARs are approval tables, useless truncated.
        content_limit = _get_truncation().get("direct_doc_max_chars", 12000)
        all_dars = []

        # ADR DARs — server-side filter (ADR collection tags DARs correctly)
        try:
            collection = self._get_collection("ArchitecturalDecision")
            props = self._get_return_props(collection)
            dar_filter = Filter.by_property("doc_type").equal("adr_approval")
            t0 = time.perf_counter()
            results = collection.query.fetch_objects(
                filters=dar_filter,
                limit=_FETCH_OBJECTS_LIMIT,
                return_properties=props,
            )
            wv_ms = elapsed_ms(t0)
            seen = {}
            for obj in results.objects:
                fp = obj.properties.get("file_path", "")
                if not fp or fp in seen:
                    continue
                result = self._build_result(obj, props, content_limit)
                result["dar_source"] = "ADR"
                seen[fp] = result
            adr_dars = sorted(seen.values(), key=lambda x: x.get("file_path", ""))
            logger.info(
                f"[timing] list_dars(ADR): weaviate={wv_ms}ms, "
                f"chunks={len(results.objects)}, dars={len(adr_dars)}"
            )
            all_dars.extend(adr_dars)
        except Exception as e:
            logger.warning(f"list_dars: ADR collection error: {e}")

        # PCP DARs from Principle collection
        try:
            collection = self._get_collection("Principle")
            props = self._get_return_props(collection)
            t0 = time.perf_counter()
            results = collection.query.fetch_objects(
                limit=_FETCH_OBJECTS_LIMIT,
                return_properties=props,
            )
            wv_ms = elapsed_ms(t0)
            seen = {}
            for obj in results.objects:
                pn = obj.properties.get("principle_number", "")
                if not pn or pn in seen:
                    continue
                title = obj.properties.get("title", "")
                if title.startswith(_PCP_EXCLUDED_TITLE_PREFIX):
                    result = self._build_result(obj, props, content_limit)
                    result["dar_source"] = "PCP"
                    seen[pn] = result
            pcp_dars = sorted(seen.values(), key=lambda x: x.get("principle_number", ""))
            logger.info(
                f"[timing] list_dars(PCP): weaviate={wv_ms}ms, "
                f"chunks={len(results.objects)}, dars={len(pcp_dars)}"
            )
            all_dars.extend(pcp_dars)
        except Exception as e:
            logger.warning(f"list_dars: Principle collection error: {e}")

        return all_dars

    def search_by_team(
        self, team_name: str, query: str = "", limit: int = 10
    ) -> list[dict]:
        """Search all documents owned by a specific team."""
        limit = _get_retrieval_limits().get("team_search", limit)
        results = []
        query_vector = (
            self._get_query_vector(f"{team_name} {query}") if query else None
        )
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
                    # Use a high limit to ensure all chunks are scanned.
                    # The per-team filter runs in Python after correction, so
                    # we must fetch everything and filter down ourselves.
                    coll_results = collection.query.fetch_objects(
                        limit=_FETCH_OBJECTS_LIMIT,
                        return_properties=props,
                    )

                for obj in coll_results.objects:
                    # Apply ownership correction before filtering so that
                    # principles with registry-overridden owners (BA, DO, NB-EA,
                    # EA) are checked against corrected values, not the raw
                    # Weaviate value (which is always "ESA" due to index.md).
                    item = self._build_result(obj, props, content_limit)
                    owner = item.get("owner_team", "")
                    abbr = item.get("owner_team_abbr", "")
                    owner_display = item.get("owner_display", "")
                    if (
                        team_name.lower() in owner.lower()
                        or team_name.lower() == abbr.lower()
                        or team_name.lower() in owner_display.lower()
                    ):
                        item["type"] = collection_type
                        results.append(item)
            except Exception as e:
                logger.warning(f"Error searching {base_name} by team: {e}")

        return results

    def get_collection_stats(self) -> dict:
        """Get statistics about all collections."""
        base_names = [
            "ArchitecturalDecision",
            "Principle",
            "PolicyDocument",
        ]
        stats = {}
        t0 = time.perf_counter()
        for base_name in base_names:
            if self.client.collections.exists(base_name):
                collection = self.client.collections.get(base_name)
                aggregate = collection.aggregate.over_all(total_count=True)
                stats[base_name] = aggregate.total_count
            else:
                stats[base_name] = 0
        wv_ms = elapsed_ms(t0)
        logger.info(f"[timing] get_collection_stats: weaviate={wv_ms}ms")
        return stats
