"""Tests for the ArchiMate YAML ↔ XML converter."""

import xml.etree.ElementTree as ET

import pytest
import yaml

from src.aion.tools.yaml_to_xml import xml_to_yaml, yaml_to_archimate_xml

NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
TAG = lambda t: f"{{{NS}}}{t}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_YAML = """\
model:
  name: "Test Architecture Model"
  documentation: "A test model for unit testing"

elements:
  - id: b1
    type: BusinessProcess
    name: "Order Processing"
  - id: a1
    type: ApplicationComponent
    name: "Order Service"
  - id: a2
    type: ApplicationInterface
    name: "Order API"
  - id: t1
    type: SystemSoftware
    name: "Container Runtime"

relationships:
  - type: Serving
    source: a1
    target: b1
    name: "processes orders"
  - type: Composition
    source: a1
    target: a2
  - type: Serving
    source: t1
    target: a1
    name: "hosts"
"""

ELEMENTS_ONLY_YAML = """\
model:
  name: "Elements Only"

elements:
  - id: m1
    type: Goal
    name: "Improve Efficiency"
  - id: b1
    type: BusinessProcess
    name: "Manual Review"

relationships: []
"""


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:

    def test_valid_yaml_produces_xml(self):
        xml_str, info = yaml_to_archimate_xml(VALID_YAML)
        assert info["element_count"] == 4
        assert info["relationship_count"] == 3
        assert "<?xml" in xml_str
        assert "</model>" in xml_str or "<model" in xml_str

    def test_xml_has_correct_elements(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        root = ET.fromstring(xml_str)
        elements = root.find(TAG("elements"))
        assert elements is not None
        elems = elements.findall(TAG("element"))
        assert len(elems) == 4

    def test_xml_has_correct_relationships(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        root = ET.fromstring(xml_str)
        rels = root.find(TAG("relationships"))
        assert rels is not None
        rel_list = rels.findall(TAG("relationship"))
        assert len(rel_list) == 3

    def test_element_ids_prefixed(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        root = ET.fromstring(xml_str)
        elements = root.find(TAG("elements"))
        for elem in elements.findall(TAG("element")):
            assert elem.get("identifier", "").startswith("id-")

    def test_relationship_ids_deterministic(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        root = ET.fromstring(xml_str)
        rels = root.find(TAG("relationships"))
        rel_ids = [r.get("identifier") for r in rels.findall(TAG("relationship"))]
        assert "id-rel-a1-b1" in rel_ids
        assert "id-rel-a1-a2" in rel_ids
        assert "id-rel-t1-a1" in rel_ids

    def test_elements_only_model(self):
        xml_str, info = yaml_to_archimate_xml(ELEMENTS_ONLY_YAML)
        assert info["element_count"] == 2
        assert info["relationship_count"] == 0
        root = ET.fromstring(xml_str)
        # Should still have a view with nodes
        views = root.find(TAG("views"))
        assert views is not None


# ---------------------------------------------------------------------------
# View generation
# ---------------------------------------------------------------------------

class TestViewGeneration:

    def test_all_elements_have_nodes(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        root = ET.fromstring(xml_str)
        elements = root.find(TAG("elements"))
        element_ids = {e.get("identifier") for e in elements.findall(TAG("element"))}

        views = root.find(TAG("views"))
        diagrams = views.find(TAG("diagrams"))
        view = diagrams.findall(TAG("view"))[0]
        node_erefs = {n.get("elementRef") for n in view.findall(TAG("node"))}

        assert element_ids == node_erefs, (
            f"Missing nodes for elements: {element_ids - node_erefs}"
        )

    def test_relationships_have_connections(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        root = ET.fromstring(xml_str)
        rels = root.find(TAG("relationships"))
        rel_ids = {r.get("identifier") for r in rels.findall(TAG("relationship"))}

        views = root.find(TAG("views"))
        diagrams = views.find(TAG("diagrams"))
        view = diagrams.findall(TAG("view"))[0]
        conn_rrefs = {c.get("relationshipRef") for c in view.findall(TAG("connection"))}

        assert rel_ids == conn_rrefs, (
            f"Missing connections for relationships: {rel_ids - conn_rrefs}"
        )

    def test_grid_layout_positions(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        root = ET.fromstring(xml_str)
        views = root.find(TAG("views"))
        diagrams = views.find(TAG("diagrams"))
        view = diagrams.findall(TAG("view"))[0]
        nodes = view.findall(TAG("node"))

        # All nodes should have positive coordinates
        for node in nodes:
            x = int(node.get("x", "0"))
            y = int(node.get("y", "0"))
            w = int(node.get("w", "0"))
            h = int(node.get("h", "0"))
            assert x >= 0
            assert y >= 0
            assert w > 0
            assert h > 0

    def test_connection_source_target_are_node_ids(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        root = ET.fromstring(xml_str)
        views = root.find(TAG("views"))
        diagrams = views.find(TAG("diagrams"))
        view = diagrams.findall(TAG("view"))[0]

        node_ids = {n.get("identifier") for n in view.findall(TAG("node"))}
        for conn in view.findall(TAG("connection")):
            src = conn.get("source")
            tgt = conn.get("target")
            assert src in node_ids, f"Connection source '{src}' not a node ID"
            assert tgt in node_ids, f"Connection target '{tgt}' not a node ID"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestValidationErrors:

    def test_missing_model_name(self):
        yaml_str = """\
model:
  documentation: "no name"
elements:
  - id: a1
    type: ApplicationComponent
    name: "Test"
relationships: []
"""
        with pytest.raises(ValueError, match="model.name"):
            yaml_to_archimate_xml(yaml_str)

    def test_missing_elements(self):
        yaml_str = """\
model:
  name: "Test"
elements: []
relationships: []
"""
        with pytest.raises(ValueError, match="non-empty list"):
            yaml_to_archimate_xml(yaml_str)

    def test_invalid_element_type(self):
        yaml_str = """\
model:
  name: "Test"
elements:
  - id: x1
    type: FakeElement
    name: "Bad Type"
relationships: []
"""
        with pytest.raises(ValueError, match="invalid type 'FakeElement'"):
            yaml_to_archimate_xml(yaml_str)

    def test_invalid_relationship_type(self):
        yaml_str = """\
model:
  name: "Test"
elements:
  - id: a1
    type: ApplicationComponent
    name: "Service"
  - id: b1
    type: BusinessProcess
    name: "Process"
relationships:
  - type: FakeRelation
    source: a1
    target: b1
"""
        with pytest.raises(ValueError, match="invalid type 'FakeRelation'"):
            yaml_to_archimate_xml(yaml_str)

    def test_broken_referential_integrity(self):
        yaml_str = """\
model:
  name: "Test"
elements:
  - id: a1
    type: ApplicationComponent
    name: "Service"
relationships:
  - type: Serving
    source: a1
    target: nonexistent
"""
        with pytest.raises(ValueError, match="does not reference"):
            yaml_to_archimate_xml(yaml_str)

    def test_missing_element_id(self):
        yaml_str = """\
model:
  name: "Test"
elements:
  - type: ApplicationComponent
    name: "No ID"
relationships: []
"""
        with pytest.raises(ValueError, match="'id' is required"):
            yaml_to_archimate_xml(yaml_str)

    def test_duplicate_element_id(self):
        yaml_str = """\
model:
  name: "Test"
elements:
  - id: a1
    type: ApplicationComponent
    name: "First"
  - id: a1
    type: ApplicationComponent
    name: "Duplicate"
relationships: []
"""
        with pytest.raises(ValueError, match="Duplicate element id"):
            yaml_to_archimate_xml(yaml_str)

    def test_invalid_yaml_syntax(self):
        with pytest.raises(ValueError, match="Invalid YAML"):
            yaml_to_archimate_xml("{ invalid yaml [[[")


# ---------------------------------------------------------------------------
# Duplicate source-target pairs get suffixed IDs
# ---------------------------------------------------------------------------

class TestDuplicateRelationshipIDs:

    def test_duplicate_pairs_get_suffixed_ids(self):
        yaml_str = """\
model:
  name: "Test"
elements:
  - id: a1
    type: ApplicationComponent
    name: "Service A"
  - id: a2
    type: ApplicationComponent
    name: "Service B"
relationships:
  - type: Serving
    source: a1
    target: a2
    name: "first"
  - type: Flow
    source: a1
    target: a2
    name: "second"
"""
        xml_str, _ = yaml_to_archimate_xml(yaml_str)
        root = ET.fromstring(xml_str)
        rels = root.find(TAG("relationships"))
        rel_ids = [r.get("identifier") for r in rels.findall(TAG("relationship"))]
        assert "id-rel-a1-a2" in rel_ids
        assert "id-rel-a1-a2-2" in rel_ids


# ---------------------------------------------------------------------------
# Roundtrip: YAML → XML → validate_archimate
# ---------------------------------------------------------------------------

class TestRoundtrip:

    def test_roundtrip_validates(self):
        from src.aion.tools.archimate import validate_archimate

        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        result = validate_archimate(xml_str)
        assert result["valid"], f"Validation errors: {result.get('errors', [])}"
        assert result["element_count"] == 4
        assert result["relationship_count"] == 3

    def test_elements_only_roundtrip_validates(self):
        from src.aion.tools.archimate import validate_archimate

        xml_str, _ = yaml_to_archimate_xml(ELEMENTS_ONLY_YAML)
        result = validate_archimate(xml_str)
        assert result["valid"], f"Validation errors: {result.get('errors', [])}"


# ---------------------------------------------------------------------------
# XML → YAML (reverse converter)
# ---------------------------------------------------------------------------

class TestXmlToYaml:

    def test_roundtrip_preserves_element_count(self):
        """xml_to_yaml output fed back to yaml_to_archimate_xml keeps counts."""
        xml1, info1 = yaml_to_archimate_xml(VALID_YAML)
        yaml_back = xml_to_yaml(xml1)
        xml2, info2 = yaml_to_archimate_xml(yaml_back)
        assert info1["element_count"] == info2["element_count"]
        assert info1["relationship_count"] == info2["relationship_count"]

    def test_extracts_all_elements(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        yaml_str = xml_to_yaml(xml_str)
        data = yaml.safe_load(yaml_str)
        assert len(data["elements"]) == 4

    def test_extracts_all_relationships(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        yaml_str = xml_to_yaml(xml_str)
        data = yaml.safe_load(yaml_str)
        assert len(data["relationships"]) == 3

    def test_strips_id_prefix(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        yaml_str = xml_to_yaml(xml_str)
        data = yaml.safe_load(yaml_str)
        for elem in data["elements"]:
            assert not elem["id"].startswith("id-"), (
                f"Element ID should have id- prefix stripped: {elem['id']}"
            )

    def test_relationship_source_target_stripped(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        yaml_str = xml_to_yaml(xml_str)
        data = yaml.safe_load(yaml_str)
        for rel in data["relationships"]:
            assert not rel["source"].startswith("id-")
            assert not rel["target"].startswith("id-")

    def test_relationships_have_no_id(self):
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        yaml_str = xml_to_yaml(xml_str)
        data = yaml.safe_load(yaml_str)
        for rel in data["relationships"]:
            assert "id" not in rel

    def test_omits_empty_documentation(self):
        xml_str, _ = yaml_to_archimate_xml(ELEMENTS_ONLY_YAML)
        yaml_str = xml_to_yaml(xml_str)
        data = yaml.safe_load(yaml_str)
        for elem in data["elements"]:
            if "documentation" in elem:
                assert elem["documentation"], "Empty documentation should be omitted"

    def test_handles_special_characters(self):
        """Elements with & and < in names survive the round-trip."""
        special_yaml = """\
model:
  name: "Special Chars Test"
elements:
  - id: a1
    type: ApplicationComponent
    name: "Forecast & Schedule"
    documentation: "Threshold < 30s"
relationships: []
"""
        xml_str, _ = yaml_to_archimate_xml(special_yaml)
        yaml_back = xml_to_yaml(xml_str)
        assert "Forecast & Schedule" in yaml_back
        assert "Threshold < 30s" in yaml_back

    def test_empty_relationships_produces_empty_list(self):
        xml_str, _ = yaml_to_archimate_xml(ELEMENTS_ONLY_YAML)
        yaml_str = xml_to_yaml(xml_str)
        data = yaml.safe_load(yaml_str)
        assert data["relationships"] == []

    def test_invalid_xml_raises(self):
        with pytest.raises(ValueError, match="Invalid XML"):
            xml_to_yaml("not xml at all")

    def test_no_elements_raises(self):
        minimal_xml = (
            '<?xml version="1.0"?>'
            '<model xmlns="http://www.opengroup.org/xsd/archimate/3.0/">'
            '<name xml:lang="en">Empty</name>'
            '</model>'
        )
        with pytest.raises(ValueError, match="No.*elements"):
            xml_to_yaml(minimal_xml)

    def test_roundtrip_validates(self):
        """Full roundtrip: YAML → XML → YAML → XML → validate."""
        from src.aion.tools.archimate import validate_archimate

        xml1, _ = yaml_to_archimate_xml(VALID_YAML)
        yaml_back = xml_to_yaml(xml1)
        xml2, _ = yaml_to_archimate_xml(yaml_back)
        result = validate_archimate(xml2)
        assert result["valid"], f"Roundtrip validation errors: {result.get('errors', [])}"
