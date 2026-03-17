"""Tests for Phase 3: Canonical UUID Pipeline.

Covers frontmatter dct:identifier preservation through the pipeline,
dct:issued/dct:language enrichment, and UUID integrity checks.
All tests use tmp_path SQLite databases.
"""

import logging

import pytest
import yaml

from aion.chunking.models import ChunkMetadata
from aion.generation import GenerationPipeline
from aion.tools.reconciliation import build_source_metadata, enrich_yaml_with_dct
from aion.registry.element_registry import (
    init_registry_table,
    lookup_element,
    reconcile_elements,
)

# ---------------------------------------------------------------------------
# ChunkMetadata dct fields
# ---------------------------------------------------------------------------

class TestChunkMetadataDctFields:
    def test_dct_fields_round_trip(self):
        """dct_identifier and dct_issued survive to_dict() serialization."""
        meta = ChunkMetadata(
            dct_identifier="urn:uuid:abc-123",
            dct_issued="2025-06-15",
        )
        d = meta.to_dict()
        assert d["dct_identifier"] == "urn:uuid:abc-123"
        assert d["dct_issued"] == "2025-06-15"

    def test_defaults_are_empty(self):
        """Default dct fields are empty strings."""
        meta = ChunkMetadata()
        assert meta.dct_identifier == ""
        assert meta.dct_issued == ""


# ---------------------------------------------------------------------------
# _build_source_metadata() — dct_identifier preference
# ---------------------------------------------------------------------------

class TestBuildSourceMetadataDctPreference:
    def test_prefers_dct_identifier_over_chunk_uuid(self):
        """When dct_identifier is present, it takes precedence over chunk UUID."""
        sources = [{
            "principle_number": "0012",
            "title": "Business Driven Data Readiness",
            "kb_uuid": "random-chunk-uuid",
            "dct_identifier": "urn:uuid:3c4d5e6f-7a8b-4c9d-0e1f-2a3b4c5d6e7f",
        }]
        meta = build_source_metadata(sources)
        assert meta["PCP.12"]["resolved_identifier"] == "urn:uuid:3c4d5e6f-7a8b-4c9d-0e1f-2a3b4c5d6e7f"

    def test_falls_back_to_kb_uuid(self):
        """When dct_identifier is empty, falls back to urn:uuid:{kb_uuid}."""
        sources = [{
            "principle_number": "0010",
            "title": "Test",
            "kb_uuid": "fallback-uuid-123",
            "dct_identifier": "",
        }]
        meta = build_source_metadata(sources)
        assert meta["PCP.10"]["resolved_identifier"] == "urn:uuid:fallback-uuid-123"

    def test_no_double_urn_prefix(self):
        """dct_identifier already has urn:uuid: prefix — must not double it."""
        sources = [{
            "principle_number": "0012",
            "title": "Test",
            "kb_uuid": "ignored",
            "dct_identifier": "urn:uuid:abc-def",
        }]
        meta = build_source_metadata(sources)
        assert meta["PCP.12"]["resolved_identifier"] == "urn:uuid:abc-def"
        assert "urn:uuid:urn:uuid:" not in meta["PCP.12"]["resolved_identifier"]

    def test_raw_dct_identifier_stored(self):
        """_raw_dct_identifier is stored for UUID integrity checking."""
        sources = [{
            "principle_number": "0012",
            "title": "Test",
            "kb_uuid": "random",
            "dct_identifier": "urn:uuid:abc-def",
        }]
        meta = build_source_metadata(sources)
        assert meta["PCP.12"]["_raw_dct_identifier"] == "urn:uuid:abc-def"

    def test_issued_and_language_added(self):
        """dct_issued and language are included in source metadata."""
        sources = [{
            "principle_number": "0012",
            "title": "Test",
            "kb_uuid": "uuid-12",
            "dct_issued": "2025-06-15",
        }]
        meta = build_source_metadata(sources)
        assert meta["PCP.12"]["issued"] == "2025-06-15"
        assert meta["PCP.12"]["language"] == "en"

    def test_missing_dct_issued_not_in_metadata(self):
        """When dct_issued is empty, 'issued' key is absent from entry."""
        sources = [{
            "principle_number": "0010",
            "title": "Test",
            "kb_uuid": "uuid-10",
            "dct_issued": "",
        }]
        meta = build_source_metadata(sources)
        assert "issued" not in meta["PCP.10"]

    def test_dct_identifier_only_no_chunk_uuid(self):
        """Source with dct_identifier but no chunk UUID should still be included."""
        sources = [{
            "principle_number": "0012",
            "title": "Test",
            "kb_uuid": "",
            "dct_identifier": "urn:uuid:abc-def",
        }]
        meta = build_source_metadata(sources)
        assert "PCP.12" in meta
        assert meta["PCP.12"]["resolved_identifier"] == "urn:uuid:abc-def"


# ---------------------------------------------------------------------------
# _enrich_yaml_with_dct() — issued, language, UUID integrity
# ---------------------------------------------------------------------------

class TestEnrichYamlDctExtended:
    def test_issued_and_language_in_enriched_yaml(self):
        """dct:issued and dct:language appear in enriched element properties."""
        metadata = {
            "PCP.10": {
                "resolved_identifier": "urn:uuid:abc-123",
                "title": "Test Principle",
                "issued": "2025-06-15",
                "language": "en",
                "_raw_dct_identifier": "urn:uuid:abc-123",
            },
        }
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [{
                "id": "m1",
                "type": "Principle",
                "name": "PCP.10 Test",
                "source_ref": "PCP.10",
            }],
            "relationships": [],
        }, sort_keys=False)

        result = enrich_yaml_with_dct(yaml_input, metadata)
        data = yaml.safe_load(result)
        props = data["elements"][0]["properties"]
        assert props["dct:issued"] == "2025-06-15"
        assert props["dct:language"] == "en"

    def test_uuid_mismatch_logs_warning(self, caplog):
        """UUID mismatch between enriched and raw KB value triggers warning."""
        metadata = {
            "PCP.10": {
                "resolved_identifier": "urn:uuid:enriched-different",
                "title": "Test",
                "_raw_dct_identifier": "urn:uuid:original-from-kb",
            },
        }
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [{
                "id": "m1",
                "type": "Principle",
                "name": "PCP.10 Test",
                "source_ref": "PCP.10",
            }],
            "relationships": [],
        }, sort_keys=False)

        with caplog.at_level(logging.WARNING, logger="aion.tools.reconciliation"):
            enrich_yaml_with_dct(yaml_input, metadata)

        assert "UUID mismatch" in caplog.text
        assert "enriched-different" in caplog.text
        assert "original-from-kb" in caplog.text

    def test_no_warning_when_uuids_match(self, caplog):
        """No warning when enriched UUID matches raw KB value."""
        metadata = {
            "PCP.10": {
                "resolved_identifier": "urn:uuid:abc-123",
                "title": "Test",
                "_raw_dct_identifier": "urn:uuid:abc-123",
            },
        }
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [{
                "id": "m1",
                "type": "Principle",
                "name": "PCP.10 Test",
                "source_ref": "PCP.10",
            }],
            "relationships": [],
        }, sort_keys=False)

        with caplog.at_level(logging.WARNING, logger="aion.tools.reconciliation"):
            enrich_yaml_with_dct(yaml_input, metadata)

        assert "UUID mismatch" not in caplog.text


# ---------------------------------------------------------------------------
# reconcile_elements() — source_metadata for dct_identifier
# ---------------------------------------------------------------------------

class TestReconcileWithSourceMetadata:
    @pytest.fixture
    def db(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_registry_table(db_path)
        return db_path

    def test_new_element_gets_dct_from_source_metadata(self, db):
        """New element with source_ref + matching source_metadata gets KB UUID."""
        source_metadata = {
            "PCP.10": {
                "resolved_identifier": "urn:uuid:canonical-from-kb",
                "title": "Eventual Consistency",
            },
        }
        elements = [{
            "id": "m1",
            "type": "Principle",
            "name": "PCP.10 Consistency",
            "source_ref": "PCP.10",
        }]
        reconcile_elements(elements, source_metadata=source_metadata, db_path=db)

        entry = lookup_element("Principle", "PCP.10 Consistency", db_path=db)
        assert entry is not None
        assert entry["dct_identifier"] == "urn:uuid:canonical-from-kb"

    def test_new_element_without_source_ref_gets_auto_uuid(self, db):
        """New element without source_ref gets auto-generated UUID."""
        elements = [{
            "id": "b1",
            "type": "BusinessRole",
            "name": "Grid Operator",
        }]
        reconcile_elements(elements, db_path=db)

        entry = lookup_element("BusinessRole", "Grid Operator", db_path=db)
        assert entry is not None
        assert entry["dct_identifier"].startswith("urn:uuid:")
