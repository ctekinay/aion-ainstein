"""Unit tests for the Element Registry (Phase 2).

All tests use tmp_path SQLite databases — no interaction with production data.
"""

import logging

import pytest

from src.aion.registry.element_registry import (
    _canonical_name,
    _check_near_miss,
    _levenshtein,
    find_near_duplicates,
    format_registry_context,
    get_stats,
    init_registry_table,
    lookup_element,
    merge_elements,
    query_registry_for_prompt,
    reconcile_elements,
    register_element,
    update_element_usage,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Create a fresh in-memory-style SQLite DB with registry table."""
    db_path = tmp_path / "test.db"
    init_registry_table(db_path)
    return db_path


# ---------------------------------------------------------------------------
# _canonical_name
# ---------------------------------------------------------------------------

class TestCanonicalName:
    def test_basic_lowering(self):
        assert _canonical_name("Grid Operations") == "grid operations"

    def test_whitespace_collapse(self):
        assert _canonical_name("  Grid   Operations  ") == "grid operations"

    def test_trailing_punctuation_stripped(self):
        assert _canonical_name("Grid Operations.") == "grid operations"
        assert _canonical_name("Grid Operations...") == "grid operations"
        assert _canonical_name("Grid Operations!?") == "grid operations"

    def test_internal_punctuation_preserved(self):
        assert _canonical_name("A/B Testing Framework") == "a/b testing framework"

    def test_no_article_removal(self):
        # "A/B Testing" must NOT become "b testing"
        assert _canonical_name("A/B Testing") == "a/b testing"
        assert _canonical_name("The Grid") == "the grid"


# ---------------------------------------------------------------------------
# _levenshtein
# ---------------------------------------------------------------------------

class TestLevenshtein:
    def test_identical(self):
        assert _levenshtein("abc", "abc") == 0

    def test_insertion(self):
        assert _levenshtein("abc", "abcd") == 1

    def test_deletion(self):
        assert _levenshtein("abcd", "abc") == 1

    def test_substitution(self):
        assert _levenshtein("abc", "axc") == 1

    def test_empty(self):
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "") == 3

    def test_both_empty(self):
        assert _levenshtein("", "") == 0

    def test_realistic(self):
        # "grid operations" vs "grid operation" = 1
        assert _levenshtein("grid operations", "grid operation") == 1


# ---------------------------------------------------------------------------
# register + lookup round-trip
# ---------------------------------------------------------------------------

class TestRegisterAndLookup:
    def test_register_returns_canonical_id(self, db):
        cid = register_element("Principle", "PCP.10 Eventual Consistency", db_path=db)
        assert cid.startswith("id-")
        assert len(cid) == 39  # "id-" + 36-char UUID

    def test_lookup_after_register(self, db):
        cid = register_element(
            "Principle", "PCP.10 Eventual Consistency",
            documentation="Test doc",
            dct_identifier="urn:uuid:abc-123",
            dct_title="Eventual Consistency",
            source_doc_refs=["PCP.10"],
            db_path=db,
        )
        result = lookup_element("Principle", "PCP.10 Eventual Consistency", db_path=db)
        assert result is not None
        assert result["canonical_id"] == cid
        assert result["element_type"] == "Principle"
        assert result["display_name"] == "PCP.10 Eventual Consistency"
        assert result["documentation"] == "Test doc"
        assert result["dct_identifier"] == "urn:uuid:abc-123"
        assert result["dct_title"] == "Eventual Consistency"
        assert result["source_doc_refs"] == ["PCP.10"]
        assert result["generation_count"] == 1

    def test_case_insensitive_lookup(self, db):
        register_element("Principle", "Grid Operations", db_path=db)
        result = lookup_element("Principle", "grid operations", db_path=db)
        assert result is not None
        assert result["display_name"] == "Grid Operations"

    def test_lookup_nonexistent(self, db):
        assert lookup_element("Principle", "Nonexistent", db_path=db) is None

    def test_different_type_no_match(self, db):
        register_element("Principle", "Grid Operations", db_path=db)
        assert lookup_element("BusinessRole", "Grid Operations", db_path=db) is None

    def test_auto_generated_dct_identifier(self, db):
        register_element("Node", "API Gateway", db_path=db)
        result = lookup_element("Node", "API Gateway", db_path=db)
        assert result["dct_identifier"].startswith("urn:uuid:")


# ---------------------------------------------------------------------------
# update_element_usage
# ---------------------------------------------------------------------------

class TestUpdateUsage:
    def test_bumps_generation_count(self, db):
        cid = register_element("Principle", "Grid Ops", db_path=db)
        update_element_usage(cid, db_path=db)
        result = lookup_element("Principle", "Grid Ops", db_path=db)
        assert result["generation_count"] == 2

    def test_merges_doc_refs(self, db):
        cid = register_element(
            "Principle", "Grid Ops",
            source_doc_refs=["PCP.10"],
            db_path=db,
        )
        update_element_usage(cid, new_doc_refs=["PCP.11", "PCP.10"], db_path=db)
        result = lookup_element("Principle", "Grid Ops", db_path=db)
        assert result["source_doc_refs"] == ["PCP.10", "PCP.11"]  # sorted union
        assert result["generation_count"] == 2


# ---------------------------------------------------------------------------
# reconcile_elements
# ---------------------------------------------------------------------------

class TestReconcileElements:
    def test_new_elements_registered(self, db):
        elements = [
            {"id": "m1", "type": "Principle", "name": "PCP.10 Consistency"},
            {"id": "b1", "type": "BusinessRole", "name": "Grid Operator"},
        ]
        result = reconcile_elements(elements, doc_refs=["PCP.10"], db_path=db)
        assert len(result["id_map"]) == 2
        assert "m1" in result["id_map"]
        assert "b1" in result["id_map"]
        # IDs are UUIDs now
        for new_id in result["id_map"].values():
            assert len(new_id) == 36  # UUID without "id-" prefix

    def test_existing_elements_reused(self, db):
        cid = register_element("Principle", "PCP.10 Consistency", db_path=db)
        expected_short = cid[3:]

        elements = [
            {"id": "m1", "type": "Principle", "name": "PCP.10 Consistency"},
        ]
        result = reconcile_elements(elements, db_path=db)
        assert result["id_map"]["m1"] == expected_short
        # generation_count bumped
        entry = lookup_element("Principle", "PCP.10 Consistency", db_path=db)
        assert entry["generation_count"] == 2

    def test_mixed_new_and_existing(self, db):
        cid = register_element("Principle", "PCP.10 Consistency", db_path=db)
        elements = [
            {"id": "m1", "type": "Principle", "name": "PCP.10 Consistency"},
            {"id": "b1", "type": "BusinessRole", "name": "Grid Operator"},
        ]
        result = reconcile_elements(elements, db_path=db)
        assert result["id_map"]["m1"] == cid[3:]
        assert result["id_map"]["b1"] != cid[3:]

    def test_source_ref_preserved(self, db):
        elements = [
            {
                "id": "m1", "type": "Principle",
                "name": "PCP.10 Consistency",
                "source_ref": "PCP.10",
                "properties": {"custom:priority": "high"},
            },
        ]
        result = reconcile_elements(elements, db_path=db)
        elem = result["elements"][0]
        assert elem["source_ref"] == "PCP.10"
        assert elem["properties"] == {"custom:priority": "high"}

    def test_skips_elements_without_type_or_name(self, db):
        elements = [
            {"id": "x1"},  # no type or name
            {"id": "m1", "type": "Principle", "name": "Test"},
        ]
        result = reconcile_elements(elements, db_path=db)
        assert "x1" not in result["id_map"]
        assert "m1" in result["id_map"]


# ---------------------------------------------------------------------------
# Near-miss warnings
# ---------------------------------------------------------------------------

class TestNearMissWarnings:
    def test_near_miss_logged(self, db, caplog):
        register_element("Principle", "Grid Operations", db_path=db)
        with caplog.at_level(logging.WARNING):
            _check_near_miss("Principle", "grid operation", db_path=db)
        assert "Near-duplicate detected" in caplog.text

    def test_no_warning_for_distant_names(self, db, caplog):
        register_element("Principle", "Grid Operations", db_path=db)
        with caplog.at_level(logging.WARNING):
            _check_near_miss("Principle", "api gateway", db_path=db)
        assert "Near-duplicate" not in caplog.text


# ---------------------------------------------------------------------------
# query_registry_for_prompt
# ---------------------------------------------------------------------------

class TestQueryRegistryForPrompt:
    def test_tier1_doc_ref_overlap(self, db):
        register_element(
            "Principle", "PCP.10 Consistency",
            source_doc_refs=["PCP.10"], db_path=db,
        )
        register_element(
            "BusinessRole", "Grid Operator",
            source_doc_refs=["PCP.11"], db_path=db,
        )
        results = query_registry_for_prompt(doc_refs=["PCP.10"], db_path=db)
        assert len(results) >= 1
        assert results[0]["display_name"] == "PCP.10 Consistency"

    def test_tier2_recency_fills_remaining(self, db):
        register_element("Principle", "Old Element", db_path=db)
        register_element("Principle", "New Element", db_path=db)
        results = query_registry_for_prompt(db_path=db)
        assert len(results) == 2

    def test_respects_limit(self, db):
        for i in range(5):
            register_element("Principle", f"Element {i}", db_path=db)
        results = query_registry_for_prompt(limit=3, db_path=db)
        assert len(results) == 3

    def test_deduplicates_across_tiers(self, db):
        register_element(
            "Principle", "PCP.10 Consistency",
            source_doc_refs=["PCP.10"], db_path=db,
        )
        # Same element would appear in tier1 AND tier2
        results = query_registry_for_prompt(doc_refs=["PCP.10"], db_path=db)
        cids = [r["canonical_id"] for r in results]
        assert len(cids) == len(set(cids))


# ---------------------------------------------------------------------------
# format_registry_context
# ---------------------------------------------------------------------------

class TestFormatRegistryContext:
    def test_empty_list(self):
        assert format_registry_context([]) == ""

    def test_formats_elements(self):
        elements = [
            {
                "canonical_id": "id-abc-123",
                "element_type": "Principle",
                "display_name": "PCP.10 Consistency",
                "source_doc_refs": ["PCP.10"],
            },
        ]
        result = format_registry_context(elements)
        assert "KNOWN ELEMENTS" in result
        assert "id-abc-123" in result
        assert "Principle" in result
        assert "PCP.10 Consistency" in result
        assert "# from PCP.10" in result


# ---------------------------------------------------------------------------
# merge_elements
# ---------------------------------------------------------------------------

class TestMergeElements:
    def test_merge_unions_refs(self, db):
        cid1 = register_element(
            "Principle", "Grid Operations",
            source_doc_refs=["PCP.10"], db_path=db,
        )
        cid2 = register_element(
            "Principle", "Grid Ops",
            source_doc_refs=["PCP.11"], db_path=db,
        )
        merge_elements(cid1, cid2, db_path=db)
        survivor = lookup_element("Principle", "Grid Operations", db_path=db)
        assert survivor is not None
        assert set(survivor["source_doc_refs"]) == {"PCP.10", "PCP.11"}
        # Absorbed is deleted
        assert lookup_element("Principle", "Grid Ops", db_path=db) is None

    def test_merge_nonexistent_raises(self, db):
        cid = register_element("Principle", "Test", db_path=db)
        with pytest.raises(ValueError, match="not found"):
            merge_elements(cid, "id-nonexistent", db_path=db)

    def test_merge_keeps_max_gen_count(self, db):
        cid1 = register_element("Principle", "Grid Operations", db_path=db)
        cid2 = register_element("Principle", "Grid Ops", db_path=db)
        # Bump cid2's count
        update_element_usage(cid2, db_path=db)
        update_element_usage(cid2, db_path=db)
        merge_elements(cid1, cid2, db_path=db)
        survivor = lookup_element("Principle", "Grid Operations", db_path=db)
        assert survivor["generation_count"] == 3  # max(1, 3)


# ---------------------------------------------------------------------------
# find_near_duplicates
# ---------------------------------------------------------------------------

class TestFindNearDuplicates:
    def test_finds_near_dupes(self, db):
        register_element("Principle", "Grid Operations", db_path=db)
        register_element("Principle", "Grid Operation", db_path=db)  # distance=1
        pairs = find_near_duplicates(db_path=db)
        assert len(pairs) == 1
        assert pairs[0][2] == 1  # distance

    def test_ignores_different_types(self, db):
        register_element("Principle", "Grid Operations", db_path=db)
        register_element("BusinessRole", "Grid Operations", db_path=db)
        pairs = find_near_duplicates(db_path=db)
        assert len(pairs) == 0  # same name but different type — not dupes


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_empty_registry(self, db):
        stats = get_stats(db_path=db)
        assert stats["total"] == 0
        assert stats["by_type"] == {}
        assert stats["near_duplicates"] == 0

    def test_populated_registry(self, db):
        register_element("Principle", "PCP.10 Consistency", db_path=db)
        register_element("Principle", "PCP.11 Modularity", db_path=db)
        register_element("BusinessRole", "Grid Operator", db_path=db)
        stats = get_stats(db_path=db)
        assert stats["total"] == 3
        assert stats["by_type"] == {"BusinessRole": 1, "Principle": 2}
