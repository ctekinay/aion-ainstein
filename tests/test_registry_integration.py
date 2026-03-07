"""Integration tests for Element Registry with the generation pipeline.

Tests the full flow: YAML → reconciliation → dct enrichment → XML.
All tests use tmp_path SQLite databases.
"""

import xml.etree.ElementTree as ET

import pytest
import yaml

from src.aion.generation import GenerationPipeline
from src.aion.registry.element_registry import (
    format_registry_context,
    init_registry_table,
    query_registry_for_prompt,
    register_element,
)


@pytest.fixture
def db(tmp_path):
    """Create a fresh SQLite DB with registry table."""
    db_path = tmp_path / "test.db"
    init_registry_table(db_path)
    return db_path


# ---------------------------------------------------------------------------
# YAML ID rewriting
# ---------------------------------------------------------------------------

class TestYamlIdRewriting:
    def test_reconcile_rewrites_element_ids(self, db):
        """Element IDs in YAML should be rewritten to canonical registry IDs."""
        # Pre-register an element
        cid = register_element("Principle", "PCP.10 Consistency", db_path=db)
        expected_short = cid[3:]

        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [
                {"id": "m1", "type": "Principle", "name": "PCP.10 Consistency",
                 "documentation": "Test"},
                {"id": "b1", "type": "BusinessRole", "name": "Grid Operator",
                 "documentation": "Operates grid"},
            ],
            "relationships": [
                {"type": "Association", "source": "m1", "target": "b1"},
            ],
        }, sort_keys=False)

        result = GenerationPipeline._reconcile_with_registry(yaml_input, ["PCP.10"], db_path=db)
        data = yaml.safe_load(result)

        # m1 should be rewritten to canonical ID
        principle = data["elements"][0]
        assert principle["id"] == expected_short

        # b1 should be rewritten to a new registry ID (UUID)
        role = data["elements"][1]
        assert len(role["id"]) == 36  # UUID format

    def test_relationship_refs_updated(self, db):
        """Relationship source/target should follow element ID remapping."""
        cid = register_element("Principle", "PCP.10 Consistency", db_path=db)
        expected_short = cid[3:]

        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [
                {"id": "m1", "type": "Principle", "name": "PCP.10 Consistency"},
                {"id": "b1", "type": "BusinessRole", "name": "Grid Operator"},
            ],
            "relationships": [
                {"type": "Association", "source": "m1", "target": "b1"},
            ],
        }, sort_keys=False)

        result = GenerationPipeline._reconcile_with_registry(yaml_input, ["PCP.10"], db_path=db)
        data = yaml.safe_load(result)

        rel = data["relationships"][0]
        assert rel["source"] == expected_short
        # target should be the new ID for Grid Operator
        role_id = data["elements"][1]["id"]
        assert rel["target"] == role_id


# ---------------------------------------------------------------------------
# source_ref preservation through reconciliation
# ---------------------------------------------------------------------------

class TestSourceRefPreservation:
    def test_source_ref_survives_reconciliation(self, db):
        """source_ref must survive reconciliation — only dct enrichment strips it."""
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [
                {"id": "m1", "type": "Principle",
                 "name": "PCP.10 Consistency",
                 "source_ref": "PCP.10",
                 "documentation": "Test"},
            ],
            "relationships": [],
        }, sort_keys=False)

        result = GenerationPipeline._reconcile_with_registry(yaml_input, ["PCP.10"], db_path=db)
        data = yaml.safe_load(result)

        # source_ref must still be present after reconciliation
        assert data["elements"][0]["source_ref"] == "PCP.10"


# ---------------------------------------------------------------------------
# Full roundtrip: reconcile → dct enrich → XML
# ---------------------------------------------------------------------------

class TestFullRoundtrip:
    def test_reconcile_then_enrich_then_xml(self, db):
        """Full pipeline: reconcile IDs → dct enrichment → valid XML."""
        from src.aion.tools.yaml_to_xml import yaml_to_archimate_xml

        # Pre-register an element
        register_element(
            "Principle", "PCP.10 Consistency",
            dct_identifier="urn:uuid:pre-existing-id",
            db_path=db,
        )

        source_metadata = {
            "PCP.10": {
                "resolved_identifier": "urn:uuid:78c31f45-real-uuid",
                "title": "Eventual Consistency by Design",
                "creator": "Grid Ops",
            },
        }

        yaml_input = yaml.dump({
            "model": {"name": "Test Model"},
            "elements": [
                {"id": "m1", "type": "Principle",
                 "name": "PCP.10 Consistency",
                 "documentation": "Consistency principle.",
                 "source_ref": "PCP.10"},
                {"id": "b1", "type": "BusinessProcess",
                 "name": "Data Sync",
                 "documentation": "Syncs data."},
            ],
            "relationships": [
                {"type": "Association", "source": "m1", "target": "b1"},
            ],
        }, sort_keys=False)

        # Step 1: Reconcile (rewrites IDs, preserves source_ref)
        reconciled = GenerationPipeline._reconcile_with_registry(
            yaml_input, ["PCP.10"], db_path=db
        )

        # Step 2: Enrich (adds dct properties, strips source_ref)
        enriched = GenerationPipeline._enrich_yaml_with_dct(
            reconciled, source_metadata
        )

        # Verify source_ref is stripped after enrichment
        enriched_data = yaml.safe_load(enriched)
        assert "source_ref" not in enriched_data["elements"][0]

        # Step 3: Convert to XML
        xml_str, info = yaml_to_archimate_xml(enriched)

        # Verify valid XML with properties
        ns = "http://www.opengroup.org/xsd/archimate/3.0/"
        root = ET.fromstring(xml_str)
        prop_defs = root.find(f"{{{ns}}}propertyDefinitions")
        assert prop_defs is not None

        def_names = set()
        for pd in prop_defs:
            name_el = pd.find(f"{{{ns}}}name")
            if name_el is not None and name_el.text:
                def_names.add(name_el.text)
        assert "dct:identifier" in def_names
        assert "dct:title" in def_names

    def test_malformed_yaml_passes_through(self, db):
        """Malformed YAML should pass through reconciliation unchanged."""
        bad_yaml = "this is not: valid: yaml: [["
        result = GenerationPipeline._reconcile_with_registry(bad_yaml, ["PCP.10"], db_path=db)
        assert result == bad_yaml


# ---------------------------------------------------------------------------
# Prompt context injection
# ---------------------------------------------------------------------------

class TestPromptContextInjection:
    def test_format_includes_known_elements(self, db):
        """Registry elements should format into a prompt-injectable block."""
        register_element(
            "Principle", "PCP.10 Consistency",
            source_doc_refs=["PCP.10"],
            db_path=db,
        )
        register_element(
            "BusinessRole", "Grid Operator",
            source_doc_refs=["PCP.10"],
            db_path=db,
        )

        known = query_registry_for_prompt(doc_refs=["PCP.10"], db_path=db)
        context = format_registry_context(known)

        assert "KNOWN ELEMENTS" in context
        assert "PCP.10 Consistency" in context
        assert "Grid Operator" in context
        assert "Principle" in context
        assert "BusinessRole" in context

    def test_empty_registry_produces_no_context(self, db):
        """Empty registry should produce empty context string."""
        known = query_registry_for_prompt(doc_refs=["PCP.10"], db_path=db)
        context = format_registry_context(known)
        assert context == ""
