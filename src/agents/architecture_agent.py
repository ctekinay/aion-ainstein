"""Agent for querying Architectural Decision Records and principles.

Routing architecture (scoring gate):
  Queries are routed by a scoring gate, NOT by direct regex if-else.

  1. _extract_signals()  — boolean feature extraction from the query
  2. _score_intents()    — weighted combination of signals → intent scores
  3. _select_winner()    — argmax + threshold + margin gate

  New routing behavior is added by:
    - Adding a signal in _extract_signals()  (regex allowed here only)
    - Adding a weight in _WEIGHTS
    - NEVER by adding direct-routing if-else branches

  Fallback when no intent wins the scoring gate:
    - doc ref present + no retrieval verb → conversational
    - otherwise → semantic hybrid search with doc_type filter
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

from weaviate import WeaviateClient
from weaviate.classes.query import Filter

from .base import BaseAgent, AgentResponse, _needs_client_side_embedding, _embed_query
from ..weaviate.collections import get_collection_name
from ..config import settings
from ..skills.filters import build_adr_filter

logger = logging.getLogger(__name__)


# =============================================================================
# M2: Structured route trace
# =============================================================================

@dataclass
class RouteTrace:
    """Structured routing decision trace for audit and CI invariants."""

    agent: str = "ArchitectureAgent"
    intent: str = ""
    doc_refs_detected: list[str] = field(default_factory=list)
    # Scoring gate fields
    signals: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    winner: str = ""
    threshold_met: bool = False
    margin_ok: bool = False
    # Routing outcome
    path: str = ""   # list | count | lookup_exact | lookup_number | hybrid | conversational
    selected_chunk: str = "none"  # decision | none | other
    filters_applied: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))



# =============================================================================
# Signal extraction regexes (feature detectors — never route directly)
# =============================================================================

_LIST_RE = re.compile(
    r"\b(?:list|show\s+(?:me\s+)?all|enumerate)\b.*\b(?:adrs?|decisions?|principles?)\b"
    r"|\b(?:what|which)\s+(?:adrs?|decisions?|principles?)\s+(?:exist|are\s+there|do\s+we\s+have)\b",
    re.IGNORECASE,
)

_COUNT_RE = re.compile(
    r"\bhow\s+many\s+(?:adrs?|decisions?|principles?)\b"
    r"|\btotal\s+(?:number|count)\s+of\s+(?:adrs?|decisions?|principles?)\b"
    r"|\bcount\s+(?:of\s+)?(?:adrs?|decisions?|principles?)\b",
    re.IGNORECASE,
)

_ALL_QUANTIFIER_RE = re.compile(
    r"\b(?:all|every|entire|everything)\b",
    re.IGNORECASE,
)

_TOPIC_QUALIFIER_MARKERS = (
    "about", "regarding", "related to",
    "with respect to", "in terms of", "concerning",
)


# =============================================================================
# Signal extraction + Intent scoring gate
# =============================================================================

@dataclass
class RoutingSignals:
    """Boolean features extracted from the query — used by scoring gate."""

    has_list_phrase: bool = False
    has_all_quantifier: bool = False
    has_topic_qualifier: bool = False
    has_doc_ref: bool = False
    has_retrieval_verb: bool = False
    has_count_phrase: bool = False
    doc_refs: list = field(default_factory=list)


def _extract_signals(question: str) -> RoutingSignals:
    """Extract routing signals from a query.

    All regex matching happens here.  No signal directly decides intent;
    routing is determined by _score_intents().
    """
    q_lower = question.lower()
    doc_refs = _normalize_doc_ids(question)
    return RoutingSignals(
        has_list_phrase=bool(_LIST_RE.search(question)),
        has_all_quantifier=bool(_ALL_QUANTIFIER_RE.search(question)),
        has_topic_qualifier=any(m in q_lower for m in _TOPIC_QUALIFIER_MARKERS),
        has_doc_ref=len(doc_refs) > 0,
        has_retrieval_verb=_has_retrieval_intent(question),
        has_count_phrase=bool(_COUNT_RE.search(question)),
        doc_refs=doc_refs,
    )


# Scoring weights — tune these, never add if-else branches
_WEIGHTS: dict[str, dict[str, float]] = {
    "list": {
        "has_list_phrase": 2.0,
        "has_all_quantifier": 1.0,
        "has_topic_qualifier": -2.5,
    },
    "count": {
        "has_count_phrase": 3.0,
    },
    "lookup_doc": {
        "has_doc_ref_and_verb": 3.0,
        "has_doc_ref_no_verb": -3.0,
    },
    "semantic_answer": {
        "has_topic_qualifier": 1.5,
    },
}

# Minimum score for an intent to be eligible as winner
_INTENT_THRESHOLDS: dict[str, float] = {
    "list": 1.5,
    "count": 2.0,
    "lookup_doc": 2.0,
    "semantic_answer": 1.0,
}

# Winner must beat runner-up by at least this margin
_SCORE_MARGIN = 0.5


def _score_intents(signals: RoutingSignals) -> dict[str, float]:
    """Compute intent scores from signals.

    Returns a dict mapping intent name → score.
    Routing is decided by _select_winner(), not by this function.
    """
    scores: dict[str, float] = {
        "list": 0.0,
        "count": 0.0,
        "lookup_doc": 0.0,
        "semantic_answer": 0.0,
    }

    # LIST
    if signals.has_list_phrase:
        scores["list"] += _WEIGHTS["list"]["has_list_phrase"]
    if signals.has_all_quantifier:
        scores["list"] += _WEIGHTS["list"]["has_all_quantifier"]
    if signals.has_topic_qualifier:
        scores["list"] += _WEIGHTS["list"]["has_topic_qualifier"]

    # COUNT
    if signals.has_count_phrase:
        scores["count"] += _WEIGHTS["count"]["has_count_phrase"]

    # LOOKUP_DOC — compound signal
    if signals.has_doc_ref and signals.has_retrieval_verb:
        scores["lookup_doc"] += _WEIGHTS["lookup_doc"]["has_doc_ref_and_verb"]
    elif signals.has_doc_ref and not signals.has_retrieval_verb:
        scores["lookup_doc"] += _WEIGHTS["lookup_doc"]["has_doc_ref_no_verb"]

    # SEMANTIC_ANSWER
    if signals.has_topic_qualifier:
        scores["semantic_answer"] += _WEIGHTS["semantic_answer"]["has_topic_qualifier"]

    return scores


def _select_winner(
    scores: dict[str, float],
) -> tuple[Optional[str], bool, bool]:
    """Pick the winning intent from scores.

    Returns (winner_name, threshold_met, margin_ok).
    If no intent passes its threshold, winner is None.
    """
    # Sort by score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if not ranked:
        return None, False, False

    winner_name, winner_score = ranked[0]
    runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0

    threshold = _INTENT_THRESHOLDS.get(winner_name, 1.0)
    threshold_met = winner_score >= threshold
    margin_ok = (winner_score - runner_up_score) >= _SCORE_MARGIN

    if not threshold_met:
        return None, False, margin_ok

    return winner_name, threshold_met, margin_ok


# =============================================================================
# A3: Canonical ID normalization
# =============================================================================

_CANONICAL_ID_RE = re.compile(
    r"\b(ADR|PCP|DAR)[.\s\-]?(\d{1,4})(D)?\b",
    re.IGNORECASE,
)


def _normalize_doc_ids(question: str) -> list[dict]:
    """Extract and normalize doc references from a question.

    Returns list of dicts with keys:
        canonical_id: e.g. "ADR.12", "PCP.5", "ADR.12D"
        number_value: e.g. "0012", "0005"
        prefix: e.g. "ADR", "PCP"
    """
    results = []
    seen = set()
    for match in _CANONICAL_ID_RE.finditer(question):
        prefix = match.group(1).upper()
        num = int(match.group(2))
        suffix = (match.group(3) or "").upper()
        canonical_id = f"{prefix}.{num}{suffix}"
        if canonical_id not in seen:
            seen.add(canonical_id)
            results.append({
                "canonical_id": canonical_id,
                "number_value": f"{num:04d}",
                "prefix": prefix,
            })
    return results


# Bare-number detection: matches 1-4 digit numbers (e.g. "22", "0022")
# that are NOT preceded by a doc-type prefix (ADR/PCP/DAR).
_BARE_NUMBER_RE = re.compile(
    r"(?<!\w)"     # not preceded by a word character
    r"(\d{1,4})"
    r"(?!\w)",     # not followed by a word character
)


def _extract_bare_numbers(question: str) -> list[str]:
    """Extract bare document numbers from a query (no ADR/PCP/DAR prefix).

    Only returns results when the query has NO prefixed doc refs, since
    prefixed refs are already unambiguous and handled by _normalize_doc_ids.

    Returns:
        List of zero-padded number strings, e.g. ["0022"]
    """
    # If any prefixed refs exist, skip — those are already unambiguous
    if _CANONICAL_ID_RE.search(question):
        return []

    results = []
    seen = set()
    for match in _BARE_NUMBER_RE.finditer(question):
        num_str = match.group(1)
        num = int(num_str)
        # Skip 0 and very large numbers (not doc IDs)
        if num < 1 or num > 9999:
            continue
        padded = f"{num:04d}"
        if padded not in seen:
            seen.add(padded)
            results.append(padded)
    return results


@dataclass
class DocRefResolution:
    """Result of resolving a bare number to document references."""
    status: str  # "resolved" | "needs_clarification" | "none"
    number_value: str = ""
    candidates: list = field(default_factory=list)  # [{canonical_id, prefix, title, file}]
    resolved_ref: Optional[dict] = None  # same shape as _normalize_doc_ids() dict


# =============================================================================
# Follow-up marker detection
# =============================================================================

# Matches queries that refer to a previously mentioned document via pronoun
# or short demonstrative. Examples: "show it", "what does it decide",
# "tell me about that", "quote that one".
_FOLLOWUP_MARKER_RE = re.compile(
    r"\b(?:show\s+it|what\s+(?:does|about)\s+it|"
    r"tell\s+me\s+(?:about\s+)?(?:it|that|this)|"
    r"(?:that|this|the)\s+(?:one|document|adr|principle)|"
    r"quote\s+(?:it|that)|explain\s+(?:it|that)|"
    r"(?:show|get|give)\s+me\s+(?:that|this|it))\b",
    re.IGNORECASE,
)


def _has_followup_marker(question: str) -> bool:
    """Check if query contains follow-up markers referring to a prior document."""
    return bool(_FOLLOWUP_MARKER_RE.search(question))


# =============================================================================
# A4: Retrieval-verb gate
# =============================================================================

_RETRIEVAL_VERB_RE = re.compile(
    r"\b(?:what|show|tell|explain|describe|summarize|summarise|quote|detail|"
    r"find|get|give|look\s*up|retrieve|fetch|read|display|decide|decision)\b",
    re.IGNORECASE,
)


def _has_retrieval_intent(question: str) -> bool:
    """Check whether the question asks for actual information retrieval.

    Prevents 'cheeky' queries like "I wish I had written ADR.12" from
    triggering document lookup.
    """
    return bool(_RETRIEVAL_VERB_RE.search(question))


# =============================================================================
# Helper: Fetch all objects with pagination
# =============================================================================

def _fetch_all_objects(collection, return_properties: list[str] = None, page_size: int = 100) -> list:
    """Fetch ALL objects from a collection with pagination.

    Args:
        collection: Weaviate collection object
        return_properties: Properties to return
        page_size: Number of objects per page

    Returns:
        List of all Weaviate objects
    """
    all_objects = []
    offset = 0

    while True:
        results = collection.query.fetch_objects(
            limit=page_size,
            offset=offset,
            return_properties=return_properties,
        )

        if not results.objects:
            break

        all_objects.extend(results.objects)
        offset += page_size

        # Safety limit
        if offset >= 10000:
            logger.warning(f"_fetch_all_objects hit safety limit at {offset} objects")
            break

    return all_objects


# =============================================================================
# ArchitectureAgent
# =============================================================================

class ArchitectureAgent(BaseAgent):
    """Agent specialized in architecture decisions and principles."""

    name = "ArchitectureAgent"
    description = (
        "Expert in Energy System Architecture decisions and principles. "
        "Can answer questions about architectural patterns, design decisions, "
        "standards adoption, and system design rationale documented in ADRs."
    )
    collection_name = get_collection_name("adr")

    def __init__(self, client: WeaviateClient, llm_client: Optional[Any] = None):
        """Initialize the architecture agent.

        Args:
            client: Connected Weaviate client
            llm_client: Optional LLM client for generation
        """
        super().__init__(client, llm_client)

    # -----------------------------------------------------------------
    # A10: Main query() flow
    # -----------------------------------------------------------------

    async def query(
        self,
        question: str,
        limit: int = 5,
        include_principles: bool = True,
        status_filter: Optional[str] = None,
        last_doc_refs: Optional[list[dict]] = None,
        **kwargs,
    ) -> AgentResponse:
        """Query the architecture knowledge base.

        Flow:
        1. Extract signals (boolean features from query)
        1b. Bare-number resolution (if no prefixed ref)
        1c. Follow-up binding (if no doc ref + follow-up markers + last_doc_refs)
        2. Score intents via weighted signals
        3. Select winner (argmax + threshold + margin)
        4. Route to handler
        5. Emit structured route trace (JSON log line)

        Args:
            question: The user's question
            limit: Maximum number of results
            include_principles: Whether to also search principles
            status_filter: Filter by ADR status (accepted, proposed, deprecated)
            last_doc_refs: Doc refs from the previous query in this conversation,
                used for follow-up resolution (e.g. "show it" → re-use last ref)

        Returns:
            AgentResponse with architecture information
        """
        logger.info(f"ArchitectureAgent processing: {question}")

        # Step 1: Extract signals
        signals = _extract_signals(question)

        # Step 1b: Bare-number resolution — if no prefixed doc ref detected,
        # check if the query contains a bare number (e.g. "0022", "22") and
        # resolve it against known collections.
        bare_number_resolution = None
        if not signals.has_doc_ref:
            bare_numbers = _extract_bare_numbers(question)
            if bare_numbers:
                bare_number_resolution = self._resolve_bare_number_ref(bare_numbers[0])

                if bare_number_resolution.status == "resolved":
                    # Patch signals as if the user had typed the full prefix
                    ref = bare_number_resolution.resolved_ref
                    signals.doc_refs = [ref]
                    signals.has_doc_ref = True
                    logger.info(
                        "bare-number resolved: %s → %s",
                        bare_numbers[0], ref["canonical_id"],
                    )

                elif bare_number_resolution.status == "needs_clarification":
                    return self._format_clarification_response(
                        bare_number_resolution
                    )

        # Step 1c: Follow-up binding — if still no doc ref and query contains
        # follow-up markers ("show it", "what does it decide"), inject last_doc_refs
        if not signals.has_doc_ref and last_doc_refs and _has_followup_marker(question):
            signals.doc_refs = last_doc_refs
            signals.has_doc_ref = True
            signals.has_retrieval_verb = True  # follow-ups imply retrieval intent
            logger.info(
                "follow-up bound: injected %d doc ref(s) from previous query: %s",
                len(last_doc_refs),
                [r.get("canonical_id", "?") for r in last_doc_refs],
            )

        # Step 2: Score intents
        scores = _score_intents(signals)

        # Step 3: Select winner
        winner, threshold_met, margin_ok = _select_winner(scores)

        # Build trace
        trace = RouteTrace(
            doc_refs_detected=[r["canonical_id"] for r in signals.doc_refs],
            signals={k: v for k, v in asdict(signals).items() if k != "doc_refs"},
            scores=scores,
            winner=winner or "none",
            threshold_met=threshold_met,
            margin_ok=margin_ok,
        )

        # Step 4: Route by winner
        if threshold_met and margin_ok and winner:
            if winner == "list":
                trace.intent = "list"
                trace.path = "list"
                self._emit_trace(trace)
                return await self._handle_listing_query(question, include_principles)

            if winner == "count":
                trace.intent = "count"
                trace.path = "count"
                self._emit_trace(trace)
                return await self._handle_count_query(question)

            if winner == "lookup_doc":
                trace.intent = "lookup_doc"
                response = await self._handle_lookup_query(
                    question, signals.doc_refs, trace,
                )
                self._emit_trace(trace)
                return response

            if winner == "semantic_answer":
                trace.intent = "semantic_answer"
                # fall through to semantic path below

        # Step 5: Fallback — no confident winner
        # If doc refs present but no retrieval verb → conversational
        if signals.has_doc_ref and not signals.has_retrieval_verb:
            trace.intent = trace.intent or "conversational"
            trace.path = "conversational"
            self._emit_trace(trace)
            return self._conversational_response(question, signals.doc_refs)

        # Step 6: Semantic search — must always include filters
        trace.intent = trace.intent or "semantic_answer"
        trace.path = "hybrid"
        adr_filter = build_adr_filter()
        if adr_filter is None:
            logger.error(
                "INVARIANT VIOLATION: semantic path has no doc_type filter. "
                "Falling back to conversational response."
            )
            trace.filters_applied = "MISSING"
            self._emit_trace(trace)
            return self._conversational_response(question, signals.doc_refs)
        trace.filters_applied = "doc_type:adr|content"
        self._emit_trace(trace)
        return await self._handle_semantic_query(
            question, limit=limit, include_principles=include_principles,
            status_filter=status_filter, adr_filter=adr_filter,
        )

    @staticmethod
    def _emit_trace(trace: RouteTrace) -> None:
        """Emit structured route trace as a JSON log line."""
        logger.info(f"ROUTE_TRACE {trace.to_json()}")

    # -----------------------------------------------------------------
    # A6: Exact-match ID lookup
    # -----------------------------------------------------------------

    def lookup_by_canonical_id(self, canonical_id: str) -> list[dict]:
        """Look up all chunks for a document by canonical_id.

        Uses Filter.by_property("canonical_id").equal() for exact match.
        Falls back to adr_number if canonical_id returns no results.

        Args:
            canonical_id: Normalized canonical ID (e.g. "ADR.12")

        Returns:
            List of matching document chunks (may be multiple per ADR)
        """
        collection = self.client.collections.get(self.collection_name)

        # Primary: exact match on canonical_id (FIELD tokenization)
        results = collection.query.fetch_objects(
            filters=Filter.by_property("canonical_id").equal(canonical_id),
            limit=25,
        )

        if results.objects:
            chunks = [dict(obj.properties) for obj in results.objects]
            # Defense in depth: post-filter on canonical_id in case Weaviate
            # filter is bypassed or returns unexpected results.
            filtered = [
                c for c in chunks
                if c.get("canonical_id") == canonical_id
            ]
            if len(filtered) < len(chunks):
                dropped = [
                    c.get("canonical_id", "<missing>") for c in chunks
                    if c.get("canonical_id") != canonical_id
                ]
                logger.warning(
                    "canonical_id post-filter stripped mismatches: %s",
                    json.dumps({
                        "requested_canonical_id": canonical_id,
                        "dropped_count": len(dropped),
                        "dropped_canonical_ids": dropped[:10],
                    }, separators=(",", ":")),
                )
            if filtered:
                logger.info(
                    f"canonical_id lookup '{canonical_id}' returned "
                    f"{len(filtered)} chunks"
                )
                return filtered

        # Fallback: try adr_number field
        # Extract the number from canonical_id (e.g. "ADR.12" → "0012")
        match = re.match(r"[A-Z]+\.(\d+)", canonical_id)
        if match:
            number_value = f"{int(match.group(1)):04d}"
            return self._lookup_by_number_field(number_value)

        return []

    def _lookup_by_number_field(self, number_value: str) -> list[dict]:
        """Fallback lookup by adr_number field.

        Args:
            number_value: Zero-padded number string (e.g. "0012")

        Returns:
            List of matching document chunks
        """
        collection = self.client.collections.get(self.collection_name)

        results = collection.query.fetch_objects(
            filters=Filter.by_property("adr_number").equal(number_value),
            limit=25,
        )

        if results.objects:
            logger.info(
                f"adr_number lookup '{number_value}' returned "
                f"{len(results.objects)} chunks"
            )

        return [dict(obj.properties) for obj in results.objects]

    # -----------------------------------------------------------------
    # Bare-number resolution
    # -----------------------------------------------------------------

    # Map of (logical_collection_name, number_field, prefix) for bare-number lookup
    _NUMBER_FIELD_MAP = [
        ("adr", "adr_number", "ADR"),
        ("principle", "principle_number", "PCP"),
    ]

    def _resolve_bare_number_ref(self, number_value: str) -> DocRefResolution:
        """Resolve a bare number (e.g. "0022") to document references.

        Queries ADR and Principle collections by their respective number fields
        to find all documents matching the bare number.

        Args:
            number_value: Zero-padded number string (e.g. "0022")

        Returns:
            DocRefResolution with status:
              - "resolved": exactly one doc type matched → resolved_ref populated
              - "needs_clarification": multiple doc types matched → candidates populated
              - "none": no matches found
        """
        candidates = []

        for logical_name, number_field, prefix in self._NUMBER_FIELD_MAP:
            try:
                coll_name = get_collection_name(logical_name)
                collection = self.client.collections.get(coll_name)
                results = collection.query.fetch_objects(
                    filters=Filter.by_property(number_field).equal(number_value),
                    limit=5,
                )
                if results.objects:
                    # Take first object to get representative metadata
                    first = dict(results.objects[0].properties)
                    candidates.append({
                        "canonical_id": f"{prefix}.{int(number_value)}",
                        "prefix": prefix,
                        "title": first.get("title", ""),
                        "file": first.get("file_path", ""),
                    })
            except Exception as exc:
                logger.warning(
                    "bare-number lookup failed for %s.%s: %s",
                    prefix, number_value, exc,
                )

        if not candidates:
            return DocRefResolution(status="none", number_value=number_value)

        if len(candidates) == 1:
            c = candidates[0]
            return DocRefResolution(
                status="resolved",
                number_value=number_value,
                candidates=candidates,
                resolved_ref={
                    "canonical_id": c["canonical_id"],
                    "prefix": c["prefix"],
                    "number_value": number_value,
                },
            )

        # Multiple doc types share this number → needs disambiguation
        return DocRefResolution(
            status="needs_clarification",
            number_value=number_value,
            candidates=candidates,
        )

    # -----------------------------------------------------------------
    # A7: Decision chunk selection
    # -----------------------------------------------------------------

    # Matches "Section: Decision" but NOT "Section: Decision Drivers"
    _SECTION_DECISION_RE = re.compile(r"Section:\s*Decision(?!\s*Drivers)\b")

    @staticmethod
    def _has_section_decision(full_text: str) -> bool:
        """Check if full_text contains 'Section: Decision' (not 'Decision Drivers')."""
        return bool(ArchitectureAgent._SECTION_DECISION_RE.search(full_text))

    @staticmethod
    def _select_decision_chunk(chunks: list[dict]) -> Optional[dict]:
        """Select the Decision chunk from a set of ADR chunks.

        Precedence (first match wins):
        1. decision non-empty AND full_text contains "Section: Decision"
           (but NOT "Section: Decision Drivers")
        2. decision non-empty (any chunk)
        3. full_text contains "Section: Decision" (not Decision Drivers)
        4. title ends with " - Decision" (explicitly rejects "Decision Drivers")

        Args:
            chunks: List of ADR chunk dicts

        Returns:
            The decision chunk, or None if not found
        """
        # Tier 1: decision non-empty AND full_text has "Section: Decision"
        for chunk in chunks:
            decision_text = chunk.get("decision", "")
            full_text = chunk.get("full_text", "")
            if (
                decision_text and decision_text.strip()
                and ArchitectureAgent._has_section_decision(full_text)
            ):
                return chunk

        # Tier 2: decision non-empty
        for chunk in chunks:
            decision_text = chunk.get("decision", "")
            if decision_text and decision_text.strip():
                return chunk

        # Tier 3: full_text contains "Section: Decision" (not Decision Drivers)
        for chunk in chunks:
            full_text = chunk.get("full_text", "")
            if ArchitectureAgent._has_section_decision(full_text):
                return chunk

        # Tier 4: title ends with " - Decision" (reject Decision Drivers)
        for chunk in chunks:
            title = chunk.get("title", "")
            if title.endswith(" - Decision"):
                return chunk

        return None

    # -----------------------------------------------------------------
    # A8: Quote formatting
    # -----------------------------------------------------------------

    @staticmethod
    def _extract_lead_sentence(text: str) -> str:
        """Extract the first complete sentence from decision text.

        If the first line ends with a continuation marker (because, :, ;,
        and, or), extends to include subsequent lines until a sentence
        boundary (period, blank line, or bullet marker).

        Args:
            text: Raw decision text

        Returns:
            First complete sentence or clause
        """
        lines = [ln.strip() for ln in text.strip().split("\n") if ln.strip()]
        if not lines:
            return text.strip()

        # Continuation markers: line ends mid-sentence
        _CONTINUATION_RE = re.compile(r"(?:because|:|;|,\s*and|,\s*or)\s*$", re.IGNORECASE)
        # Sentence boundary: ends with ., !, ? or is a bullet/list item
        _BOUNDARY_RE = re.compile(r"[.!?]\s*$|^\s*[-*•]")

        result = lines[0]
        if not _CONTINUATION_RE.search(result):
            return result

        # Extend until sentence boundary or end of lines
        for line in lines[1:]:
            if _BOUNDARY_RE.search(result) or _BOUNDARY_RE.match(line):
                break
            result += " " + line
            if not _CONTINUATION_RE.search(line):
                break

        return result

    @staticmethod
    def _format_decision_answer(question: str, chunk: dict, canonical_id: str) -> str:
        """Format a decision answer with verbatim quote.

        Args:
            question: The original question
            chunk: The decision chunk dict
            canonical_id: The canonical document ID

        Returns:
            Formatted answer string with block quote
        """
        decision_text = chunk.get("decision", "")
        title = chunk.get("title", canonical_id)

        if not decision_text or not decision_text.strip():
            # No decision text — use full_text or content
            content = chunk.get("full_text", "") or chunk.get("content", "")
            if content:
                first_line = content.strip().split("\n")[0]
                return (
                    f"**{canonical_id}** ({title}):\n\n"
                    f"> {first_line}\n\n"
                    f"*(Full content available in the source document.)*"
                )
            return f"Found {canonical_id} but no decision text is available."

        # Extract lead sentence (handles "because:" continuation)
        lead = ArchitectureAgent._extract_lead_sentence(decision_text)

        return (
            f"**{canonical_id}** ({title}):\n\n"
            f"> {lead}\n\n"
            f"Full decision text:\n\n"
            f"> {decision_text.strip()}"
        )

    # -----------------------------------------------------------------
    # Conversational response (cheeky query gate)
    # -----------------------------------------------------------------

    def _conversational_response(
        self, question: str, doc_refs: list[dict]
    ) -> AgentResponse:
        """Return a conversational response when no retrieval verb is present.

        Args:
            question: The user's question
            doc_refs: Detected document references

        Returns:
            AgentResponse with a helpful suggestion
        """
        ref_list = ", ".join(r["canonical_id"] for r in doc_refs) if doc_refs else "the document"
        answer = (
            f"I see you mentioned {ref_list}. "
            f"If you'd like to know what it decides, try asking: "
            f"\"What does {doc_refs[0]['canonical_id'] if doc_refs else 'ADR.X'} decide?\""
        )
        return AgentResponse(
            answer=answer,
            sources=[],
            confidence=0.50,
            agent_name=self.name,
            raw_results=[],
        )

    # -----------------------------------------------------------------
    # Clarification response (bare-number ambiguity)
    # -----------------------------------------------------------------

    def _format_clarification_response(
        self, resolution: DocRefResolution
    ) -> AgentResponse:
        """Return a standardized clarification response for ambiguous bare numbers.

        Template:
          The number N matches multiple documents:
          - ADR.N (file: 00NN-title.md)
          - PCP.N (file: 00NN-title.md)
          Which one did you mean?

        The structured payload is stored in raw_results for UI rendering.
        """
        number_display = resolution.number_value.lstrip("0") or "0"
        candidate_lines = []
        for c in resolution.candidates:
            label = c["canonical_id"]
            if c.get("file"):
                label += f" (file: {c['file'].rsplit('/', 1)[-1]})"
            elif c.get("title"):
                label += f" ({c['title']})"
            candidate_lines.append(f"  - {label}")

        candidates_block = "\n".join(candidate_lines)
        answer = (
            f"The number {number_display} matches multiple documents:\n"
            f"{candidates_block}\n"
            f"Which one did you mean?"
        )

        return AgentResponse(
            answer=answer,
            sources=[],
            confidence=0.60,
            agent_name=self.name,
            raw_results=[{
                "type": "clarification",
                "number_value": resolution.number_value,
                "candidates": resolution.candidates,
            }],
        )

    # -----------------------------------------------------------------
    # Handler: LOOKUP_DOC
    # -----------------------------------------------------------------

    async def _handle_lookup_query(
        self, question: str, doc_refs: list[dict],
        trace: Optional[RouteTrace] = None,
    ) -> AgentResponse:
        """Handle exact-match document lookup queries.

        Args:
            question: The user's question
            doc_refs: Normalized document references
            trace: Optional route trace to populate

        Returns:
            AgentResponse with document content
        """
        all_chunks = []
        sources = []
        lookup_path = "lookup_exact"

        for ref in doc_refs:
            chunks = self.lookup_by_canonical_id(ref["canonical_id"])
            if not chunks:
                lookup_path = "lookup_number"
                continue

            all_chunks.extend(chunks)

            # Try to select and format the Decision chunk
            decision_chunk = self._select_decision_chunk(chunks)
            if decision_chunk:
                sources.append({
                    "title": decision_chunk.get("title", ""),
                    "type": "ADR",
                    "canonical_id": ref["canonical_id"],
                    "file": (
                        decision_chunk.get("file_path", "").split("/")[-1]
                        if decision_chunk.get("file_path") else ""
                    ),
                })

        if not all_chunks:
            if trace:
                trace.path = lookup_path
                trace.selected_chunk = "none"
            return AgentResponse(
                answer=f"No documents found for {', '.join(r['canonical_id'] for r in doc_refs)}.",
                sources=[],
                confidence=0.0,
                agent_name=self.name,
                raw_results=[],
            )

        # Format answer
        answer_parts = []
        selected_chunk_type = "none"
        for ref in doc_refs:
            ref_chunks = [
                c for c in all_chunks
                if c.get("canonical_id", "").startswith(ref["canonical_id"].rstrip("D"))
            ]
            if not ref_chunks:
                answer_parts.append(f"No content found for {ref['canonical_id']}.")
                continue

            decision_chunk = self._select_decision_chunk(ref_chunks)
            if decision_chunk:
                selected_chunk_type = "decision"
                answer_parts.append(
                    self._format_decision_answer(question, decision_chunk, ref["canonical_id"])
                )
            else:
                selected_chunk_type = "other"
                titles = [c.get("title", "Untitled") for c in ref_chunks]
                answer_parts.append(
                    f"**{ref['canonical_id']}** — Found {len(ref_chunks)} sections: "
                    f"{', '.join(titles)}"
                )

        if trace:
            trace.path = lookup_path
            trace.selected_chunk = selected_chunk_type

        answer = "\n\n---\n\n".join(answer_parts)
        confidence = 0.95 if all_chunks else 0.0

        return AgentResponse(
            answer=answer,
            sources=sources,
            confidence=confidence,
            agent_name=self.name,
            raw_results=all_chunks,
        )

    # -----------------------------------------------------------------
    # Handler: Semantic search (default path)
    # -----------------------------------------------------------------

    async def _handle_semantic_query(
        self,
        question: str,
        limit: int = 5,
        include_principles: bool = True,
        status_filter: Optional[str] = None,
        adr_filter: Optional[Any] = None,
    ) -> AgentResponse:
        """Handle semantic search queries with doc_type filtering.

        Args:
            question: The user's question
            limit: Maximum results
            include_principles: Whether to include principles
            status_filter: Optional status filter
            adr_filter: Pre-built doc_type filter (required; caller must provide)

        Returns:
            AgentResponse with search results
        """
        # A9/M3: filter must be present — caller enforces this
        if adr_filter is None:
            adr_filter = build_adr_filter()

        adr_results = self.hybrid_search(
            query=question,
            limit=limit,
            alpha=settings.alpha_vocabulary,
            filters=adr_filter,
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

        # Build sources
        sources = self._build_sources(all_results)

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

    # -----------------------------------------------------------------
    # Shared helpers
    # -----------------------------------------------------------------

    def _search_principles(self, query: str, limit: int = 3) -> list[dict]:
        """Search principles collection.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching principles
        """
        try:
            collection = self.client.collections.get(get_collection_name("principle"))
            hybrid_kwargs = dict(
                query=query,
                limit=limit,
                alpha=settings.alpha_vocabulary,
            )
            if _needs_client_side_embedding():
                hybrid_kwargs["vector"] = _embed_query(query)
            results = collection.query.hybrid(**hybrid_kwargs)
            return [dict(obj.properties) for obj in results.objects]
        except Exception as e:
            logger.warning(f"Failed to search principles: {e}")
            return []

    @staticmethod
    def _build_sources(results: list[dict]) -> list[dict]:
        """Build sources list from search results.

        Args:
            results: List of result dicts

        Returns:
            List of source metadata dicts
        """
        sources = []
        for doc in results:
            doc_type = "ADR" if doc.get("context") else "Principle"
            sources.append({
                "title": doc.get("title", ""),
                "type": doc_type,
                "status": doc.get("status", ""),
                "file": (
                    doc.get("file_path", "").split("/")[-1]
                    if doc.get("file_path") else ""
                ),
            })
        return sources

    def _calculate_confidence(self, results: list[dict]) -> float:
        """Calculate confidence score based on search results."""
        if not results:
            return 0.0

        scores = [r.get("_score", 0) for r in results[:3] if r.get("_score")]
        if not scores:
            return 0.5

        avg_score = sum(scores) / len(scores)
        return min(max(avg_score, 0.0), 1.0)

    # -----------------------------------------------------------------
    # Listing / counting (kept from original)
    # -----------------------------------------------------------------

    def list_all_adrs(self) -> list[dict]:
        """List all ADRs in the collection.

        Returns:
            List of all ADR documents with title, status, and file info
        """
        collection = self.client.collections.get(self.collection_name)

        # Fetch ALL objects with pagination for complete results
        all_objects = _fetch_all_objects(
            collection,
            return_properties=["title", "status", "file_path", "context", "decision"],
        )

        adrs = []
        for obj in all_objects:
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
        collection = self.client.collections.get(get_collection_name("principle"))

        # Fetch ALL objects with pagination for complete results
        all_objects = _fetch_all_objects(
            collection,
            return_properties=["title", "file_path", "doc_type"],
        )

        return [dict(obj.properties) for obj in all_objects]

    def list_adrs_by_status(self, status: str) -> list[dict]:
        """List all ADRs with a specific status.

        Args:
            status: The status to filter by

        Returns:
            List of matching ADRs
        """
        collection = self.client.collections.get(self.collection_name)

        results = collection.query.fetch_objects(
            filters=Filter.by_property("status").equal(status),
            limit=100,
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
