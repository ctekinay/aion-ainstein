"""SKOSMOS terminology verification client with local-first approach.

This module provides:
- Local vocabulary loading from TTL files (deterministic, low latency, CI friendly)
- Optional API fallback when local lookup misses
- ABSTAIN logic: only abstain when term cannot be verified (local miss + API miss/fail)

Enterprise-grade approach: If local hit exists, never abstain due to API failure.

Part of Phase 5 implementation (IR0003 Gap A).

Usage:
    from src.weaviate.skosmos_client import get_skosmos_client, TermLookupResult

    client = get_skosmos_client()
    result = client.lookup_term("ACLineSegment")

    if result.found:
        print(f"Found: {result.label} - {result.definition}")
    elif result.should_abstain:
        print(f"ABSTAIN: {result.abstain_reason}")
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Set
import re

import httpx
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SKOS, OWL

from ..config import settings
from ..observability import metrics, get_logger

logger = logging.getLogger(__name__)

# Common namespaces for energy sector vocabularies
IEC = Namespace("http://iec.ch/TC57/")
CIM = Namespace("http://iec.ch/TC57/CIM100#")
ESA = Namespace("https://esa.alliander.com/")


@dataclass
class TermDefinition:
    """A verified terminology definition from SKOSMOS."""
    uri: str
    pref_label: str
    alt_labels: List[str] = field(default_factory=list)
    definition: str = ""
    vocabulary_name: str = ""
    source: str = "local"  # "local" or "api"


@dataclass
class TermLookupResult:
    """Result of a terminology lookup operation.

    Attributes:
        found: Whether the term was found (local or API)
        term: The term that was looked up
        definition: The verified definition (if found)
        source: Where the term was found ("local", "api", or None)
        should_abstain: Whether the system should abstain from answering
        abstain_reason: Human-readable reason for abstention
        latency_ms: Lookup latency in milliseconds
    """
    found: bool
    term: str
    definition: Optional[TermDefinition] = None
    source: Optional[str] = None
    should_abstain: bool = False
    abstain_reason: str = ""
    latency_ms: float = 0.0

    @property
    def label(self) -> str:
        """Get the preferred label (convenience)."""
        return self.definition.pref_label if self.definition else ""

    @property
    def definition_text(self) -> str:
        """Get the definition text (convenience)."""
        return self.definition.definition if self.definition else ""


class LocalVocabularyIndex:
    """In-memory index of SKOS vocabulary terms loaded from TTL files.

    Thread-safe: Uses read-write lock for concurrent access.
    """

    def __init__(self):
        self._terms: Dict[str, TermDefinition] = {}
        self._alt_label_map: Dict[str, str] = {}  # alt_label -> pref_label
        self._loaded = False
        self._lock = threading.RLock()
        self._load_time_ms: float = 0.0
        self._term_count: int = 0
        self._vocabulary_names: Set[str] = set()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def term_count(self) -> int:
        return self._term_count

    @property
    def vocabularies(self) -> Set[str]:
        return self._vocabulary_names.copy()

    def load(self, data_path: Path) -> None:
        """Load all TTL vocabulary files from the data path.

        Args:
            data_path: Directory containing .ttl files
        """
        obs_logger = get_logger("skosmos_client")
        start_time = time.time()

        with self._lock:
            if self._loaded:
                obs_logger.debug("vocabulary_already_loaded")
                return

            ttl_files = list(data_path.glob("*.ttl"))
            obs_logger.info("loading_vocabularies", file_count=len(ttl_files), path=str(data_path))

            for ttl_file in ttl_files:
                try:
                    self._load_file(ttl_file)
                except Exception as e:
                    obs_logger.error("file_load_error", file=ttl_file.name, error=str(e))
                    continue

            self._loaded = True
            self._term_count = len(self._terms)
            self._load_time_ms = (time.time() - start_time) * 1000

            obs_logger.info(
                "vocabulary_load_complete",
                term_count=self._term_count,
                vocabulary_count=len(self._vocabulary_names),
                latency_ms=round(self._load_time_ms, 2)
            )

    def _load_file(self, file_path: Path) -> None:
        """Load a single TTL file into the index."""
        graph = Graph()
        graph.parse(file_path, format="turtle")
        vocabulary_name = file_path.stem
        self._vocabulary_names.add(vocabulary_name)

        # Extract SKOS concepts
        for concept_uri in graph.subjects(RDF.type, SKOS.Concept):
            self._extract_concept(graph, concept_uri, vocabulary_name)

        # Extract OWL classes (many IEC ontologies use OWL)
        for class_uri in graph.subjects(RDF.type, OWL.Class):
            self._extract_owl_class(graph, class_uri, vocabulary_name)

    def _extract_concept(self, graph: Graph, uri: URIRef, vocab_name: str) -> None:
        """Extract a SKOS concept and add to index."""
        pref_label = self._get_label(graph, uri, SKOS.prefLabel)
        if not pref_label:
            return

        alt_labels = self._get_labels(graph, uri, SKOS.altLabel)
        definition = self._get_literal(graph, uri, SKOS.definition)

        term_def = TermDefinition(
            uri=str(uri),
            pref_label=pref_label,
            alt_labels=alt_labels,
            definition=definition,
            vocabulary_name=vocab_name,
            source="local"
        )

        # Index by normalized pref_label
        normalized = self._normalize_term(pref_label)
        self._terms[normalized] = term_def

        # Index by URI local name (e.g., "ACLineSegment" from full URI)
        local_name = self._get_local_name(uri)
        if local_name:
            normalized_local = self._normalize_term(local_name)
            if normalized_local not in self._terms:
                self._terms[normalized_local] = term_def

        # Index alt labels
        for alt in alt_labels:
            normalized_alt = self._normalize_term(alt)
            if normalized_alt not in self._alt_label_map:
                self._alt_label_map[normalized_alt] = normalized

    def _extract_owl_class(self, graph: Graph, uri: URIRef, vocab_name: str) -> None:
        """Extract an OWL class and add to index."""
        # Try rdfs:label first, then fall back to local name
        label = self._get_label(graph, uri, RDFS.label)
        if not label:
            label = self._get_local_name(uri)
        if not label:
            return

        comment = self._get_literal(graph, uri, RDFS.comment)

        term_def = TermDefinition(
            uri=str(uri),
            pref_label=label,
            alt_labels=[],
            definition=comment,
            vocabulary_name=vocab_name,
            source="local"
        )

        normalized = self._normalize_term(label)
        if normalized not in self._terms:
            self._terms[normalized] = term_def

    def lookup(self, term: str) -> Optional[TermDefinition]:
        """Look up a term in the local index.

        Args:
            term: The term to look up (case-insensitive)

        Returns:
            TermDefinition if found, None otherwise
        """
        if not self._loaded:
            return None

        normalized = self._normalize_term(term)

        # Direct lookup
        if normalized in self._terms:
            return self._terms[normalized]

        # Alt label lookup
        if normalized in self._alt_label_map:
            pref_normalized = self._alt_label_map[normalized]
            return self._terms.get(pref_normalized)

        # Fuzzy match: try without common suffixes/prefixes
        # e.g., "ACLineSegments" -> "ACLineSegment"
        if normalized.endswith("s") and len(normalized) > 3:
            singular = normalized[:-1]
            if singular in self._terms:
                return self._terms[singular]

        return None

    def search(self, query: str, limit: int = 10) -> List[TermDefinition]:
        """Search for terms containing the query string.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching TermDefinitions
        """
        if not self._loaded:
            return []

        normalized_query = self._normalize_term(query)
        results = []

        for key, term_def in self._terms.items():
            if normalized_query in key:
                results.append(term_def)
                if len(results) >= limit:
                    break

        return results

    @staticmethod
    def _normalize_term(term: str) -> str:
        """Normalize a term for lookup (lowercase, strip whitespace)."""
        return term.lower().strip()

    @staticmethod
    def _get_label(graph: Graph, subject: URIRef, predicate) -> str:
        """Get a single label, preferring English."""
        labels = list(graph.objects(subject, predicate))
        if not labels:
            return ""

        # Prefer English labels
        for label in labels:
            if hasattr(label, "language") and label.language in ("en", "en-US"):
                return str(label)

        return str(labels[0])

    @staticmethod
    def _get_labels(graph: Graph, subject: URIRef, predicate) -> List[str]:
        """Get all labels for a predicate."""
        return [str(obj) for obj in graph.objects(subject, predicate)]

    @staticmethod
    def _get_literal(graph: Graph, subject: URIRef, predicate) -> str:
        """Get a single literal value, preferring English."""
        literals = list(graph.objects(subject, predicate))
        if not literals:
            return ""

        # Prefer English literals
        for lit in literals:
            if hasattr(lit, "language") and lit.language in ("en", "en-US"):
                return str(lit)

        return str(literals[0])

    @staticmethod
    def _get_local_name(uri: URIRef) -> str:
        """Extract local name from URI."""
        uri_str = str(uri)
        if "#" in uri_str:
            return uri_str.split("#")[-1]
        return uri_str.split("/")[-1]


class SKOSMOSClient:
    """SKOSMOS terminology verification client with local-first approach.

    Resolution order:
    1. Local index lookup (loaded from TTL files)
    2. If local miss and API enabled: call SKOSMOS API
    3. If API fails but local hit exists: use local (never abstain due to API failure)
    4. If both miss: abstain (term cannot be verified)

    Thread-safe: Safe for concurrent use from multiple coroutines.
    """

    def __init__(
        self,
        mode: str = "hybrid",
        data_path: Optional[Path] = None,
        api_url: Optional[str] = None,
        api_timeout: float = 5.0,
        lazy_load: bool = False,
    ):
        """Initialize the SKOSMOS client.

        Args:
            mode: "local", "api", or "hybrid" (default: "hybrid")
            data_path: Path to TTL vocabulary files (default: from settings)
            api_url: SKOSMOS API URL (default: from settings)
            api_timeout: API timeout in seconds
            lazy_load: If True, load vocabularies on first lookup
        """
        self.mode = mode
        self.data_path = data_path or settings.resolve_path(settings.skosmos_data_path)
        self.api_url = api_url or settings.skosmos_api_url
        self.api_timeout = api_timeout
        self.lazy_load = lazy_load

        self._local_index = LocalVocabularyIndex()
        self._api_cache: Dict[str, TermDefinition] = {}
        self._cache_lock = threading.Lock()

        self._obs_logger = get_logger("skosmos_client")

        # Load immediately if not lazy
        if not lazy_load and mode in ("local", "hybrid"):
            self._local_index.load(self.data_path)

    def _ensure_loaded(self) -> None:
        """Ensure local vocabulary is loaded (lazy load support)."""
        if self.mode in ("local", "hybrid") and not self._local_index.is_loaded:
            self._local_index.load(self.data_path)

    def lookup_term(self, term: str, request_id: Optional[str] = None) -> TermLookupResult:
        """Look up a terminology term with local-first resolution.

        Args:
            term: The term to verify (e.g., "ACLineSegment", "CIMXML")
            request_id: Optional request ID for logging correlation

        Returns:
            TermLookupResult with verification status and abstention decision
        """
        start_time = time.time()
        obs_logger = get_logger("skosmos_client", request_id)

        metrics.increment("skosmos_lookup_total")

        self._ensure_loaded()

        # Step 1: Local lookup (always tried first in local/hybrid mode)
        local_result = None
        if self.mode in ("local", "hybrid"):
            local_result = self._local_index.lookup(term)
            if local_result:
                latency_ms = (time.time() - start_time) * 1000
                metrics.increment("skosmos_hit_total", labels={"source": "local"})
                metrics.observe("skosmos_lookup_duration_seconds", latency_ms / 1000)

                obs_logger.info(
                    "term_lookup_hit",
                    term=term,
                    source="local",
                    vocabulary=local_result.vocabulary_name,
                    latency_ms=round(latency_ms, 2)
                )

                return TermLookupResult(
                    found=True,
                    term=term,
                    definition=local_result,
                    source="local",
                    should_abstain=False,
                    latency_ms=latency_ms
                )

        # Step 2: API lookup (if local miss and API enabled)
        api_result = None
        api_error = None
        if self.mode in ("api", "hybrid") and self.api_url:
            api_result, api_error = self._api_lookup(term, obs_logger)
            if api_result:
                latency_ms = (time.time() - start_time) * 1000
                metrics.increment("skosmos_hit_total", labels={"source": "api"})
                metrics.observe("skosmos_lookup_duration_seconds", latency_ms / 1000)

                obs_logger.info(
                    "term_lookup_hit",
                    term=term,
                    source="api",
                    latency_ms=round(latency_ms, 2)
                )

                return TermLookupResult(
                    found=True,
                    term=term,
                    definition=api_result,
                    source="api",
                    should_abstain=False,
                    latency_ms=latency_ms
                )

        # Step 3: Handle miss scenarios
        latency_ms = (time.time() - start_time) * 1000
        metrics.increment("skosmos_miss_total")
        metrics.observe("skosmos_lookup_duration_seconds", latency_ms / 1000)

        # Determine abstention
        should_abstain = False
        abstain_reason = ""

        if self.mode == "local":
            # Local-only mode: abstain if local miss
            should_abstain = True
            abstain_reason = f"Term '{term}' not found in local vocabulary index."
        elif self.mode == "api":
            # API-only mode: abstain if API miss/error
            should_abstain = True
            if api_error:
                abstain_reason = f"Term '{term}' could not be verified (API error: {api_error})."
            else:
                abstain_reason = f"Term '{term}' not found in SKOSMOS API."
        else:  # hybrid
            # Hybrid mode: abstain only if both local AND API miss/fail
            # If local hit exists but API fails, DO NOT abstain (key enterprise requirement)
            if local_result:
                # Local hit + API fail = use local, don't abstain
                should_abstain = False
            else:
                # Local miss + API miss/fail = abstain
                should_abstain = True
                if api_error:
                    abstain_reason = f"Term '{term}' could not be verified (not in local index, API error: {api_error})."
                else:
                    abstain_reason = f"Term '{term}' not found in local vocabulary or SKOSMOS API."

        if should_abstain:
            metrics.increment("rag_abstention_total", labels={"reason": "skosmos_verification_failed"})
            obs_logger.warn(
                "term_lookup_abstain",
                term=term,
                reason=abstain_reason,
                latency_ms=round(latency_ms, 2)
            )

        return TermLookupResult(
            found=False,
            term=term,
            definition=None,
            source=None,
            should_abstain=should_abstain,
            abstain_reason=abstain_reason,
            latency_ms=latency_ms
        )

    def _api_lookup(self, term: str, obs_logger) -> tuple[Optional[TermDefinition], Optional[str]]:
        """Look up a term via the SKOSMOS REST API.

        Args:
            term: The term to look up
            obs_logger: Logger for observability

        Returns:
            Tuple of (TermDefinition if found, error message if failed)
        """
        if not self.api_url:
            return None, "API URL not configured"

        # Check cache first
        normalized = term.lower().strip()
        with self._cache_lock:
            if normalized in self._api_cache:
                metrics.increment("skosmos_cache_hit_total")
                return self._api_cache[normalized], None

        try:
            # SKOSMOS REST API: search endpoint
            # Example: GET /rest/v1/search?query=ACLineSegment&unique=true
            url = f"{self.api_url.rstrip('/')}/search"
            params = {"query": term, "unique": "true"}

            with httpx.Client(timeout=self.api_timeout) as client:
                response = client.get(url, params=params)
                response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if not results:
                return None, None  # Not found (not an error)

            # Take the first (best) result
            result = results[0]
            term_def = TermDefinition(
                uri=result.get("uri", ""),
                pref_label=result.get("prefLabel", ""),
                alt_labels=result.get("altLabel", []) if isinstance(result.get("altLabel"), list) else [],
                definition=result.get("definition", ""),
                vocabulary_name=result.get("vocab", ""),
                source="api"
            )

            # Cache the result
            with self._cache_lock:
                self._api_cache[normalized] = term_def

            return term_def, None

        except httpx.TimeoutException:
            metrics.increment("skosmos_timeout_total")
            obs_logger.warn("api_timeout", term=term, timeout_seconds=self.api_timeout)
            return None, "API timeout"

        except httpx.HTTPStatusError as e:
            obs_logger.error("api_http_error", term=term, status_code=e.response.status_code)
            return None, f"HTTP {e.response.status_code}"

        except Exception as e:
            obs_logger.error("api_error", term=term, error=str(e))
            return None, str(e)

    def verify_query_terms(self, query: str, request_id: Optional[str] = None) -> List[TermLookupResult]:
        """Verify all technical terms in a query.

        Extracts potential technical terms from the query and verifies each one.

        Args:
            query: The user's query
            request_id: Optional request ID for logging

        Returns:
            List of TermLookupResult for each extracted term
        """
        terms = self._extract_technical_terms(query)
        results = []

        for term in terms:
            result = self.lookup_term(term, request_id)
            results.append(result)

        return results

    def _extract_technical_terms(self, query: str) -> List[str]:
        """Extract potential technical terms from a query.

        Looks for:
        - CamelCase words (ACLineSegment, PowerTransformer)
        - Acronyms (CIM, CIMXML, IEC)
        - Domain-specific patterns (IEC61970, CIM100)
        """
        terms = []

        # CamelCase pattern (e.g., ACLineSegment, PowerTransformer)
        camel_pattern = re.compile(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b')
        terms.extend(camel_pattern.findall(query))

        # Acronyms and technical identifiers (e.g., CIM, CIMXML, IEC61970)
        tech_pattern = re.compile(r'\b[A-Z]{2,}(?:\d+)?(?:-[A-Z0-9]+)?\b')
        terms.extend(tech_pattern.findall(query))

        # Domain-specific patterns (IEC standards)
        iec_pattern = re.compile(r'\bIEC\s*\d+(?:-\d+)?\b', re.IGNORECASE)
        terms.extend(iec_pattern.findall(query))

        # Deduplicate while preserving order
        seen = set()
        unique_terms = []
        for term in terms:
            if term.lower() not in seen:
                seen.add(term.lower())
                unique_terms.append(term)

        return unique_terms

    def get_stats(self) -> Dict:
        """Get client statistics for monitoring.

        Returns:
            Dict with term_count, vocabulary_count, load_time_ms, etc.
        """
        return {
            "mode": self.mode,
            "local_loaded": self._local_index.is_loaded,
            "local_term_count": self._local_index.term_count,
            "local_vocabularies": list(self._local_index.vocabularies),
            "local_load_time_ms": round(self._local_index._load_time_ms, 2),
            "api_configured": bool(self.api_url),
            "api_cache_size": len(self._api_cache),
        }


# =============================================================================
# Module-level singleton
# =============================================================================

_skosmos_client: Optional[SKOSMOSClient] = None
_client_lock = threading.Lock()


def get_skosmos_client() -> SKOSMOSClient:
    """Get or create the global SKOSMOS client singleton.

    Returns:
        Configured SKOSMOSClient instance
    """
    global _skosmos_client

    with _client_lock:
        if _skosmos_client is None:
            _skosmos_client = SKOSMOSClient(
                mode=settings.skosmos_mode,
                data_path=settings.resolve_path(settings.skosmos_data_path),
                api_url=settings.skosmos_api_url,
                api_timeout=settings.skosmos_api_timeout_seconds,
                lazy_load=settings.skosmos_lazy_load,
            )
            logger.info(
                f"SKOSMOS client initialized: mode={settings.skosmos_mode}, "
                f"data_path={settings.skosmos_data_path}, "
                f"api_configured={bool(settings.skosmos_api_url)}"
            )

    return _skosmos_client


def reset_skosmos_client() -> None:
    """Reset the global SKOSMOS client (for testing)."""
    global _skosmos_client
    with _client_lock:
        _skosmos_client = None
