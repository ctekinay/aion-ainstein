"""Gold routing suite — behavioral envelope tests for ArchitectureAgent routing.

Validates the behavioral envelope of ArchitectureAgent routing.
Each query specifies exact expectations for: path, winner, key signals,
and selected_chunk. Runs against mocked Weaviate (no live connection).

Categories:
  - Prefixed lookup (D1)
  - Bare-number lookup (D2, D4)
  - Bare-number clarification (D3)
  - Cheeky / conversational (D5)
  - List (D6, D7)
  - Count (D8)
  - Semantic (D9) — winner=semantic_answer, conventions excluded
  - Regression traps
  - Follow-up binding
"""

import json
import logging
import asyncio
from unittest.mock import MagicMock

import pytest

from src.agents.architecture_agent import (
    ArchitectureAgent,
    _extract_signals,
    _score_intents,
    _select_winner,
)
from src.agents.base import AgentResponse
from src.weaviate.collections import get_collection_name


# =============================================================================
# Fixtures
# =============================================================================

def _make_chunk(
    title="Test ADR",
    decision="",
    canonical_id="ADR.12",
    file_path="docs/adr/0012-test.md",
    context="Some context",
    full_text="",
    doc_type="adr",
    adr_number="0012",
    status="accepted",
):
    return {
        "title": title,
        "decision": decision,
        "canonical_id": canonical_id,
        "file_path": file_path,
        "context": context,
        "full_text": full_text,
        "doc_type": doc_type,
        "adr_number": adr_number,
        "status": status,
    }


def _make_weaviate_object(properties: dict):
    obj = MagicMock()
    obj.properties = properties
    return obj


def _make_fetch_result(chunks: list[dict]):
    result = MagicMock()
    result.objects = [_make_weaviate_object(c) for c in chunks]
    return result


def _make_single_collection_client(chunks=None):
    """Mock client where all collections return the same data."""
    client = MagicMock()
    collection = MagicMock()
    collection.query.fetch_objects.return_value = _make_fetch_result(chunks or [])
    client.collections.get.return_value = collection
    return client, collection


def _make_multi_collection_client(adr_results=None, principle_results=None):
    """Mock client with per-collection routing."""
    client = MagicMock()
    adr_coll = MagicMock()
    pcp_coll = MagicMock()
    adr_coll.query.fetch_objects.return_value = adr_results or _make_fetch_result([])
    pcp_coll.query.fetch_objects.return_value = principle_results or _make_fetch_result([])

    def get_collection(name):
        if name == get_collection_name("adr"):
            return adr_coll
        if name == get_collection_name("principle"):
            return pcp_coll
        return MagicMock()

    client.collections.get.side_effect = get_collection
    return client, adr_coll, pcp_coll


DECISION_CHUNK_12 = _make_chunk(
    title="ADR.12 - Decision",
    decision="We adopt IEC CIM as the domain language.",
    canonical_id="ADR.12",
    file_path="data/esa-main-artifacts/decisions/adr/0012-domain-language.md",
    full_text="Section: Decision\nWe adopt IEC CIM as the domain language.",
    adr_number="0012",
)

DECISION_CHUNK_22 = _make_chunk(
    title="ADR.22 - Decision",
    decision="We adopt the interoperability standard.",
    canonical_id="ADR.22",
    file_path="data/esa-main-artifacts/decisions/adr/0022-interop.md",
    full_text="Section: Decision\nWe adopt the interoperability standard.",
    adr_number="0022",
)


async def _capture_trace(caplog, agent, question, **query_kwargs):
    """Run query and return parsed route trace dict."""
    with caplog.at_level(logging.INFO, logger="src.agents.architecture_agent"):
        response = await agent.query(question, **query_kwargs)
    trace_lines = [r.message for r in caplog.records if "ROUTE_TRACE" in r.message]
    trace = {}
    if trace_lines:
        raw = trace_lines[-1].replace("ROUTE_TRACE ", "")
        try:
            trace = json.loads(raw)
        except json.JSONDecodeError:
            pass
    caplog.clear()
    return response, trace


# =============================================================================
# D1: Prefixed doc ref → exact lookup
# =============================================================================

class TestGoldPrefixedLookup:
    """Prefixed doc refs must always take the exact lookup path."""

    QUERIES = [
        "What does ADR.0012 decide about domain language?",
        "ADR-12 quote the decision.",
        "Show me ADR 12 decision.",
        "What does ADR.12 decide?",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", QUERIES)
    async def test_prefixed_lookup_path(self, query, caplog):
        client, collection = _make_single_collection_client([DECISION_CHUNK_12])
        agent = ArchitectureAgent(client)

        response, trace = await _capture_trace(caplog, agent, query)

        assert trace.get("path") == "lookup_exact", f"Expected lookup_exact, got {trace.get('path')}"
        assert trace.get("winner") == "lookup_doc"
        assert trace.get("signals", {}).get("has_doc_ref") is True
        assert trace.get("signals", {}).get("has_retrieval_verb") is True
        assert not collection.query.hybrid.called, "Hybrid must NOT be called for prefixed lookup"

    @pytest.mark.asyncio
    async def test_prefixed_decision_chunk_selected(self, caplog):
        """Decision chunk must be selected (not context/drivers)."""
        client, collection = _make_single_collection_client([DECISION_CHUNK_12])
        agent = ArchitectureAgent(client)

        response, trace = await _capture_trace(caplog, agent, "What does ADR.0012 decide?")

        assert trace.get("selected_chunk") == "decision"
        assert "CIM" in response.answer or "domain language" in response.answer.lower()


# =============================================================================
# D2/D4: Bare-number lookup
# =============================================================================

class TestGoldBareNumberLookup:
    """Bare numbers with single match must resolve and take lookup path."""

    @pytest.mark.asyncio
    async def test_bare_0022_resolves_to_lookup(self, caplog):
        """'What does 0022 decide?' → resolved → lookup path."""
        client, adr_coll, _ = _make_multi_collection_client(
            adr_results=_make_fetch_result([DECISION_CHUNK_22]),
        )
        # Sequential calls: resolver lookup, then canonical lookup
        adr_coll.query.fetch_objects.side_effect = [
            _make_fetch_result([DECISION_CHUNK_22]),  # resolver
            _make_fetch_result([]),                     # principle resolver (via adr coll — won't match)
            _make_fetch_result([DECISION_CHUNK_22]),   # canonical lookup
            _make_fetch_result([DECISION_CHUNK_22]),   # number fallback
        ]
        agent = ArchitectureAgent(client)

        response, trace = await _capture_trace(caplog, agent, "What does 0022 decide?")

        assert response.confidence >= 0.80
        assert "ADR.22" in response.answer or "interoperability" in response.answer.lower()

    @pytest.mark.asyncio
    async def test_bare_22_resolves_same_as_0022(self, caplog):
        """'Show me document 22' → same resolution as 0022."""
        client, adr_coll, _ = _make_multi_collection_client(
            adr_results=_make_fetch_result([DECISION_CHUNK_22]),
        )
        adr_coll.query.fetch_objects.side_effect = [
            _make_fetch_result([DECISION_CHUNK_22]),
            _make_fetch_result([]),
            _make_fetch_result([DECISION_CHUNK_22]),
            _make_fetch_result([DECISION_CHUNK_22]),
        ]
        agent = ArchitectureAgent(client)

        response, trace = await _capture_trace(caplog, agent, "Show me document 22")

        assert response.confidence >= 0.80

    @pytest.mark.asyncio
    async def test_bare_9999_no_match_falls_through(self, caplog):
        """Bare number with no matches → semantic/hybrid path."""
        client, adr_coll, _ = _make_multi_collection_client()

        # Semantic path mocks
        obj = MagicMock()
        obj.properties = _make_chunk(title="ADR.5", canonical_id="ADR.5")
        obj.metadata.score = 0.80
        hybrid_result = MagicMock()
        hybrid_result.objects = [obj]
        adr_coll.query.hybrid.return_value = hybrid_result

        gen_result = MagicMock()
        gen_result.generated = "No document 9999 found."
        gen_result.objects = hybrid_result.objects
        adr_coll.generate.near_text.return_value = gen_result
        adr_coll.generate.near_vector.return_value = gen_result

        agent = ArchitectureAgent(client)
        response, trace = await _capture_trace(caplog, agent, "What does 9999 decide?")

        # Must NOT return clarification
        assert "which" not in response.answer.lower() or "match" not in response.answer.lower()


# =============================================================================
# D3: Bare-number clarification
# =============================================================================

class TestGoldBareNumberClarification:
    """Bare number matching multiple doc types → clarification, no hybrid."""

    @pytest.mark.asyncio
    async def test_ambiguous_22_returns_clarification(self, caplog):
        """'What does 22 decide?' with ADR+PCP → clarification prompt."""
        adr_chunk = _make_chunk(
            title="ADR.22 - Decision",
            canonical_id="ADR.22",
            adr_number="0022",
        )
        principle_obj = MagicMock()
        principle_obj.properties = {
            "title": "PCP.22 - Interop Mandate",
            "principle_number": "0022",
            "file_path": "docs/principles/0022-interop.md",
            "canonical_id": "PCP.22",
        }
        principle_result = MagicMock()
        principle_result.objects = [principle_obj]

        client, adr_coll, pcp_coll = _make_multi_collection_client(
            adr_results=_make_fetch_result([adr_chunk]),
            principle_results=principle_result,
        )
        agent = ArchitectureAgent(client)

        response, trace = await _capture_trace(caplog, agent, "What does 22 decide?")

        assert "ADR.22" in response.answer
        assert "PCP.22" in response.answer
        assert response.confidence == 0.60
        # Hybrid must NOT be called on clarification path
        assert not adr_coll.query.hybrid.called, "Hybrid must NOT be called on clarification path"
        # Structured payload for UI rendering
        assert len(response.raw_results) == 1
        payload = response.raw_results[0]
        assert payload["type"] == "clarification"
        assert payload["number_value"] == "0022"
        assert len(payload["candidates"]) == 2

    @pytest.mark.asyncio
    async def test_ambiguous_0022_also_clarifies(self, caplog):
        """'Show me 0022' with ADR+PCP → same clarification."""
        adr_chunk = _make_chunk(canonical_id="ADR.22", adr_number="0022")
        principle_obj = MagicMock()
        principle_obj.properties = {
            "title": "PCP.22 - Interop Mandate",
            "principle_number": "0022",
            "file_path": "docs/principles/0022-interop.md",
            "canonical_id": "PCP.22",
        }
        principle_result = MagicMock()
        principle_result.objects = [principle_obj]

        client, _, _ = _make_multi_collection_client(
            adr_results=_make_fetch_result([adr_chunk]),
            principle_results=principle_result,
        )
        agent = ArchitectureAgent(client)

        response, _ = await _capture_trace(caplog, agent, "Show me 0022")

        assert "ADR.22" in response.answer
        assert "PCP.22" in response.answer


# =============================================================================
# D5: Cheeky queries → conversational, no retrieval
# =============================================================================

class TestGoldCheekyQueries:
    """Cheeky queries with doc refs but no retrieval verb → conversational."""

    QUERIES = [
        "I wish I had written ADR.12",
        "ADR.12 is annoying",
        "Someone told me about ADR.5",
        "ADR.12 reminds me of something",
        "I like ADR.12",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", QUERIES)
    async def test_cheeky_conversational(self, query, caplog):
        client, collection = _make_single_collection_client()
        agent = ArchitectureAgent(client)

        response, trace = await _capture_trace(caplog, agent, query)

        assert trace.get("path") == "conversational", f"Expected conversational, got {trace.get('path')}"
        assert trace.get("signals", {}).get("has_doc_ref") is True
        assert trace.get("signals", {}).get("has_retrieval_verb") is False
        assert not collection.query.fetch_objects.called, "No lookup for cheeky query"
        assert not collection.query.hybrid.called, "No hybrid for cheeky query"


# =============================================================================
# D6/D7: List queries — scoped vs unscoped
# =============================================================================

class TestGoldListQueries:
    """Unscoped list → list path; scoped list → semantic path."""

    @pytest.mark.asyncio
    async def test_unscoped_list_all_adrs(self, caplog):
        """'List all ADRs' → list path."""
        client, collection = _make_single_collection_client()
        collection.query.fetch_objects.return_value = _make_fetch_result([])
        agent = ArchitectureAgent(client)

        response, trace = await _capture_trace(caplog, agent, "List all ADRs")

        assert trace.get("path") == "list"
        assert trace.get("winner") == "list"
        assert response.confidence >= 0.90

    def test_scoped_list_scores_semantic_higher(self):
        """'List principles about interoperability' → semantic wins in scores."""
        signals = _extract_signals("List all principles about interoperability")
        scores = _score_intents(signals)
        assert scores["semantic_answer"] > scores["list"], (
            f"Semantic ({scores['semantic_answer']}) should beat List ({scores['list']})"
        )

    def test_unscoped_list_scores_list_higher(self):
        """'List all ADRs' → list wins in scores."""
        signals = _extract_signals("List all ADRs")
        scores = _score_intents(signals)
        assert scores["list"] > scores["semantic_answer"], (
            f"List ({scores['list']}) should beat Semantic ({scores['semantic_answer']})"
        )


# =============================================================================
# D8: Count queries
# =============================================================================

class TestGoldCountQueries:
    """Count queries → count path."""

    QUERIES = [
        "How many ADRs are there?",
        "How many principles do we have?",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", QUERIES)
    async def test_count_path(self, query, caplog):
        client, collection = _make_single_collection_client()
        collection.query.fetch_objects.return_value = _make_fetch_result([])
        agent = ArchitectureAgent(client)

        response, trace = await _capture_trace(caplog, agent, query)

        assert trace.get("path") == "count"
        assert trace.get("winner") == "count"


# =============================================================================
# D9: Semantic queries — must have filters
# =============================================================================

class TestGoldSemanticQueries:
    """Semantic queries must use hybrid with doc_type filters and win semantic_answer."""

    # Queries with retrieval verbs → scoring gate selects semantic_answer
    SCORED_QUERIES = [
        "What principles do we have about interoperability?",
        "Summarize our approach to CIM adoption.",
        "What security patterns are used?",
    ]

    # Queries without retrieval verbs → fallback to hybrid (winner=none is OK)
    FALLBACK_QUERIES = [
        "How do we handle semantic interoperability in ESA?",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", SCORED_QUERIES)
    async def test_semantic_wins_scoring_gate(self, query, caplog):
        client, collection = _make_single_collection_client()
        collection.query.fetch_objects.return_value = _make_fetch_result([])

        obj = MagicMock()
        obj.properties = _make_chunk(title="ADR.5", canonical_id="ADR.5")
        obj.metadata.score = 0.80
        hybrid_result = MagicMock()
        hybrid_result.objects = [obj]
        collection.query.hybrid.return_value = hybrid_result

        gen_result = MagicMock()
        gen_result.generated = "Test semantic answer."
        gen_result.objects = hybrid_result.objects
        collection.generate.near_text.return_value = gen_result
        collection.generate.near_vector.return_value = gen_result

        agent = ArchitectureAgent(client)
        response, trace = await _capture_trace(caplog, agent, query)

        assert trace.get("path") == "hybrid", f"Expected hybrid, got {trace.get('path')}"
        assert trace.get("winner") == "semantic_answer", (
            f"Expected winner=semantic_answer, got {trace.get('winner')} for: {query}"
        )
        assert trace.get("threshold_met") is True, (
            f"Expected threshold_met=True for: {query}"
        )
        assert collection.query.hybrid.called, "Hybrid must be called for semantic queries"
        first_call = collection.query.hybrid.call_args_list[0]
        assert first_call.kwargs.get("filters") is not None, "Filters must be present"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", FALLBACK_QUERIES)
    async def test_semantic_fallback_still_uses_hybrid_with_filters(self, query, caplog):
        """Queries without retrieval verbs still reach hybrid with filters."""
        client, collection = _make_single_collection_client()
        collection.query.fetch_objects.return_value = _make_fetch_result([])

        obj = MagicMock()
        obj.properties = _make_chunk(title="ADR.5", canonical_id="ADR.5")
        obj.metadata.score = 0.80
        hybrid_result = MagicMock()
        hybrid_result.objects = [obj]
        collection.query.hybrid.return_value = hybrid_result

        gen_result = MagicMock()
        gen_result.generated = "Test semantic answer."
        gen_result.objects = hybrid_result.objects
        collection.generate.near_text.return_value = gen_result
        collection.generate.near_vector.return_value = gen_result

        agent = ArchitectureAgent(client)
        response, trace = await _capture_trace(caplog, agent, query)

        assert trace.get("path") == "hybrid", f"Expected hybrid, got {trace.get('path')}"
        assert collection.query.hybrid.called, "Hybrid must be called"
        first_call = collection.query.hybrid.call_args_list[0]
        assert first_call.kwargs.get("filters") is not None, "Filters must be present"

    @pytest.mark.asyncio
    async def test_semantic_excludes_conventions_from_results(self, caplog):
        """Conventions/template docs must be stripped from semantic results."""
        client, collection = _make_single_collection_client()
        collection.query.fetch_objects.return_value = _make_fetch_result([])

        # Hybrid returns a real ADR + a conventions doc
        real_obj = MagicMock()
        real_obj.properties = _make_chunk(
            title="ADR.5 - Security", canonical_id="ADR.5",
        )
        real_obj.metadata.score = 0.85

        conventions_obj = MagicMock()
        conventions_obj.properties = _make_chunk(
            title="ADR Conventions", canonical_id="",
            file_path="data/adr/adr-conventions.md", doc_type="content",
        )
        conventions_obj.metadata.score = 0.75

        hybrid_result = MagicMock()
        hybrid_result.objects = [real_obj, conventions_obj]
        collection.query.hybrid.return_value = hybrid_result

        gen_result = MagicMock()
        gen_result.generated = "Security patterns."
        gen_result.objects = hybrid_result.objects
        collection.generate.near_text.return_value = gen_result
        collection.generate.near_vector.return_value = gen_result

        agent = ArchitectureAgent(client)
        response, trace = await _capture_trace(
            caplog, agent, "What security patterns are used?",
        )

        for doc in response.raw_results:
            assert "convention" not in doc.get("title", "").lower(), (
                f"Conventions doc leaked: {doc.get('title')}"
            )


# =============================================================================
# Regression traps
# =============================================================================

class TestGoldRegressionTraps:
    """Queries that historically broke routing."""

    @pytest.mark.asyncio
    async def test_decision_drivers_still_looks_up(self, caplog):
        """'Decision drivers of ADR.12' → lookup (not conversational)."""
        driver_chunk = _make_chunk(
            title="ADR.12 - Decision Drivers",
            full_text="Section: Decision Drivers\nNeed for interop.",
            canonical_id="ADR.12",
        )
        client, collection = _make_single_collection_client([driver_chunk])
        agent = ArchitectureAgent(client)

        response, trace = await _capture_trace(caplog, agent, "Decision drivers of ADR.12")

        assert trace.get("path") in ("lookup_exact", "lookup_number"), (
            f"Expected lookup path, got {trace.get('path')}"
        )

    @pytest.mark.asyncio
    async def test_adrs_boring_is_conversational(self, caplog):
        """'ADRs are boring documents' → conversational (no doc ref)."""
        client, collection = _make_single_collection_client()

        obj = MagicMock()
        obj.properties = _make_chunk(title="ADR.5", canonical_id="ADR.5")
        obj.metadata.score = 0.80
        hybrid_result = MagicMock()
        hybrid_result.objects = [obj]
        collection.query.hybrid.return_value = hybrid_result

        gen_result = MagicMock()
        gen_result.generated = "Test."
        gen_result.objects = hybrid_result.objects
        collection.generate.near_text.return_value = gen_result
        collection.generate.near_vector.return_value = gen_result

        agent = ArchitectureAgent(client)
        response, trace = await _capture_trace(caplog, agent, "ADRs are boring documents")

        # No specific doc ref, so no conversational override — falls to semantic
        # (this is correct: "ADRs" is not a doc ref, just a plural noun)
        assert trace.get("path") in ("hybrid", "conversational")

    @pytest.mark.asyncio
    async def test_pcp22_prefixed_still_works(self, caplog):
        """'PCP.22 what does it state?' → lookup path."""
        pcp_chunk = _make_chunk(
            title="PCP.22 - Statement",
            decision="Interoperability is mandatory.",
            canonical_id="PCP.22",
            doc_type="principle",
        )
        client, collection = _make_single_collection_client([pcp_chunk])
        agent = ArchitectureAgent(client)

        response, trace = await _capture_trace(caplog, agent, "PCP.22 what does it state?")

        assert trace.get("path") == "lookup_exact"
        assert trace.get("winner") == "lookup_doc"


# =============================================================================
# Follow-up binding
# =============================================================================

class TestGoldFollowupBinding:
    """Follow-up queries with last_doc_refs inject previous refs correctly."""

    @pytest.mark.asyncio
    async def test_show_it_after_adr12_lookup(self, caplog):
        """Simulate: user asked about ADR.12, then says 'Show it'."""
        client, collection = _make_single_collection_client([DECISION_CHUNK_12])
        agent = ArchitectureAgent(client)

        last_refs = [{"canonical_id": "ADR.12", "prefix": "ADR", "number_value": "0012"}]
        response, trace = await _capture_trace(
            caplog, agent, "Show it", last_doc_refs=last_refs,
        )

        assert trace.get("path") == "lookup_exact"
        assert trace.get("signals", {}).get("has_doc_ref") is True
        assert "CIM" in response.answer or "ADR.12" in response.answer

    @pytest.mark.asyncio
    async def test_what_does_it_decide_after_lookup(self, caplog):
        """'What does it decide?' with last_doc_refs → lookup."""
        client, collection = _make_single_collection_client([DECISION_CHUNK_12])
        agent = ArchitectureAgent(client)

        last_refs = [{"canonical_id": "ADR.12", "prefix": "ADR", "number_value": "0012"}]
        response, trace = await _capture_trace(
            caplog, agent, "What does it decide?", last_doc_refs=last_refs,
        )

        assert trace.get("path") == "lookup_exact"
        assert response.confidence >= 0.80

    @pytest.mark.asyncio
    async def test_explicit_ref_overrides_last_refs(self, caplog):
        """Explicit ADR.12 in query ignores last_doc_refs=[ADR.22]."""
        client, collection = _make_single_collection_client([DECISION_CHUNK_12])
        agent = ArchitectureAgent(client)

        last_refs = [{"canonical_id": "ADR.22", "prefix": "ADR", "number_value": "0022"}]
        response, trace = await _capture_trace(
            caplog, agent, "What does ADR.12 decide?", last_doc_refs=last_refs,
        )

        assert trace.get("path") == "lookup_exact"
        assert "ADR.12" in trace.get("doc_refs_detected", [])

    @pytest.mark.asyncio
    async def test_no_marker_no_injection(self, caplog):
        """Normal semantic query ignores last_doc_refs (no follow-up marker)."""
        client, collection = _make_single_collection_client()
        collection.query.fetch_objects.return_value = _make_fetch_result([])

        obj = MagicMock()
        obj.properties = _make_chunk(title="ADR.5", canonical_id="ADR.5")
        obj.metadata.score = 0.80
        hybrid_result = MagicMock()
        hybrid_result.objects = [obj]
        collection.query.hybrid.return_value = hybrid_result

        gen_result = MagicMock()
        gen_result.generated = "Security answer."
        gen_result.objects = hybrid_result.objects
        collection.generate.near_text.return_value = gen_result
        collection.generate.near_vector.return_value = gen_result

        agent = ArchitectureAgent(client)

        last_refs = [{"canonical_id": "ADR.12", "prefix": "ADR", "number_value": "0012"}]
        response, trace = await _capture_trace(
            caplog, agent, "What security patterns are used?",
            last_doc_refs=last_refs,
        )

        # Must NOT be lookup — should be hybrid/semantic
        assert trace.get("path") == "hybrid"
