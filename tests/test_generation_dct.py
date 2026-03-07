"""Tests for deterministic dct property enrichment in the generation pipeline.

Covers _normalize_ref(), _build_source_metadata(), and _enrich_yaml_with_dct().
"""

import pytest
import yaml

from src.aion.generation import GenerationPipeline

# ---------------------------------------------------------------------------
# _normalize_ref()
# ---------------------------------------------------------------------------

class TestNormalizeRef:
    """Test source_ref normalization to canonical form."""

    @pytest.mark.parametrize("raw,expected", [
        ("PCP.10", "PCP.10"),
        ("PCP 10", "PCP.10"),
        ("PCP-10", "PCP.10"),
        ("PCP10", "PCP.10"),
        ("pcp.10", "PCP.10"),
        ("pcp 10", "PCP.10"),
        ("Principle 10", "PCP.10"),
        ("PRINCIPLE.10", "PCP.10"),
        ("PRINCIPLE-10", "PCP.10"),
        ("PCP.0010", "PCP.10"),  # strips leading zeros
        ("ADR.29", "ADR.29"),
        ("ADR 29", "ADR.29"),
        ("ADR-29", "ADR.29"),
        ("adr.29", "ADR.29"),
        ("ADR.0029", "ADR.29"),
    ])
    def test_valid_refs(self, raw, expected):
        assert GenerationPipeline._normalize_ref(raw) == expected

    @pytest.mark.parametrize("raw", [
        "0010",           # bare number — ambiguous
        "POLICY.5",       # unknown prefix
        "some random text",
        "",
        "   ",
    ])
    def test_invalid_refs_return_none(self, raw):
        assert GenerationPipeline._normalize_ref(raw) is None


# ---------------------------------------------------------------------------
# _build_source_metadata()
# ---------------------------------------------------------------------------

class TestBuildSourceMetadata:
    """Test metadata lookup construction from fetched sources."""

    def test_principle_source(self):
        sources = [{
            "principle_number": "0010",
            "title": "Eventual Consistency by Design",
            "kb_uuid": "78c31f45-4ed7-4025-99d5-b29fa23b54a5",
            "owner_display": "Grid Operations Team",
        }]
        meta = GenerationPipeline._build_source_metadata(sources)
        assert "PCP.10" in meta
        assert meta["PCP.10"]["kb_uuid"] == "urn:uuid:78c31f45-4ed7-4025-99d5-b29fa23b54a5"
        assert meta["PCP.10"]["title"] == "Eventual Consistency by Design"
        assert meta["PCP.10"]["creator"] == "Grid Operations Team"

    def test_adr_source(self):
        sources = [{
            "adr_number": "0029",
            "title": "Use CIM Standards",
            "kb_uuid": "aaaa-bbbb-cccc",
        }]
        meta = GenerationPipeline._build_source_metadata(sources)
        assert "ADR.29" in meta
        assert meta["ADR.29"]["kb_uuid"] == "urn:uuid:aaaa-bbbb-cccc"
        assert meta["ADR.29"]["title"] == "Use CIM Standards"
        assert "creator" not in meta["ADR.29"]  # no owner_display

    def test_no_kb_uuid_skipped(self):
        sources = [{
            "principle_number": "0010",
            "title": "Missing UUID",
            "kb_uuid": "",
        }]
        meta = GenerationPipeline._build_source_metadata(sources)
        assert meta == {}

    def test_multiple_sources(self):
        sources = [
            {
                "principle_number": "0010",
                "title": "PCP 10",
                "kb_uuid": "uuid-10",
            },
            {
                "principle_number": "0011",
                "title": "PCP 11",
                "kb_uuid": "uuid-11",
                "owner_display": "Team B",
            },
        ]
        meta = GenerationPipeline._build_source_metadata(sources)
        assert len(meta) == 2
        assert "PCP.10" in meta
        assert "PCP.11" in meta
        assert "creator" not in meta["PCP.10"]
        assert meta["PCP.11"]["creator"] == "Team B"

    def test_both_principle_and_adr_logs_warning(self, caplog):
        """When a source has both fields, principle_number wins with a warning."""
        sources = [{
            "principle_number": "0010",
            "adr_number": "0029",
            "title": "Ambiguous",
            "kb_uuid": "uuid-ambiguous",
        }]
        meta = GenerationPipeline._build_source_metadata(sources)
        assert "PCP.10" in meta
        assert "ADR.29" not in meta
        assert "both principle_number" in caplog.text


# ---------------------------------------------------------------------------
# _enrich_yaml_with_dct()
# ---------------------------------------------------------------------------

class TestEnrichYamlWithDct:
    """Test YAML enrichment with dct properties."""

    METADATA = {
        "PCP.10": {
            "kb_uuid": "urn:uuid:78c31f45-4ed7-4025-99d5-b29fa23b54a5",
            "title": "Eventual Consistency by Design",
            "creator": "Grid Operations Team",
            "issued": "2025-06-15",
            "language": "en",
            "_raw_dct_identifier": "urn:uuid:78c31f45-4ed7-4025-99d5-b29fa23b54a5",
        },
        "ADR.29": {
            "kb_uuid": "urn:uuid:aaaa-bbbb-cccc-dddd",
            "title": "Use CIM Standards",
            "_raw_dct_identifier": "urn:uuid:aaaa-bbbb-cccc-dddd",
        },
    }

    def test_explicit_source_ref(self):
        """source_ref on element -> dct properties added, source_ref stripped."""
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [{
                "id": "m1",
                "type": "Principle",
                "name": "PCP.10 Eventual Consistency",
                "documentation": "...",
                "source_ref": "PCP.10",
            }],
            "relationships": [],
        }, sort_keys=False)

        result = GenerationPipeline._enrich_yaml_with_dct(yaml_input, self.METADATA)
        data = yaml.safe_load(result)

        elem = data["elements"][0]
        assert "source_ref" not in elem  # stripped
        assert elem["properties"]["dct:identifier"] == "urn:uuid:78c31f45-4ed7-4025-99d5-b29fa23b54a5"
        assert elem["properties"]["dct:title"] == "Eventual Consistency by Design"
        assert elem["properties"]["dct:creator"] == "Grid Operations Team"
        assert elem["properties"]["dct:issued"] == "2025-06-15"
        assert elem["properties"]["dct:language"] == "en"

    def test_fallback_principle_name(self):
        """No source_ref but Principle named PCP.10 -> fallback infers."""
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [{
                "id": "m1",
                "type": "Principle",
                "name": "PCP.10 Eventual Consistency by Design",
                "documentation": "...",
            }],
            "relationships": [],
        }, sort_keys=False)

        result = GenerationPipeline._enrich_yaml_with_dct(yaml_input, self.METADATA)
        data = yaml.safe_load(result)

        elem = data["elements"][0]
        assert elem["properties"]["dct:identifier"] == "urn:uuid:78c31f45-4ed7-4025-99d5-b29fa23b54a5"

    def test_fallback_type_gate_blocks_derived_elements(self):
        """BusinessRole named 'PCP.10 Review Board' should NOT get dct properties."""
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [{
                "id": "b1",
                "type": "BusinessRole",
                "name": "PCP.10 Review Board",
                "documentation": "...",
            }],
            "relationships": [],
        }, sort_keys=False)

        result = GenerationPipeline._enrich_yaml_with_dct(yaml_input, self.METADATA)
        data = yaml.safe_load(result)

        elem = data["elements"][0]
        assert "properties" not in elem or "dct:identifier" not in elem.get("properties", {})

    def test_no_match_no_error(self):
        """Element with source_ref that doesn't match metadata -> no properties, no error."""
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [{
                "id": "m1",
                "type": "Principle",
                "name": "Some Principle",
                "documentation": "...",
                "source_ref": "PCP.99",
            }],
            "relationships": [],
        }, sort_keys=False)

        result = GenerationPipeline._enrich_yaml_with_dct(yaml_input, self.METADATA)
        data = yaml.safe_load(result)

        elem = data["elements"][0]
        assert "source_ref" not in elem  # still stripped
        assert "properties" not in elem

    def test_malformed_yaml_returns_original(self):
        """Malformed YAML input -> returns original text unchanged."""
        bad_yaml = "elements:\n  - id: [broken yaml"
        result = GenerationPipeline._enrich_yaml_with_dct(bad_yaml, self.METADATA)
        assert result == bad_yaml

    def test_no_elements_key_returns_original(self):
        """YAML without 'elements' key -> returns unchanged."""
        yaml_input = yaml.dump({"model": {"name": "Test"}}, sort_keys=False)
        result = GenerationPipeline._enrich_yaml_with_dct(yaml_input, self.METADATA)
        data = yaml.safe_load(result)
        assert "elements" not in data

    def test_overwrites_existing_dct_identifier(self):
        """LLM-generated dct:identifier gets overwritten by enrichment."""
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [{
                "id": "m1",
                "type": "Principle",
                "name": "PCP.10 Eventual Consistency",
                "documentation": "...",
                "source_ref": "PCP.10",
                "properties": {
                    "dct:identifier": "urn:uuid:wrong-uuid-from-llm",
                    "dct:language": "en",  # should be preserved
                },
            }],
            "relationships": [],
        }, sort_keys=False)

        result = GenerationPipeline._enrich_yaml_with_dct(yaml_input, self.METADATA)
        data = yaml.safe_load(result)

        elem = data["elements"][0]
        assert elem["properties"]["dct:identifier"] == "urn:uuid:78c31f45-4ed7-4025-99d5-b29fa23b54a5"
        assert elem["properties"]["dct:language"] == "en"  # preserved

    def test_empty_metadata_strips_source_ref(self):
        """Even with empty metadata, source_ref is stripped."""
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [{
                "id": "m1",
                "type": "Principle",
                "name": "PCP.10 Eventual Consistency",
                "documentation": "...",
                "source_ref": "PCP.10",
            }],
            "relationships": [],
        }, sort_keys=False)

        result = GenerationPipeline._enrich_yaml_with_dct(yaml_input, {})
        data = yaml.safe_load(result)

        elem = data["elements"][0]
        assert "source_ref" not in elem
        assert "properties" not in elem

    def test_no_creator_when_absent(self):
        """dct:creator is not added when owner_display is absent in metadata."""
        meta = {
            "ADR.29": {
                "kb_uuid": "urn:uuid:aaaa-bbbb",
                "title": "Use CIM Standards",
                # no "creator" key
            },
        }
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [{
                "id": "m1",
                "type": "ArchitecturalDecision",
                "name": "ADR.29 Use CIM Standards",
                "documentation": "...",
                "source_ref": "ADR.29",
            }],
            "relationships": [],
        }, sort_keys=False)

        result = GenerationPipeline._enrich_yaml_with_dct(yaml_input, meta)
        data = yaml.safe_load(result)

        elem = data["elements"][0]
        assert "dct:creator" not in elem.get("properties", {})
        assert elem["properties"]["dct:identifier"] == "urn:uuid:aaaa-bbbb"

    def test_observability_logging(self, caplog):
        """Enrichment emits a log line with correct counts."""
        yaml_input = yaml.dump({
            "model": {"name": "Test"},
            "elements": [
                {
                    "id": "m1",
                    "type": "Principle",
                    "name": "PCP.10 Eventual Consistency",
                    "documentation": "...",
                    "source_ref": "PCP.10",
                },
                {
                    "id": "b1",
                    "type": "BusinessProcess",
                    "name": "Data Sync",
                    "documentation": "...",
                },
                {
                    "id": "m2",
                    "type": "Principle",
                    "name": "PCP.10 Backup Principle",
                    "documentation": "...",
                    # no source_ref — fallback should fire
                },
            ],
            "relationships": [],
        }, sort_keys=False)

        import logging
        with caplog.at_level(logging.INFO, logger="src.aion.generation"):
            GenerationPipeline._enrich_yaml_with_dct(yaml_input, self.METADATA)

        # Should log: 2/3 elements enriched (1 via source_ref, 1 via name fallback)
        assert "dct enrichment:" in caplog.text
        assert "2/3 elements enriched" in caplog.text
        assert "1 via source_ref" in caplog.text
        assert "1 via name fallback" in caplog.text

    def test_source_ref_normalization_variants(self):
        """Various source_ref formats all resolve correctly."""
        for variant in ["PCP 10", "PCP-10", "pcp.10", "Principle 10"]:
            yaml_input = yaml.dump({
                "model": {"name": "Test"},
                "elements": [{
                    "id": "m1",
                    "type": "Principle",
                    "name": "Some Principle",
                    "documentation": "...",
                    "source_ref": variant,
                }],
                "relationships": [],
            }, sort_keys=False)

            result = GenerationPipeline._enrich_yaml_with_dct(yaml_input, self.METADATA)
            data = yaml.safe_load(result)
            elem = data["elements"][0]
            assert elem["properties"]["dct:identifier"] == "urn:uuid:78c31f45-4ed7-4025-99d5-b29fa23b54a5", \
                f"Failed for source_ref variant: {variant}"


# ---------------------------------------------------------------------------
# Integration: enrichment + yaml_to_archimate_xml round-trip
# ---------------------------------------------------------------------------

class TestEnrichmentXmlRoundTrip:
    """Verify enriched YAML produces valid XML with dct properties."""

    def test_enriched_yaml_produces_valid_xml(self):
        """Full pipeline: source_ref -> enrichment -> XML with property elements."""
        import xml.etree.ElementTree as ET

        from src.aion.tools.yaml_to_xml import yaml_to_archimate_xml

        metadata = {
            "PCP.10": {
                "kb_uuid": "urn:uuid:78c31f45-4ed7-4025-99d5-b29fa23b54a5",
                "title": "Eventual Consistency by Design",
                "creator": "Grid Ops",
                "issued": "2025-06-15",
                "language": "en",
                "_raw_dct_identifier": "urn:uuid:78c31f45-4ed7-4025-99d5-b29fa23b54a5",
            },
        }

        yaml_input = yaml.dump({
            "model": {"name": "PCP.10 Architecture"},
            "elements": [
                {
                    "id": "m1",
                    "type": "Principle",
                    "name": "PCP.10 Eventual Consistency by Design",
                    "documentation": "Systems should handle eventual consistency.",
                    "source_ref": "PCP.10",
                },
                {
                    "id": "b1",
                    "type": "BusinessProcess",
                    "name": "Data Synchronization",
                    "documentation": "Process for syncing data across systems.",
                },
            ],
            "relationships": [{
                "type": "Association",
                "source": "m1",
                "target": "b1",
            }],
        }, sort_keys=False)

        # Enrich
        enriched = GenerationPipeline._enrich_yaml_with_dct(yaml_input, metadata)

        # Convert to XML
        xml_str, info = yaml_to_archimate_xml(enriched)

        # Parse and verify
        ns = "http://www.opengroup.org/xsd/archimate/3.0/"
        root = ET.fromstring(xml_str)

        # Check propertyDefinitions exist
        prop_defs = root.find(f"{{{ns}}}propertyDefinitions")
        assert prop_defs is not None
        def_names = set()
        for pd in prop_defs:
            name_el = pd.find(f"{{{ns}}}name")
            if name_el is not None and name_el.text:
                def_names.add(name_el.text)
        assert "dct:identifier" in def_names
        assert "dct:title" in def_names
        assert "dct:creator" in def_names

        # Check element properties
        elements = root.find(f"{{{ns}}}elements")
        principle = None
        for elem in elements:
            name_el = elem.find(f"{{{ns}}}name")
            if name_el is not None and "Eventual" in (name_el.text or ""):
                principle = elem
                break
        assert principle is not None

        props = principle.find(f"{{{ns}}}properties")
        assert props is not None
        prop_values = {}
        for prop in props:
            ref = prop.get("propertyDefinitionRef")
            val = prop.find(f"{{{ns}}}value")
            if ref and val is not None:
                prop_values[ref] = val.text

        # Verify dct values in XML
        assert any("urn:uuid:78c31f45" in v for v in prop_values.values())

        # Verify the non-KB element has no dct properties
        biz_process = None
        for elem in elements:
            name_el = elem.find(f"{{{ns}}}name")
            if name_el is not None and "Synchronization" in (name_el.text or ""):
                biz_process = elem
                break
        assert biz_process is not None
        bp_props = biz_process.find(f"{{{ns}}}properties")
        assert bp_props is None  # no properties on non-KB element
