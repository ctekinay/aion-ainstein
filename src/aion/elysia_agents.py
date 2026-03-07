"""Elysia-based agentic RAG system for AInstein.

Uses Weaviate's Elysia framework for decision tree-based tool selection
and agentic query processing.
"""

import logging
import re
import time
from pathlib import Path

from weaviate import WeaviateClient
from weaviate.classes.query import Filter, MetadataQuery

from src.aion.config import settings
from src.aion.tools.archimate import (
    inspect_archimate_model as _inspect_archimate,
)
from src.aion.tools.archimate import (
    merge_archimate_view as _merge_archimate_view,
)
from src.aion.tools.archimate import (
    validate_archimate as _validate_archimate,
)
from src.aion.tools.skosmos import (
    skosmos_concept_details as _skosmos_details,
)
from src.aion.tools.skosmos import (
    skosmos_list_vocabularies as _skosmos_vocabs,
)
from src.aion.tools.skosmos import (
    skosmos_search as _skosmos_search,
)

# Skills framework — optional, degrades gracefully
try:
    from src.aion.skills import get_skill_registry
    _SKILLS_AVAILABLE = True
except ImportError:
    _SKILLS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Hardcoded fallbacks for when skills framework is unavailable or disabled
_DEFAULT_DISTANCE_THRESHOLD = 0.5
_DEFAULT_RETRIEVAL_LIMITS = {"adr": 8, "principle": 6, "policy": 4, "vocabulary": 4}
_DEFAULT_TRUNCATION = {"content_max_chars": 800, "elysia_content_chars": 500,
                       "elysia_summary_chars": 300, "max_context_results": 10}

# Ownership correction for principles. Weaviate's Principle collection stores
# "Energy System Architecture" / "ESA" as owner_team for ALL PCPs because the
# index.md defines a single collection-level ownership block. The actual
# per-PCP ownership is parsed from the registry-index.md source of truth.
# Adding new PCPs or changing ownership only requires editing the registry.
_OWNER_METADATA = {
    "BA": {
        "owner_team": "Business Architecture",
        "owner_team_abbr": "BA",
        "owner_display": "Alliander / Business Architecture Group",
    },
    "DO": {
        "owner_team": "Data Office",
        "owner_team_abbr": "DO",
        "owner_display": "Alliander / Data Office",
    },
    "ESA": {
        "owner_team": "Energy System Architecture",
        "owner_team_abbr": "ESA",
        "owner_display": "Alliander / System Operations / Energy System Architecture",
    },
}


def _load_principle_owners() -> dict[str, str]:
    """Parse registry-index.md to build PCP number → owner abbreviation map.

    Returns e.g. {"0010": "ESA", "0021": "BA", "0035": "DO", "0039": "ESA"}.
    Falls back to empty dict if registry is missing or unparseable.
    """
    registry_path = Path(__file__).resolve().parent.parent.parent / (
        "skills/esa-document-ontology/references/registry-index.md"
    )
    if not registry_path.exists():
        logger.warning(f"Registry not found at {registry_path}, ownership correction disabled")
        return {}

    owners: dict[str, str] = {}
    try:
        for line in registry_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("| PCP."):
                continue
            cols = [c.strip() for c in line.split("|")]
            # cols: ['', 'PCP.XX', 'Title', 'Status', 'Date', 'Owner', '']
            if len(cols) < 6:
                continue
            pcp_id = cols[1]   # "PCP.10"
            owner = cols[5]    # "ESA", "BA", "DO"
            num_str = pcp_id.replace("PCP.", "").zfill(4)
            owners[num_str] = owner
    except Exception as e:
        logger.warning(f"Failed to parse registry-index.md: {e}")
        return {}

    logger.info(f"Loaded ownership for {len(owners)} principles from registry")
    return owners


# Loaded once at import time — registry changes require restart
_PRINCIPLE_OWNERS = _load_principle_owners()



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
from src.aion.weaviate.embeddings import embed_text  # noqa: E402

# Import elysia components
try:
    import elysia  # noqa: F401
    from elysia import Tree, tool
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

        # Patch 1: Remove anti-list instructions from class docstrings.
        _patched_doc = False
        for prompt_cls in [CitedSummarizingPrompt, SummarizingPrompt, TextResponsePrompt]:
            if prompt_cls.__doc__:
                for anti_list in _ANTI_LIST_SENTENCES:
                    if anti_list in prompt_cls.__doc__:
                        prompt_cls.__doc__ = prompt_cls.__doc__.replace(anti_list, _REPLACEMENT)
                        _patched_doc = True
                        break

        # Patch 2: Remove anti-list instruction from CitedSummarizingPrompt's
        # cited_text output field description. The field desc says "do not just
        # list objects" which contradicts our response-formatter skill.
        # DSPy reads field descriptions from json_schema_extra["desc"].
        _patched_field = False
        _FIELD_ANTI_LIST = (
            "Do not just repeat information from the environment. "
            "Create insights, offer suggestions, do not just list objects."
        )
        _FIELD_REPLACEMENT = (
            "Format according to the agent description guidelines. "
            "When the user asks to list or enumerate items, provide the full list."
        )
        for prompt_cls in [CitedSummarizingPrompt, SummarizingPrompt]:
            if "cited_text" in prompt_cls.output_fields:
                field = prompt_cls.output_fields["cited_text"]
                jse = field.json_schema_extra or {}
                desc = jse.get("desc", "")
                if _FIELD_ANTI_LIST in desc:
                    new_desc = desc.replace(_FIELD_ANTI_LIST, _FIELD_REPLACEMENT)
                    jse["desc"] = new_desc
                    field.description = new_desc
                    _patched_field = True

        if _patched_doc:
            logger.info("Patched Elysia prompt docstrings to respect skill formatting rules")
        else:
            logger.warning(
                "CitedSummarizingPrompt docstring changed — "
                "skill formatting may not work. Check elysia-ai version."
            )
        if _patched_field:
            logger.info("Patched CitedSummarizingPrompt cited_text field description")
        else:
            logger.warning(
                "CitedSummarizingPrompt cited_text field description changed — "
                "anti-list instruction may still be present. Check elysia-ai version."
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

        # Default recursion limit — overridden at query time from
        # thresholds.yaml (tree.recursion_limit) so changes take effect
        # without restart. See _get_tree_config().
        self.tree.tree_data.recursion_limit = 6

        self._configure_tree_provider()
        self._prop_cache: dict[str, list[str]] = {}
        self._collection_cache: dict[str, object] = {}
        self._current_doc_refs: list[str] = []
        self._register_tools()

    @property
    def _use_openai_api(self) -> bool:
        """True for any OpenAI-compatible API (GitHub Models or native OpenAI)."""
        return settings.effective_tree_provider in ("github_models", "openai")

    def _configure_tree_provider(self):
        """Force Elysia Tree to use AInstein's configured LLM provider/model.

        Elysia's smart_setup() auto-detects OPENAI_API_KEY and defaults to
        gpt-4.1/gpt-4.1-mini, ignoring AInstein's config. This overrides
        Elysia's settings so the Tree uses whatever the UI/config says.

        Called at init and before each query() to handle runtime provider
        switches from the UI.

        See docs/MONKEY_PATCHES.md #3 for upgrade notes.
        """
        import os

        tree_provider = settings.effective_tree_provider
        model = settings.effective_tree_model
        ts = self.tree.settings

        if self._use_openai_api:
            litellm_provider = "openai"
            kwargs = settings.get_openai_client_kwargs(tree_provider)
            api_base = kwargs.get("base_url")
            # Elysia's ElysiaKeyManager context manager replaces os.environ
            # with its own API_KEYS dict before each LM call. Setting the env
            # var alone is not enough — we must also update the Tree's cached
            # API_KEYS dict so the key survives the context manager swap.
            if kwargs.get("api_key"):
                os.environ["OPENAI_API_KEY"] = kwargs["api_key"]
                self.tree.settings.API_KEYS["openai_api_key"] = kwargs["api_key"]
        else:
            # Use ollama_chat (not ollama) so litellm routes to /api/chat
            # instead of /api/generate. The completion endpoint enforces
            # JSON parsing that fails with models like gpt-oss:20b.
            litellm_provider = "ollama_chat"
            api_base = settings.ollama_url

        # Strip publisher prefix from model ID — Elysia's load_lm() will
        # add its own {provider}/ prefix. GitHub Models catalog IDs use
        # publisher/model format (e.g., "openai/gpt-4.1-mini") which would
        # become "openai/openai/gpt-4.1-mini" without stripping.
        if self._use_openai_api and "/" in model:
            model = model.split("/", 1)[1]

        current = (litellm_provider, model, api_base)
        if getattr(self, '_last_tree_config', None) == current:
            return

        ts.BASE_PROVIDER = litellm_provider
        ts.BASE_MODEL = model
        ts.COMPLEX_PROVIDER = litellm_provider
        ts.COMPLEX_MODEL = model
        if api_base:
            ts.MODEL_API_BASE = api_base

        # Create LM objects directly — Elysia's load_lm() hardcodes
        # max_tokens=8000 which is below DSPy's 16K minimum for reasoning
        # models and far below actual catalog limits (32K-100K).
        import dspy
        full_model_name = f"{litellm_provider}/{model}"
        lm_kwargs = self._get_lm_kwargs(model, api_base)
        lm = dspy.LM(model=full_model_name, **lm_kwargs)
        self.tree._base_lm = lm
        self.tree._complex_lm = lm

        self._last_tree_config = current
        logger.info(
            f"Tree provider configured: {litellm_provider}/{model}"
            + (f" via {api_base}" if api_base else "")
        )

    # Max output tokens per model family from GitHub CoPilot catalog.
    # Source: https://models.github.ai/catalog/models
    # Models not listed here get _DEFAULT_MAX_TOKENS (32K — generous
    # enough for Ollama local models and unknown cloud models).
    _MODEL_MAX_TOKENS = {
        "gpt-5": 100_000,
        "gpt-4.1": 32_768,
        "o3": 100_000,
        "o4-mini": 100_000,
    }
    _DEFAULT_MAX_TOKENS = 32_768

    def _get_lm_kwargs(self, model: str, api_base: str | None) -> dict:
        """Build kwargs for dspy.LM with actual output token limits.

        Elysia's load_lm() hardcodes max_tokens=8000 for all models.
        We bypass it and set the real limits from the model catalog.
        DSPy's LM constructor handles reasoning model detection
        (o1/o3/o4/gpt-5) internally — we just need correct max_tokens.
        """
        kwargs = {}
        if api_base:
            kwargs["api_base"] = api_base

        max_tokens = self._DEFAULT_MAX_TOKENS
        for prefix, tokens in self._MODEL_MAX_TOKENS.items():
            if model.startswith(prefix):
                max_tokens = tokens
                break

        kwargs["max_tokens"] = max_tokens
        return kwargs

    # Properties that are never useful in tool results: full_text is a
    # redundant copy of the entire document, content_hash is an internal
    # deduplication key.
    _EXCLUDED_PROPS = frozenset({"full_text", "content_hash"})

    def _get_collection(self, base_name: str):
        """Get a Weaviate collection by name. Caches validated handles.

        Args:
            base_name: Collection name (e.g., "Vocabulary")

        Returns:
            Weaviate collection object
        """
        if base_name in self._collection_cache:
            return self._collection_cache[base_name]

        if not self.client.collections.exists(base_name):
            raise ValueError(f"Collection {base_name} does not exist in Weaviate")

        coll = self.client.collections.get(base_name)
        self._collection_cache[base_name] = coll
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
        to the 'content' field only. Corrects principle ownership metadata
        (Weaviate stores ESA for all PCPs; BA/DO overrides applied here).
        """
        result = {}
        for key in props:
            val = obj.properties.get(key, "")
            if key == "content" and content_limit and isinstance(val, str):
                val = val[:content_limit]
            result[key] = val

        # Correct ownership for principles using registry data
        pn = result.get("principle_number")
        if pn and pn in _PRINCIPLE_OWNERS:
            owner_abbr = _PRINCIPLE_OWNERS[pn]
            if owner_abbr in _OWNER_METADATA:
                result.update(_OWNER_METADATA[owner_abbr])

        return result

    def _get_query_vector(self, query: str) -> list[float] | None:
        """Compute query embedding for hybrid search.

        All collections use client-side embeddings (Vectorizer.none()),
        so we always compute the vector here.

        Args:
            query: The search query text

        Returns:
            Embedding vector, or None on failure
        """
        try:
            return embed_text(query)
        except Exception as e:
            logger.error(f"Failed to compute query embedding: {e}")
            return None

    def _register_tools(self) -> None:
        """Register custom tools for each knowledge domain."""

        # Vocabulary search is now handled by SKOSMOS tools (skosmos_search,
        # skosmos_concept_details, skosmos_list_vocabularies) which query the
        # live SKOSMOS REST API. The old Weaviate Vocabulary collection has been
        # deleted — it contained stale ingested .ttl data.

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

            # Use structured doc_refs from the Persona instead of regex.
            # The Persona extracts document references in canonical form
            # (e.g., "ADR.29", "ADR.22D") — no regex needed.
            adr_refs = [r for r in self._current_doc_refs if r.startswith("ADR.")]
            is_dar_query = any(r.endswith("D") for r in adr_refs)
            # Strip trailing "D" to get the actual ADR numbers
            adr_numbers = []
            for ref in adr_refs:
                num_str = ref.split(".")[1].replace("D", "")
                try:
                    adr_numbers.append(int(num_str))
                except ValueError:
                    pass

            if len(adr_numbers) >= 2:
                # Multiple ADR numbers — use range filter from min to max.
                # Caveat: "Compare ADR.10 and ADR.35" produces a range that
                # includes all 26 ADRs in between, not just the two asked
                # about. The LLM still sees the original query and should
                # focus on the mentioned documents; the extra data is noise
                # but not harmful.
                start = str(min(adr_numbers)).zfill(4)
                end = str(max(adr_numbers)).zfill(4)
                # WEAVIATE BUG: combining range operators (greater_or_equal /
                # less_or_equal) with not_equal on a *different* property
                # silently drops results. Workaround: apply range filter in
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

            if len(adr_numbers) == 1:
                # Single ADR number — exact filter
                padded = str(adr_numbers[0]).zfill(4)
                if is_dar_query:
                    adr_filter = Filter.by_property("adr_number").equal(padded)
                else:
                    adr_filter = (
                        Filter.by_property("adr_number").equal(padded)
                        & Filter.by_property("title").not_equal("Decision Approval Record List")
                    )
            else:
                # No specific ADR number in doc_refs — exclude DARs, templates,
                # and index pages by default. Without this, generic queries like
                # "What ADRs exist?" return approval records alongside decisions.
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

            # Use structured doc_refs from the Persona instead of regex.
            # The Persona extracts document references in canonical form
            # (e.g., "PCP.22", "PCP.10D") — no regex needed.
            pcp_refs = [r for r in self._current_doc_refs if r.startswith("PCP.")]
            is_dar_query = any(r.endswith("D") for r in pcp_refs)
            # Strip trailing "D" to get the actual PCP numbers
            pcp_numbers = []
            for ref in pcp_refs:
                num_str = ref.split(".")[1].replace("D", "")
                try:
                    pcp_numbers.append(int(num_str))
                except ValueError:
                    pass

            if len(pcp_numbers) >= 2:
                # Multiple PCP numbers — use range filter from min to max.
                # Caveat: "Compare PCP.10 and PCP.35" produces a range that
                # includes all 26 PCPs in between, not just the two asked
                # about. The LLM still sees the original query and should
                # focus on the mentioned documents; the extra data is noise
                # but not harmful.
                start = str(min(pcp_numbers)).zfill(4)
                end = str(max(pcp_numbers)).zfill(4)
                # WEAVIATE BUG: combining range operators (greater_or_equal /
                # less_or_equal) with not_equal on a *different* property
                # silently drops results. Workaround: apply range filter in
                # Weaviate, do DAR exclusion in the Python loop below.
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

            if len(pcp_numbers) == 1:
                # Single PCP number — exact filter
                padded = str(pcp_numbers[0]).zfill(4)
                if is_dar_query:
                    pcp_filter = Filter.by_property("principle_number").equal(padded)
                else:
                    pcp_filter = (
                        Filter.by_property("principle_number").equal(padded)
                        & Filter.by_property("title").not_equal("Decision Approval Record List")
                    )
            else:
                # No specific PCP number in doc_refs — exclude DAR chunks
                # by default. doc_type is unreliable in Principle collection
                # (DARs tagged as "principle"), so use title-based filtering.
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

            Policy documents are formal governance DOCX/PDF files from the Data Office
            (DO) and Corporate Governance (CG), primarily in Dutch. Topics include:
            data classification (BIV), information governance, data quality, metadata
            management, privacy, security, data lifecycle, and data product management.

            These are NOT ADRs or Principles — they are separate policy documents.
            Owned by the Data Office (DO) and Corporate Governance (CG) teams.

            Large documents are automatically chunked (~6000 chars per chunk), so
            multiple results may come from the same document.

            Use this tool ONLY for searching specific policy content, NOT for listing.
            To enumerate or count policies, use list_all_policies instead.

            Use this tool when the user asks about:
            - Data governance policies or "beleid" (Dutch for policy)
            - Data classification, BIV classification
            - Compliance, regulatory requirements
            - Data quality, metadata management policies
            - Privacy or security policies

            Do NOT use this tool for ADRs (use search_architecture_decisions) or
            Principles (use search_principles). PCP.31-38 are Data Office PRINCIPLES
            (architectural guidance), not POLICIES (governance rules) — do not confuse
            them.

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

        # List all policies tool
        @tool(tree=self.tree)
        async def list_all_policies() -> list[dict]:
            """List ALL policy documents in the system.

            ALWAYS use this tool (never search_policies) when the user wants to
            see, enumerate, or count policy documents rather than search for
            specific content:
            - "What policies exist?", "List all policies", "Show all policies"
            - "What policy documents do we have?", "How many policies are there?"
            - "What data governance policies are there?"

            Returns one entry per policy document with title, owner_team, and
            file_type. Policies are formal governance DOCX/PDF files — NOT
            principles (PCPs) or ADRs.

            Returns:
                Complete list of all policy documents with all available metadata
            """
            collection = self._get_collection("PolicyDocument")
            props = self._get_return_props(collection)
            t0 = time.perf_counter()
            results = collection.query.fetch_objects(
                limit=500,  # High enough to get all chunks
                return_properties=props,
            )
            wv_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"[timing] list_all_policies: weaviate={wv_ms}ms, chunks={len(results.objects)}")

            # Deduplicate by file_path — each policy may have multiple chunks
            # from structure-aware chunking. Return one entry per source document.
            # Strip file_path and file_type from returned dicts: policies have no
            # numbered ID (unlike adr_number/principle_number), so the Tree
            # summarizer would show raw filesystem paths and file extensions to
            # users if these fields were present. Users should see only title
            # and owner_team.
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
            limit = _get_retrieval_limits().get("team_search", limit)
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
            base_names = ["ArchitecturalDecision", "Principle", "PolicyDocument"]
            stats = {}
            t0 = time.perf_counter()
            for base_name in base_names:
                if self.client.collections.exists(base_name):
                    collection = self.client.collections.get(base_name)
                    aggregate = collection.aggregate.over_all(total_count=True)
                    stats[base_name] = aggregate.total_count
                else:
                    stats[base_name] = 0
            wv_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"[timing] get_collection_stats: weaviate={wv_ms}ms")
            return stats

        # -----------------------------------------------------------------
        # ArchiMate tools — model validation, inspection, view merging
        # -----------------------------------------------------------------

        @tool(tree=self.tree)
        async def validate_archimate(xml_content: str) -> dict:
            """Validate an ArchiMate 3.2 Open Exchange XML model.

            Checks element types, relationship types, and source/target
            compatibility against the ArchiMate 3.2 specification.

            Use this tool when:
            - The user asks you to generate an ArchiMate model (validate
              your own output before presenting it)
            - The user provides XML and asks if it's valid
            - After fixing errors in a previously invalid model

            Do NOT use this tool for:
            - Searching the knowledge base for architecture documents — use
              search_architecture_decisions instead
            - Vocabulary lookups — use skosmos_search instead

            Args:
                xml_content: Complete ArchiMate XML string

            Returns:
                Dict with valid (bool), element_count, relationship_count,
                errors (list), and warnings (list)
            """
            return _validate_archimate(xml_content)

        @tool(tree=self.tree)
        async def inspect_archimate_model(xml_content: str) -> dict:
            """Inspect an ArchiMate model to understand its structure.

            Parses an ArchiMate XML model and returns a summary of its
            elements by layer, relationships by type, existing views,
            and element/relationship indices.

            Use this tool when:
            - The user asks what's in an existing model
            - You need to understand a model's structure before adding a view
            - The user asks about elements, layers, or relationships in a model

            Do NOT use this tool for:
            - Validating a model — use validate_archimate instead
            - Searching the knowledge base — use search tools instead

            Args:
                xml_content: Complete ArchiMate XML string

            Returns:
                Dict with model_name, element_count, elements_by_layer,
                relationships_by_type, existing_views, element_index,
                relationship_index
            """
            return _inspect_archimate(xml_content)

        @tool(tree=self.tree)
        async def merge_archimate_view(model_xml: str, fragment_xml: str) -> dict:
            """Merge an ArchiMate view fragment into an existing model.

            Takes a base model and a view fragment, deduplicates elements
            and relationships by identifier, and appends new views.

            Use this tool when:
            - The user asks to add a view to an existing model
            - You generated a view fragment and need to combine it with
              the base model

            Do NOT use this tool for:
            - Creating a model from scratch — generate the full XML directly
            - Validating XML — use validate_archimate instead

            Args:
                model_xml: The base ArchiMate model XML
                fragment_xml: The view fragment XML to merge in

            Returns:
                Dict with success (bool), merged_xml, elements_added,
                relationships_added, views_added, error (str or None)
            """
            return _merge_archimate_view(model_xml, fragment_xml)

        # -----------------------------------------------------------------
        # SKOSMOS tools — vocabulary search, concept details, vocab listing
        # -----------------------------------------------------------------

        @tool(tree=self.tree)
        async def skosmos_search(
            query: str,
            lang: str = "en",
            vocab: str | None = None,
            max_results: int = 10,
        ) -> dict:
            """Search SKOSMOS for vocabulary terms by label matching.

            This is step 1 of a two-step lookup. Search results contain
            prefLabel, altLabel, vocab, and URI — but NOT the full definition.
            After finding a match, you MUST call skosmos_concept_details with
            the result's uri and vocab to retrieve the actual definition.

            SKOSMOS provides authoritative term definitions from IEC, ENTSO-E,
            and EU vocabularies. Uses exact and pattern-based label matching —
            more precise than Weaviate vector similarity for term lookups.

            Use this tool when the user asks:
            - "What is [term]?" or "Define [term]"
            - About IEC standard terminology or abbreviations
            - For precise vocabulary definitions (active power, reactive power)
            - To compare or distinguish domain terms

            Do NOT use this tool for:
            - Searching ADRs, PCPs, or policy documents — use the Weaviate
              search tools instead
            - General architecture questions — use search_architecture_decisions

            IMPORTANT: This tool finds terms but does NOT return definitions.
            Always follow up with skosmos_concept_details to get the definition.

            Args:
                query: The term or phrase to search for
                lang: Language code (default "en")
                vocab: Optional vocabulary ID to limit search to
                max_results: Maximum results to return (default 10)

            Returns:
                Dict with results (list of concept dicts with uri, prefLabel,
                altLabel, vocab) and total_results. Definition field will be
                empty — use skosmos_concept_details to get it.
            """
            return _skosmos_search(query, lang=lang, vocab=vocab, max_results=max_results)

        @tool(tree=self.tree)
        async def skosmos_concept_details(
            uri: str,
            vocab: str,
            lang: str = "en",
        ) -> dict:
            """Get the full definition and details for a SKOS concept by URI.

            This is step 2 of vocabulary lookup. ALWAYS call this after
            skosmos_search returns results — the search endpoint does NOT
            return definitions. This tool fetches the complete concept record
            including the formal definition, broader/narrower hierarchy,
            related concepts, and all labels.

            Do NOT use this tool for:
            - Initial term searches — use skosmos_search first to find URIs

            IMPORTANT: Both uri and vocab are REQUIRED. Get them from
            skosmos_search results — each result has "uri" and "vocab" fields.

            Args:
                uri: The concept URI (from skosmos_search results "uri" field)
                vocab: The vocabulary ID (from skosmos_search results "vocab" field, e.g. "EURLEX", "ESAV")
                lang: Language code (default "en")

            Returns:
                Dict with uri, prefLabel, altLabels, definition, broader,
                narrower, related, scopeNote, notation
            """
            return _skosmos_details(uri, vocab=vocab, lang=lang)

        @tool(tree=self.tree)
        async def skosmos_list_vocabularies(lang: str = "en") -> dict:
            """List all vocabularies available in SKOSMOS.

            Returns vocabulary IDs, titles, descriptions, and concept counts
            for all loaded vocabularies (IEC, ENTSO-E, EU, ESA, etc.).

            Use this tool when:
            - The user asks "What vocabularies do you have?"
            - The user asks about available terminology sources
            - You need to find the right vocab ID for a skosmos_search

            Args:
                lang: Language code (default "en")

            Returns:
                Dict with vocabularies list (id, title, description,
                concept_count, languages)
            """
            return _skosmos_vocabs(lang=lang)

        # Artifact tools — allow the Tree to save and load generated content
        # (ArchiMate XML, etc.) across turns for iterative refinement.
        @tool(tree=self.tree)
        async def save_artifact(filename: str, content: str, content_type: str, summary: str = "") -> dict:
            """ALWAYS call this tool after generating any structured output
            (ArchiMate XML, JSON schemas, configuration files, etc.).
            Call save_artifact BEFORE writing the text response — the artifact
            must be persisted so the user can request refinements in follow-up
            messages. If you skip this tool, the generated content will be lost
            between turns.

            Args:
                filename: Descriptive filename (e.g., "oauth2-model.archimate.xml",
                    "data-governance-policy.json")
                content: The full artifact content
                content_type: MIME-like type (e.g., "archimate/xml", "application/json")
                summary: Brief description (e.g., "28 elements, 33 relationships")

            Returns:
                Dict with artifact_id and filename
            """
            from src.aion.chat_ui import save_artifact as _save

            conv_id = self._current_conversation_id
            if not conv_id:
                return {"error": "No conversation context — artifact not saved"}

            artifact_id = _save(conv_id, filename, content, content_type, summary)

            # Emit artifact SSE event so the frontend renders a download card
            if self._current_event_queue:
                self._current_event_queue.put({
                    "type": "artifact",
                    "artifact_id": artifact_id,
                    "filename": filename,
                    "content_type": content_type,
                    "summary": summary,
                })

            return {"artifact_id": artifact_id, "filename": filename, "summary": summary}

        @tool(tree=self.tree)
        async def get_artifact(content_type: str = "") -> dict:
            """ALWAYS call this tool FIRST when the user wants to refine,
            modify, review, compare, or analyze a previously generated or
            uploaded artifact. This loads the full content from the previous
            turn so you can work with the complete artifact instead of
            reconstructing it from memory. Without calling this tool,
            requests involving artifacts will produce incomplete or
            fragmented output.

            Args:
                content_type: Optional filter (e.g., "archimate/xml",
                    "application/json"). Leave empty for any type.

            Returns:
                Dict with filename, content, content_type, summary — or error
            """
            from src.aion.chat_ui import get_latest_artifact

            conv_id = self._current_conversation_id
            logger.info(f"get_artifact called: conversation_id={conv_id}, content_type={content_type!r}")
            if not conv_id:
                logger.warning("get_artifact: no conversation_id set")
                return {"error": "No conversation context — cannot load artifact"}

            artifact = get_latest_artifact(conv_id, content_type=content_type or None)
            if not artifact:
                logger.warning(f"get_artifact: no artifact found for conversation_id={conv_id}")
                return {"error": "No artifact found in this conversation"}

            content = artifact.get("content", "")
            logger.info(
                f"get_artifact: found {artifact['filename']} "
                f"({len(content)} chars) for {conv_id}"
            )

            # Inject the full artifact content into the Tree's atlas so it
            # persists across all LLM iterations. Returning 10KB+ content
            # as a tool result gets lost between Elysia's chain-of-thought
            # iterations; injecting into the atlas makes it part of the
            # system context that every subsequent LLM call sees.
            current_atlas = self.tree.tree_data.atlas.agent_description or ""
            artifact_block = (
                f"\n\n## LOADED ARTIFACT: {artifact['filename']}\n"
                f"Content type: {artifact['content_type']}\n"
                f"Summary: {artifact.get('summary', 'N/A')}\n\n"
                f"```\n{content}\n```\n"
            )
            self.tree.tree_data.atlas.agent_description = current_atlas + artifact_block
            logger.info(
                f"Injected artifact ({len(content)} chars) into Tree atlas"
            )

            # Return metadata only — the full content is in the atlas
            return {
                "filename": artifact["filename"],
                "content_type": artifact["content_type"],
                "summary": artifact.get("summary", ""),
                "status": "Loaded into context — full content available for modification",
            }

        logger.info("Registered Elysia tools: ADR, principles, policies, search_by_team, archimate(3), skosmos(3), artifacts(2)")

    async def query(self, question: str, collection_names: list[str] | None = None,
                    event_queue=None, skill_tags: list[str] | None = None,
                    doc_refs: list[str] | None = None,
                    conversation_id: str | None = None,
                    artifact_context: str | None = None) -> tuple[str, list[dict]]:
        """Process a query using Elysia's decision tree.

        Iterates Tree.async_run() directly (bypassing tree.run() which wraps
        it with Rich console rendering). Each yielded result is mapped to a
        typed SSE event and placed on event_queue for real-time streaming.

        Args:
            question: The user's question
            collection_names: Optional list of collection names to focus on
            event_queue: Optional Queue for streaming typed SSE events
            doc_refs: Structured document references from the Persona
                (e.g., ["ADR.29"], ["PCP.22", "ADR.12"], [])
            conversation_id: Optional conversation ID for artifact storage
            artifact_context: Pre-built artifact block to inject into atlas
                after skill content. Used for follow-ups that reference a
                previously inspected/generated artifact.

        Returns:
            Tuple of (response text, retrieved objects)
        """
        # Store per-query state so tools can access them via self
        self._current_conversation_id = conversation_id
        self._current_doc_refs = doc_refs or []
        self._current_event_queue = event_queue
        logger.info(f"Elysia processing: {question}")

        # Always specify our collection names to bypass Elysia's metadata collection discovery
        # This avoids gRPC errors from Elysia's internal collections
        requested = collection_names or [
            "ArchitecturalDecision",
            "Principle",
            "PolicyDocument",
        ]
        our_collections = []
        for name in requested:
            if self.client.collections.exists(name):
                our_collections.append(name)
            else:
                logger.warning(f"Collection {name} not found, skipping")
        if not our_collections:
            raise ValueError("No valid collections found in Weaviate")

        # Inject active skill content into the Tree's atlas so it reaches
        # all ElysiaChainOfThought prompts, including cited_summarize.
        # On-demand skills (ArchiMate, SKOSMOS) are only included when
        # the Persona emits matching skill_tags for this query.
        skill_content = _get_skill_content(question, skill_tags=skill_tags)
        if skill_content:
            self.tree.tree_data.atlas.agent_description = skill_content
            logger.debug(
                f"Injected {len(skill_content)} chars of skill content into Tree atlas"
                f" (skill_tags={skill_tags})"
            )

        # Append artifact context AFTER skill content injection (which does a
        # hard overwrite of agent_description). This ensures the artifact
        # survives the skill injection at the line above.
        if artifact_context:
            current = self.tree.tree_data.atlas.agent_description or ""
            self.tree.tree_data.atlas.agent_description = current + artifact_context
            logger.info(f"Injected artifact context ({len(artifact_context)} chars) into Tree atlas")

        # Sync Tree's LLM with AInstein's config (handles runtime provider switches)
        self._configure_tree_provider()

        # Read recursion limit from config at query time (not init time)
        # so changes to thresholds.yaml take effect without restart.
        self.tree.tree_data.recursion_limit = _get_tree_config().get("recursion_limit", 6)

        try:
            # Clear stale state from the previous query — the Tree is a
            # singleton so conversation_history and retrieved_objects persist
            # across queries. Without this reset, the summarizer can reference
            # prior query results ("conversation history bleed").
            self.tree.tree_data.conversation_history = []
            self.tree.retrieved_objects = []

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
            # Permanent LLM errors (model not found, bad API key) must not
            # be swallowed into the degraded _direct_query path.
            if _is_permanent_llm_error(e):
                from src.aion.persona import PermanentLLMError
                raise PermanentLLMError(
                    f"Model error: {e}. Check your model settings."
                ) from e
            # Transient errors: fall back to direct tool execution
            logger.warning(f"Elysia tree failed: {e}, using direct tool execution")
            final_response, objects = await self._direct_query(question)

        return final_response, objects

    def _map_tree_result_to_event(self, result: dict) -> dict | None:
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

        list_policy_patterns = [
            "what polic", "list polic", "list all polic", "show polic",
            "policies exist", "all policies", "all the polic",
            "policy document", "what beleid", "governance polic"
        ]
        if any(pattern in question_lower for pattern in list_policy_patterns):
            logger.info("Detected policy listing query, using direct fetch")
            return await self._handle_list_policies_query()

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
            # Vocabulary search is now handled by SKOSMOS tools, not Weaviate
        ]

        # Search relevant collections based on keyword triggers
        for base_name, type_label, keywords in collection_map:
            if not any(term in question_lower for term in keywords):
                continue
            try:
                collection = self.client.collections.get(base_name)
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
                logger.warning(f"Error searching {base_name}: {e}")

        # If no specific collection matched, search all
        if not all_results:
            for base_name, type_label, _ in collection_map:
                try:
                    collection = self.client.collections.get(base_name)
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
                    logger.warning(f"Error searching {base_name}: {e}")

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
        if self._use_openai_api:
            response_text = await self._generate_with_openai(system_prompt, user_prompt)
        else:
            response_text = await self._generate_with_ollama(system_prompt, user_prompt)

        return response_text, all_results

    async def _generate_with_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using Ollama API.

        Args:
            system_prompt: System instruction
            user_prompt: User's message with context

        Returns:
            Generated response text
        """
        import re
        import time

        import httpx

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

        openai_client = OpenAI(**settings.get_openai_client_kwargs(settings.effective_tree_provider))

        # GPT-5.x models use max_completion_tokens instead of max_tokens
        model = settings.effective_tree_model
        completion_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        # gpt-5.x models use max_completion_tokens; handle publisher/ prefix
        model_base = model.rsplit("/", 1)[-1] if "/" in model else model
        if model_base.startswith("gpt-5"):
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

    async def _handle_list_policies_query(self) -> tuple[str, list[dict]]:
        """Handle 'list all policies' type queries directly.

        This method is called when the Elysia tree fails and the user asks
        a listing question like:
        - "What policies do we have in the system?"
        - "List all policy documents"
        - "What data governance policies are there?"

        Fetches all policy documents from the collection, deduplicates by
        file_path (policies are chunked), and returns a formatted list.

        Returns:
            Tuple of (formatted response text, list of policy objects)
        """
        try:
            collection = self._get_collection("PolicyDocument")
            props = self._get_return_props(collection)
            results = collection.query.fetch_objects(
                limit=500,
                return_properties=props,
            )

            content_limit = _get_truncation().get("content_max_chars", 800)
            seen = {}
            for obj in results.objects:
                file_path = obj.properties.get("file_path", "")
                if not file_path or file_path in seen:
                    continue
                seen[file_path] = self._build_result(obj, props, content_limit)

            all_results = sorted(seen.values(), key=lambda x: x.get("title", ""))

        except Exception as e:
            logger.warning(f"Error listing policies: {e}")
            return "I encountered an error while retrieving the policy list.", []

        if not all_results:
            return "No policy documents were found in the knowledge base.", []

        response_lines = [f"I found {len(all_results)} policy documents:\n"]
        for policy in all_results:
            title = policy.get('title', 'Untitled')
            owner = policy.get('owner_team', '')
            owner_suffix = f" — Owner: {owner}" if owner else ""
            response_lines.append(f"- {title}{owner_suffix}")

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
