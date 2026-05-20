"""Layer 3: Ingestion Integrity Tests.

Validates post-conditions on ingested data in Weaviate. Each test checks
a specific invariant that, if violated, causes silent downstream failures.

These tests require a live Weaviate instance with ingested data.
Run with: pytest -m ingestion

Cross-references to UUID Pipeline E2E suite (docs/e2e-uuid-pipeline-tests.md):
  - Invariant 5 (dct_identifier) → UUID Scenario 6 (chunk vs frontmatter UUID)
  - Invariant 10 (doc_ref round-trip) → UUID Scenario 6 (fetch won't find doc)
"""

import pytest

ADR_COLLECTION = "ArchitecturalDecision"
PRINCIPLE_COLLECTION = "Principle"

EXPECTED_ADR_COUNT = 18
EXPECTED_PCP_COUNT = 31

# Properties that should never be zero-length on well-ingested docs
ADR_REQUIRED_PROPS = {"adr_number", "title"}
PCP_REQUIRED_PROPS = {"principle_number", "title"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_all(weaviate_client, collection_name: str, props: list[str],
               include_vector: bool = False, limit: int = 500):
    """Fetch all objects from a collection with given properties."""
    col = weaviate_client.collections.get(collection_name)
    result = col.query.fetch_objects(
        limit=limit,
        include_vector=include_vector,
        return_properties=props,
    )
    return result.objects


def _get_collection_name(weaviate_client, base_name: str) -> str:
    """Resolve collection name — try base, then _OpenAI suffix."""
    collections = weaviate_client.collections.list_all()
    if base_name in collections:
        return base_name
    openai_name = f"{base_name}_OpenAI"
    if openai_name in collections:
        return openai_name
    pytest.fail(f"Collection '{base_name}' (or '{openai_name}') not found in Weaviate")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def adr_collection_name(weaviate_client):
    return _get_collection_name(weaviate_client, ADR_COLLECTION)


@pytest.fixture(scope="module")
def pcp_collection_name(weaviate_client):
    return _get_collection_name(weaviate_client, PRINCIPLE_COLLECTION)


@pytest.fixture(scope="module")
def all_adrs(weaviate_client, adr_collection_name):
    """Fetch all ADR objects (with vectors)."""
    return _fetch_all(
        weaviate_client, adr_collection_name,
        ["adr_number", "title", "status", "doc_type",
         "dct_identifier", "dct_issued", "content_hash"],
        include_vector=True,
    )


@pytest.fixture(scope="module")
def all_pcps(weaviate_client, pcp_collection_name):
    """Fetch all Principle objects (with vectors)."""
    return _fetch_all(
        weaviate_client, pcp_collection_name,
        ["principle_number", "title", "doc_type",
         "dct_identifier", "dct_issued", "content_hash"],
        include_vector=True,
    )


# ---------------------------------------------------------------------------
# Invariant 1: All 18 ADRs present
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
class TestADRCompleteness:
    """Catch: silent ingestion skip from frontmatter parse error."""

    def test_all_adrs_present(self, all_adrs):
        adr_numbers = {obj.properties.get("adr_number", "") for obj in all_adrs}
        # Remove empty and filter to unique non-empty numbers
        adr_numbers.discard("")
        adr_numbers.discard(None)
        assert len(adr_numbers) >= EXPECTED_ADR_COUNT, (
            f"Expected at least {EXPECTED_ADR_COUNT} unique ADRs, "
            f"found {len(adr_numbers)}: {sorted(adr_numbers)}"
        )


# ---------------------------------------------------------------------------
# Invariant 2: All 31 PCPs present
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
class TestPCPCompleteness:
    """Catch: _enrich_from_registry() silently returns on missing number."""

    def test_all_pcps_present(self, all_pcps):
        pcp_numbers = {obj.properties.get("principle_number", "") for obj in all_pcps}
        pcp_numbers.discard("")
        pcp_numbers.discard(None)
        assert len(pcp_numbers) >= EXPECTED_PCP_COUNT, (
            f"Expected at least {EXPECTED_PCP_COUNT} unique PCPs, "
            f"found {len(pcp_numbers)}: {sorted(pcp_numbers)}"
        )


# ---------------------------------------------------------------------------
# Invariant 3: No zero vectors
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
class TestNoZeroVectors:
    """Catch: embed_batch() returns [0.0]*dim for empty texts (lines 189, 210).

    Zero vectors in Weaviate never match any semantic query — they're
    effectively invisible to RAG retrieval.
    """

    def test_no_zero_vectors_in_adrs(self, all_adrs):
        zero_vector_docs = []
        for obj in all_adrs:
            vec = obj.vector.get("default", []) if isinstance(obj.vector, dict) else (obj.vector or [])
            if vec and all(v == 0.0 for v in vec):
                adr_num = obj.properties.get("adr_number", "unknown")
                zero_vector_docs.append(adr_num)
        assert not zero_vector_docs, (
            f"ADRs with zero vectors (invisible to search): {zero_vector_docs}"
        )

    def test_no_zero_vectors_in_pcps(self, all_pcps):
        zero_vector_docs = []
        for obj in all_pcps:
            vec = obj.vector.get("default", []) if isinstance(obj.vector, dict) else (obj.vector or [])
            if vec and all(v == 0.0 for v in vec):
                pcp_num = obj.properties.get("principle_number", "unknown")
                zero_vector_docs.append(pcp_num)
        assert not zero_vector_docs, (
            f"PCPs with zero vectors (invisible to search): {zero_vector_docs}"
        )


# ---------------------------------------------------------------------------
# Invariant 4: No duplicate chunks (content_hash uniqueness)
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
class TestNoDuplicateChunks:
    """Catch: re-ingestion without dedup produces duplicate search results."""

    def test_no_duplicate_adr_chunks(self, all_adrs):
        hashes = [obj.properties.get("content_hash", "") for obj in all_adrs]
        hashes = [h for h in hashes if h]
        duplicates = {h for h in hashes if hashes.count(h) > 1}
        assert not duplicates, (
            f"Duplicate content_hash values in ADR collection: {len(duplicates)} hashes "
            f"have multiple chunks"
        )

    def test_no_duplicate_pcp_chunks(self, all_pcps):
        hashes = [obj.properties.get("content_hash", "") for obj in all_pcps]
        hashes = [h for h in hashes if h]
        duplicates = {h for h in hashes if hashes.count(h) > 1}
        assert not duplicates, (
            f"Duplicate content_hash values in Principle collection: {len(duplicates)} hashes "
            f"have multiple chunks"
        )


# ---------------------------------------------------------------------------
# Invariant 5: dct_identifier present on all PCPs
# Cross-ref: failure here → UUID pipeline Scenario 6 will also fail.
#   "dct_identifier missing — fix ingestion first."
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
class TestDctIdentifierPresent:
    """Catch: frontmatter extraction failure breaks UUID pipeline."""

    def test_all_pcps_have_dct_identifier(self, all_pcps):
        # Deduplicate by principle_number — only need one chunk per PCP
        seen = {}
        for obj in all_pcps:
            pn = obj.properties.get("principle_number", "")
            if pn and pn not in seen:
                seen[pn] = obj.properties.get("dct_identifier", "")

        missing = [pn for pn, dct_id in seen.items() if not dct_id]
        assert not missing, (
            f"PCPs missing dct_identifier (breaks UUID pipeline — see "
            f"docs/e2e-uuid-pipeline-tests.md Scenario 6): {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Invariant 6: dct_issued present on all docs
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
class TestDctIssuedPresent:
    """Catch: temporal queries fail without dct_issued."""

    def test_pcps_have_dct_issued(self, all_pcps):
        seen = {}
        for obj in all_pcps:
            pn = obj.properties.get("principle_number", "")
            if pn and pn not in seen:
                seen[pn] = obj.properties.get("dct_issued", "")

        missing = [pn for pn, issued in seen.items() if not issued]
        # Warn rather than fail — dct_issued may legitimately be absent
        # on older docs. Track coverage percentage.
        coverage = (len(seen) - len(missing)) / max(len(seen), 1) * 100
        assert coverage >= 50, (
            f"Only {coverage:.0f}% of PCPs have dct_issued. "
            f"Missing: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Invariant 7: Section chunks inherit parent metadata
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
class TestChunkMetadataInheritance:
    """Catch: chunking strips parent adr_number/principle_number from sections."""

    def test_pcp_section_chunks_have_principle_number(self, all_pcps):
        orphans = []
        for obj in all_pcps:
            chunk_type = obj.properties.get("chunk_type", "")
            pn = obj.properties.get("principle_number", "")
            if chunk_type == "section" and not pn:
                title = obj.properties.get("title", "unknown")
                orphans.append(title)
        assert not orphans, (
            f"Section chunks missing principle_number (orphaned): {orphans[:10]}"
        )

    def test_adr_section_chunks_have_adr_number(self, all_adrs):
        orphans = []
        for obj in all_adrs:
            chunk_type = obj.properties.get("chunk_type", "")
            an = obj.properties.get("adr_number", "")
            if chunk_type == "section" and not an:
                title = obj.properties.get("title", "unknown")
                orphans.append(title)
        assert not orphans, (
            f"Section chunks missing adr_number (orphaned): {orphans[:10]}"
        )


# ---------------------------------------------------------------------------
# Invariant 8: ADR status field populated
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
class TestADRStatusPopulated:
    """Catch: _enrich_from_registry() silent failure leaves status empty."""

    def test_accepted_adrs_have_status(self, all_adrs):
        seen = {}
        for obj in all_adrs:
            an = obj.properties.get("adr_number", "")
            if an and an not in seen:
                seen[an] = obj.properties.get("status", "")

        missing = [an for an, status in seen.items() if not status]
        # Allow some missing — draft ADRs may not have status
        coverage = (len(seen) - len(missing)) / max(len(seen), 1) * 100
        assert coverage >= 70, (
            f"Only {coverage:.0f}% of ADRs have status. "
            f"Missing: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Invariant 9: Embedding dimension consistency
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
class TestEmbeddingDimensionConsistency:
    """Catch: model change creates incompatible vectors in same collection."""

    def test_all_adr_vectors_same_dimension(self, all_adrs):
        dims = set()
        for obj in all_adrs:
            vec = obj.vector.get("default", []) if isinstance(obj.vector, dict) else (obj.vector or [])
            if vec:
                dims.add(len(vec))
        assert len(dims) <= 1, (
            f"ADR collection has mixed vector dimensions: {dims}. "
            f"This indicates an embedding model change during ingestion."
        )

    def test_all_pcp_vectors_same_dimension(self, all_pcps):
        dims = set()
        for obj in all_pcps:
            vec = obj.vector.get("default", []) if isinstance(obj.vector, dict) else (obj.vector or [])
            if vec:
                dims.add(len(vec))
        assert len(dims) <= 1, (
            f"Principle collection has mixed vector dimensions: {dims}. "
            f"This indicates an embedding model change during ingestion."
        )


# ---------------------------------------------------------------------------
# Invariant 10: Cross-collection doc_ref round-trip
# Cross-ref: failure here → UUID pipeline Scenario 6 (fetch won't find doc).
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
class TestDocRefRoundTrip:
    """Catch: principle_number stored as '0012' but _fetch_pcps() queries
    with int() conversion — format mismatch breaks lookup silently."""

    def test_principle_number_format_is_queryable(self, weaviate_client, pcp_collection_name):
        """Verify we can fetch a PCP by its stored principle_number format."""
        from weaviate.classes.query import Filter

        col = weaviate_client.collections.get(pcp_collection_name)

        # First, get a sample principle_number
        sample = col.query.fetch_objects(
            limit=1,
            return_properties=["principle_number"],
        )
        if not sample.objects:
            pytest.skip("No principles in Weaviate")

        pn = sample.objects[0].properties["principle_number"]

        # Now query for it exactly as stored
        results = col.query.fetch_objects(
            filters=Filter.by_property("principle_number").equal(pn),
            limit=10,
            return_properties=["principle_number", "title"],
        )
        assert len(results.objects) > 0, (
            f"Querying principle_number='{pn}' returned 0 results. "
            f"Format mismatch between stored value and query filter. "
            f"This will cause UUID pipeline Scenario 6 to fail."
        )

    def test_adr_number_format_is_queryable(self, weaviate_client, adr_collection_name):
        """Verify we can fetch an ADR by its stored adr_number format."""
        from weaviate.classes.query import Filter

        col = weaviate_client.collections.get(adr_collection_name)

        sample = col.query.fetch_objects(
            limit=1,
            return_properties=["adr_number"],
        )
        if not sample.objects:
            pytest.skip("No ADRs in Weaviate")

        an = sample.objects[0].properties["adr_number"]

        results = col.query.fetch_objects(
            filters=Filter.by_property("adr_number").equal(an),
            limit=10,
            return_properties=["adr_number", "title"],
        )
        assert len(results.objects) > 0, (
            f"Querying adr_number='{an}' returned 0 results. "
            f"Format mismatch between stored value and query filter."
        )


# ---------------------------------------------------------------------------
# C6: Index-Time Ownership Correction (ADR candidate C6)
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
class TestPrincipleOwnershipCorrect:
    """Verify that principle ownership is correct in Weaviate (written at ingestion time).

    These checks confirm the C6 ADR implementation: ownership is authoritative
    in Weaviate, corrected during ingestion by _override_principle_ownership(),
    not patched at query time.

    Confirmation criteria from C6-index-time-ownership-correction.md:
      1. PCP.21 → owner_team_abbr = "BA"
      2. PCP.35 → owner_team_abbr = "DO"
      3. PCP.41 → owner_team_abbr = "NB-EA"
      4. PCP.39 → owner_team_abbr = "ESA" (non-contiguous ESA principle)
      5. No correction block in rag_search._build_result (structural, not live)
    """

    def _fetch_by_pcp(self, weaviate_client, principle_collection_name, pcp_number: str):
        """Fetch a single principle by principle_number (zero-padded 4-digit string)."""
        from weaviate.classes.query import Filter

        col = weaviate_client.collections.get(principle_collection_name)
        result = col.query.fetch_objects(
            filters=Filter.by_property("principle_number").equal(pcp_number),
            limit=1,
            return_properties=["principle_number", "owner_team_abbr", "owner_team"],
        )
        if not result.objects:
            pytest.skip(f"PCP.{pcp_number} not found in Weaviate")
        return result.objects[0].properties

    def test_pcp21_owner_is_ba(self, weaviate_client, principle_collection_name):
        """PCP.21 belongs to Business Architecture."""
        props = self._fetch_by_pcp(weaviate_client, principle_collection_name, "0021")
        assert props.get("owner_team_abbr") == "BA", (
            f"PCP.0021 has owner_team_abbr={props.get('owner_team_abbr')!r}, expected 'BA'. "
            f"Re-run ingestion with the C6 fix to correct ownership in Weaviate."
        )

    def test_pcp35_owner_is_do(self, weaviate_client, principle_collection_name):
        """PCP.35 belongs to Data Office."""
        props = self._fetch_by_pcp(weaviate_client, principle_collection_name, "0035")
        assert props.get("owner_team_abbr") == "DO", (
            f"PCP.0035 has owner_team_abbr={props.get('owner_team_abbr')!r}, expected 'DO'."
        )

    def test_pcp41_owner_is_nb_ea(self, weaviate_client, principle_collection_name):
        """PCP.41 belongs to Netbeheer Nederland Enterprise Architecture."""
        props = self._fetch_by_pcp(weaviate_client, principle_collection_name, "0041")
        assert props.get("owner_team_abbr") == "NB-EA", (
            f"PCP.0041 has owner_team_abbr={props.get('owner_team_abbr')!r}, expected 'NB-EA'."
        )

    def test_pcp39_owner_is_esa(self, weaviate_client, principle_collection_name):
        """PCP.39 belongs to ESA (non-contiguous — the original reported symptom)."""
        props = self._fetch_by_pcp(weaviate_client, principle_collection_name, "0039")
        assert props.get("owner_team_abbr") == "ESA", (
            f"PCP.0039 has owner_team_abbr={props.get('owner_team_abbr')!r}, expected 'ESA'."
        )

    def test_no_query_time_correction_in_build_result(self):
        """_build_result() must not contain a query-time ownership correction block.

        Structural guard: if this test fails, the C6 removal was partially reverted.
        """
        import inspect
        from aion.tools.rag_search import RAGSearchToolkit
        src = inspect.getsource(RAGSearchToolkit._build_result)
        assert "_get_principle_owners" not in src, (
            "_build_result() still references _get_principle_owners — "
            "the query-time correction was not fully removed."
        )
        assert "_OWNER_METADATA" not in src, (
            "_build_result() still references _OWNER_METADATA — "
            "the query-time correction was not fully removed."
        )
