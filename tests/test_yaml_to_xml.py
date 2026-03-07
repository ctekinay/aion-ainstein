"""Tests for the ArchiMate YAML ↔ XML converter."""

import xml.etree.ElementTree as ET

import pytest
import yaml

from src.aion.tools.yaml_to_xml import (
    _prop_def_id,
    _validate_properties,
    apply_yaml_diff,
    xml_to_yaml,
    yaml_to_archimate_xml,
)

NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
def TAG(t): return f"{{{NS}}}{t}"  # noqa: N802


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

    def test_layout_positions(self):
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

    def test_sugiyama_layer_ordering(self):
        """Motivation elements should appear above Application elements (lower Y)."""
        yaml_str = """\
model:
  name: "Layer Test"
elements:
  - id: m1
    type: Goal
    name: "A Goal"
  - id: a1
    type: ApplicationComponent
    name: "An App"
  - id: t1
    type: Node
    name: "A Server"
relationships:
  - type: Realization
    source: a1
    target: m1
  - type: Serving
    source: t1
    target: a1
"""
        xml_str, _ = yaml_to_archimate_xml(yaml_str)
        root = ET.fromstring(xml_str)
        view = root.find(TAG("views")).find(TAG("diagrams")).findall(TAG("view"))[0]

        # Build elementRef → y mapping
        ref_to_y = {}
        for node in view.findall(TAG("node")):
            ref_to_y[node.get("elementRef")] = int(node.get("y"))

        assert ref_to_y["id-m1"] < ref_to_y["id-a1"], \
            "Motivation element should have lower Y than Application"
        assert ref_to_y["id-a1"] < ref_to_y["id-t1"], \
            "Application element should have lower Y than Technology"

    def test_sugiyama_no_overlapping_nodes(self):
        """No two nodes should occupy the same bounding box."""
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        root = ET.fromstring(xml_str)
        view = root.find(TAG("views")).find(TAG("diagrams")).findall(TAG("view"))[0]

        boxes = []
        for node in view.findall(TAG("node")):
            x = int(node.get("x"))
            y = int(node.get("y"))
            w = int(node.get("w"))
            h = int(node.get("h"))
            boxes.append((x, y, x + w, y + h))

        for i, (x1, y1, x2, y2) in enumerate(boxes):
            for j, (ax1, ay1, ax2, ay2) in enumerate(boxes):
                if i >= j:
                    continue
                # Check no overlap: one box must be entirely left, right, above, or below
                overlap = not (x2 <= ax1 or ax2 <= x1 or y2 <= ay1 or ay2 <= y1)
                assert not overlap, (
                    f"Nodes {i} and {j} overlap: "
                    f"({x1},{y1},{x2},{y2}) vs ({ax1},{ay1},{ax2},{ay2})"
                )

    def test_sugiyama_wide_element_name(self):
        """Elements with long names should get wider bounding boxes."""
        yaml_str = """\
model:
  name: "Width Test"
elements:
  - id: s1
    type: ApplicationComponent
    name: "Short"
  - id: l1
    type: ApplicationComponent
    name: "This Is A Very Long Element Name"
relationships: []
"""
        xml_str, _ = yaml_to_archimate_xml(yaml_str)
        root = ET.fromstring(xml_str)
        view = root.find(TAG("views")).find(TAG("diagrams")).findall(TAG("view"))[0]

        widths = {}
        for node in view.findall(TAG("node")):
            widths[node.get("elementRef")] = int(node.get("w"))

        assert widths["id-l1"] > widths["id-s1"], \
            "Long-named element should be wider"

    def test_junction_elements_through_pipeline(self):
        """AndJunction and OrJunction flow through YAML→XML→view→validation."""
        from src.aion.tools.archimate import validate_archimate

        yaml_str = """\
model:
  name: "Junction Test"
elements:
  - id: bp1
    type: BusinessProcess
    name: "Check Order"
  - id: bp2
    type: BusinessProcess
    name: "Ship Order"
  - id: bp3
    type: BusinessProcess
    name: "Cancel Order"
  - id: j1
    type: AndJunction
    name: "Split"
  - id: j2
    type: OrJunction
    name: "Merge"
relationships:
  - type: Triggering
    source: bp1
    target: j1
  - type: Triggering
    source: j1
    target: bp2
  - type: Triggering
    source: j1
    target: bp3
  - type: Triggering
    source: bp2
    target: j2
  - type: Triggering
    source: bp3
    target: j2
"""
        xml_str, info = yaml_to_archimate_xml(yaml_str)
        assert info["element_count"] == 5
        assert info["relationship_count"] == 5

        # Junction elements appear in XML
        root = ET.fromstring(xml_str)
        elements = root.find(TAG("elements"))
        types = {e.get(f"{{{XSI}}}type") for e in elements.findall(TAG("element"))}
        assert "AndJunction" in types
        assert "OrJunction" in types

        # All elements have view nodes
        view = root.find(TAG("views")).find(TAG("diagrams")).findall(TAG("view"))[0]
        node_erefs = {n.get("elementRef") for n in view.findall(TAG("node"))}
        assert "id-j1" in node_erefs
        assert "id-j2" in node_erefs

        # Validates without errors
        result = validate_archimate(xml_str)
        assert result["valid"], f"Validation errors: {result['errors']}"


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

    def test_invalid_relationship_pattern_warns(self, caplog):
        """Invalid source→target pair logs a warning but does not raise."""
        yaml_str = """\
model:
  name: "Test"
elements:
  - id: a1
    type: ApplicationComponent
    name: "Component"
  - id: m1
    type: Goal
    name: "A Goal"
relationships:
  - type: Triggering
    source: a1
    target: m1
"""
        import logging
        with caplog.at_level(logging.WARNING, logger="src.aion.tools.yaml_to_xml"):
            xml_str, info = yaml_to_archimate_xml(yaml_str)
        assert info["relationship_count"] == 1
        assert any("may not be a valid" in msg for msg in caplog.messages)

    def test_node_assignment_to_app_component_no_warning(self, caplog):
        """Node → ApplicationComponent (Assignment) is valid hosting."""
        yaml_str = """\
model:
  name: "Test"
elements:
  - id: t1
    type: Node
    name: "Server"
  - id: a1
    type: ApplicationComponent
    name: "Backend"
relationships:
  - type: Assignment
    source: t1
    target: a1
"""
        import logging
        with caplog.at_level(logging.WARNING, logger="src.aion.tools.yaml_to_xml"):
            xml_str, info = yaml_to_archimate_xml(yaml_str)
        assert info["relationship_count"] == 1
        assert not any("may not be a valid" in msg for msg in caplog.messages)

    def test_system_software_access_to_data_object_no_warning(self, caplog):
        """SystemSoftware → DataObject (Access) is valid cross-layer access."""
        yaml_str = """\
model:
  name: "Test"
elements:
  - id: t1
    type: SystemSoftware
    name: "DBMS"
  - id: a1
    type: DataObject
    name: "Customer Data"
relationships:
  - type: Access
    source: t1
    target: a1
"""
        import logging
        with caplog.at_level(logging.WARNING, logger="src.aion.tools.yaml_to_xml"):
            xml_str, info = yaml_to_archimate_xml(yaml_str)
        assert info["relationship_count"] == 1
        assert not any("may not be a valid" in msg for msg in caplog.messages)

    def test_capability_realization_to_business_service_no_warning(self, caplog):
        """Capability → BusinessService (Realization) is valid strategy→business."""
        yaml_str = """\
model:
  name: "Test"
elements:
  - id: s1
    type: Capability
    name: "API Management"
  - id: b1
    type: BusinessService
    name: "Customer Portal"
relationships:
  - type: Realization
    source: s1
    target: b1
"""
        import logging
        with caplog.at_level(logging.WARNING, logger="src.aion.tools.yaml_to_xml"):
            xml_str, info = yaml_to_archimate_xml(yaml_str)
        assert info["relationship_count"] == 1
        assert not any("may not be a valid" in msg for msg in caplog.messages)


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


# ---------------------------------------------------------------------------
# Diff-based refinement: apply_yaml_diff
# ---------------------------------------------------------------------------

class TestApplyYamlDiff:
    """Tests for the diff-based merge engine."""

    def test_add_elements_and_relationships(self):
        diff = """\
refinement:
  add:
    elements:
      - id: t2
        type: Node
        name: "API Gateway"
    relationships:
      - type: Serving
        source: t2
        target: a1
"""
        merged, summary = apply_yaml_diff(VALID_YAML, diff)
        data = yaml.safe_load(merged)
        assert len(data["elements"]) == 5
        assert any(e["id"] == "t2" for e in data["elements"])
        # Relationship count: 3 original + 1 new
        assert len(data["relationships"]) == 4
        assert summary["added_elements"] == 1
        assert summary["added_relationships"] == 1
        assert summary["modified"] == 0
        assert summary["removed_elements"] == 0

    def test_modify_element_name(self):
        diff = """\
refinement:
  modify:
    a1:
      name: "Renamed Order Service"
"""
        merged, summary = apply_yaml_diff(VALID_YAML, diff)
        data = yaml.safe_load(merged)
        a1 = next(e for e in data["elements"] if e["id"] == "a1")
        assert a1["name"] == "Renamed Order Service"
        # Type should be unchanged
        assert a1["type"] == "ApplicationComponent"
        assert summary["modified"] == 1

    def test_modify_element_documentation(self):
        diff = """\
refinement:
  modify:
    b1:
      documentation: "Updated process description"
"""
        merged, summary = apply_yaml_diff(VALID_YAML, diff)
        data = yaml.safe_load(merged)
        b1 = next(e for e in data["elements"] if e["id"] == "b1")
        assert b1.get("documentation") == "Updated process description"
        assert summary["modified"] == 1

    def test_modify_model_metadata(self):
        diff = """\
refinement:
  modify:
    model:
      name: "Updated Model Name"
      documentation: "New description"
"""
        merged, summary = apply_yaml_diff(VALID_YAML, diff)
        data = yaml.safe_load(merged)
        assert data["model"]["name"] == "Updated Model Name"
        assert data["model"]["documentation"] == "New description"
        assert summary["modified"] == 1

    def test_remove_element_cascades_relationships(self):
        """Removing a1 should cascade-remove relationships where a1 is source or target."""
        diff = """\
refinement:
  remove:
    elements: [a1]
"""
        merged, summary = apply_yaml_diff(VALID_YAML, diff)
        data = yaml.safe_load(merged)
        # a1 removed → 3 elements left
        assert len(data["elements"]) == 3
        assert not any(e["id"] == "a1" for e in data["elements"])
        # a1 was source in Serving:a1→b1 and Composition:a1→a2,
        # and target in Serving:t1→a1 — all 3 should be removed
        assert len(data["relationships"]) == 0
        assert summary["removed_elements"] == 1
        assert summary["removed_relationships"] == 3
        assert len(summary["cascade_notes"]) == 3

    def test_cascade_note_format(self):
        diff = """\
refinement:
  remove:
    elements: [a2]
"""
        _, summary = apply_yaml_diff(VALID_YAML, diff)
        # a2 is target in Composition:a1→a2 — one cascaded removal
        assert summary["removed_relationships"] == 1
        note = summary["cascade_notes"][0]
        assert "Composition" in note
        assert "a1" in note
        assert "a2" in note

    def test_invalid_modify_nonexistent_id(self):
        diff = """\
refinement:
  modify:
    nonexistent:
      name: "Ghost"
"""
        with pytest.raises(ValueError, match="not found"):
            apply_yaml_diff(VALID_YAML, diff)

    def test_invalid_add_duplicate_id(self):
        diff = """\
refinement:
  add:
    elements:
      - id: a1
        type: ApplicationComponent
        name: "Duplicate"
"""
        with pytest.raises(ValueError, match="already exists"):
            apply_yaml_diff(VALID_YAML, diff)

    def test_invalid_add_bad_type(self):
        diff = """\
refinement:
  add:
    elements:
      - id: x1
        type: FakeType
        name: "Bad"
"""
        with pytest.raises(ValueError, match="invalid type"):
            apply_yaml_diff(VALID_YAML, diff)

    def test_invalid_modify_forbidden_field(self):
        diff = """\
refinement:
  modify:
    a1:
      type: BusinessProcess
"""
        with pytest.raises(ValueError, match="cannot patch field 'type'"):
            apply_yaml_diff(VALID_YAML, diff)

    def test_invalid_missing_refinement_key(self):
        diff = """\
add:
  elements:
    - id: x1
      type: Node
      name: "No refinement wrapper"
"""
        with pytest.raises(ValueError, match="refinement"):
            apply_yaml_diff(VALID_YAML, diff)

    def test_mixed_valid_invalid_is_all_or_nothing(self):
        """3 valid adds + 1 invalid modify → entire diff rejected."""
        diff = """\
refinement:
  add:
    elements:
      - id: x1
        type: Node
        name: "Good 1"
      - id: x2
        type: Node
        name: "Good 2"
      - id: x3
        type: Node
        name: "Good 3"
  modify:
    nonexistent:
      name: "Bad"
"""
        with pytest.raises(ValueError, match="not found"):
            apply_yaml_diff(VALID_YAML, diff)
        # Base model should be unchanged (all-or-nothing verified by
        # the fact that ValueError was raised before serialization)

    def test_empty_sections_work(self):
        """Diff with only add (no modify/remove) should succeed."""
        diff = """\
refinement:
  add:
    elements:
      - id: n1
        type: Node
        name: "New Node"
"""
        merged, summary = apply_yaml_diff(VALID_YAML, diff)
        data = yaml.safe_load(merged)
        assert len(data["elements"]) == 5
        assert summary["added_elements"] == 1
        assert summary["modified"] == 0
        assert summary["removed_elements"] == 0

    def test_id_normalization_strips_prefix(self):
        """Diff with id- prefix should work (stripped automatically)."""
        diff = """\
refinement:
  add:
    elements:
      - id: id-n1
        type: Node
        name: "Prefixed ID"
    relationships:
      - type: Serving
        source: id-n1
        target: id-a1
"""
        merged, summary = apply_yaml_diff(VALID_YAML, diff)
        data = yaml.safe_load(merged)
        assert any(e["id"] == "n1" for e in data["elements"])
        assert summary["added_elements"] == 1
        assert summary["added_relationships"] == 1

    def test_roundtrip_after_merge(self):
        """Merged YAML → _parse_and_validate → yaml_to_archimate_xml → validate."""
        from src.aion.tools.archimate import validate_archimate

        diff = """\
refinement:
  add:
    elements:
      - id: t2
        type: Node
        name: "Load Balancer"
    relationships:
      - type: Serving
        source: t2
        target: a1
  modify:
    b1:
      name: "Updated Order Processing"
"""
        merged, _ = apply_yaml_diff(VALID_YAML, diff)
        xml_str, info = yaml_to_archimate_xml(merged)
        assert info["element_count"] == 5
        assert info["relationship_count"] == 4
        result = validate_archimate(xml_str)
        assert result["valid"], f"Validation errors: {result.get('errors', [])}"

    def test_remove_nonexistent_warns_not_fails(self):
        """Removing a nonexistent element should warn, not reject the diff."""
        diff = """\
refinement:
  remove:
    elements: [ghost_element]
"""
        merged, summary = apply_yaml_diff(VALID_YAML, diff)
        assert summary["removed_elements"] == 0
        assert len(summary["warnings"]) == 1
        assert "ghost_element" in summary["warnings"][0]
        assert "not found" in summary["warnings"][0]

    def test_remove_nonexistent_alongside_valid_ops(self):
        """Valid add + nonexistent remove: add succeeds, remove warns."""
        diff = """\
refinement:
  add:
    elements:
      - id: new1
        type: Node
        name: "New Server"
  remove:
    elements: [does_not_exist]
"""
        merged, summary = apply_yaml_diff(VALID_YAML, diff)
        assert summary["added_elements"] == 1
        assert summary["removed_elements"] == 0
        assert len(summary["warnings"]) == 1
        assert "New Server" in merged


# ---------------------------------------------------------------------------
# Viewpoint tests
# ---------------------------------------------------------------------------

MULTI_LAYER_YAML = """\
model:
  name: "Multi-Layer Architecture"

elements:
  - id: g1
    type: Goal
    name: "Reduce Manual Work"
  - id: r1
    type: Requirement
    name: "Automate Approvals"
  - id: ba1
    type: BusinessActor
    name: "Process Owner"
  - id: bp1
    type: BusinessProcess
    name: "Approval Workflow"
  - id: ac1
    type: ApplicationComponent
    name: "Workflow Engine"
  - id: as1
    type: ApplicationService
    name: "Approval Service"
  - id: n1
    type: Node
    name: "App Server"
  - id: ss1
    type: SystemSoftware
    name: "Java Runtime"

relationships:
  - type: Realization
    source: bp1
    target: r1
  - type: Serving
    source: ac1
    target: bp1
  - type: Composition
    source: ac1
    target: as1
  - type: Serving
    source: n1
    target: ac1
  - type: Assignment
    source: n1
    target: ss1
"""


class TestViewpoints:

    def test_viewpoints_constant_covers_all_layers(self):
        """Every non-Composite/Junction element type appears in at least one viewpoint."""
        from src.aion.tools.archimate import VALID_ELEMENT_TYPES
        from src.aion.tools.yaml_to_xml import VIEWPOINTS

        excluded = {"Grouping", "Location", "AndJunction", "OrJunction"}
        all_viewpoint_types: set[str] = set()
        for types in VIEWPOINTS.values():
            if types is not None:
                all_viewpoint_types |= types

        uncovered = VALID_ELEMENT_TYPES - excluded - all_viewpoint_types
        assert uncovered == set(), (
            f"Element types not covered by any viewpoint: {uncovered}"
        )

    def test_filter_for_viewpoint_application(self):
        """Application viewpoint keeps only application-layer elements."""
        from src.aion.tools.yaml_to_xml import (
            _filter_for_viewpoint,
            _parse_and_validate,
        )

        data = _parse_and_validate(MULTI_LAYER_YAML)
        filtered = _filter_for_viewpoint(data, "application")

        element_ids = {e["id"] for e in filtered["elements"]}
        assert element_ids == {"id-ac1", "id-as1"}

        # Only the intra-application relationship should survive
        assert len(filtered["relationships"]) == 1
        rel = filtered["relationships"][0]
        assert rel["type"] == "Composition"

    def test_filter_for_viewpoint_layered_returns_all(self):
        """Layered viewpoint returns all elements unfiltered."""
        from src.aion.tools.yaml_to_xml import (
            _filter_for_viewpoint,
            _parse_and_validate,
        )

        data = _parse_and_validate(MULTI_LAYER_YAML)
        filtered = _filter_for_viewpoint(data, "layered")

        assert len(filtered["elements"]) == len(data["elements"])
        assert len(filtered["relationships"]) == len(data["relationships"])

    def test_generate_viewpoint_xml_application(self):
        """Application viewpoint generates valid XML with only app elements."""
        from src.aion.tools.yaml_to_xml import generate_viewpoint_xml

        xml_str, info = generate_viewpoint_xml(MULTI_LAYER_YAML, "application")
        assert info["viewpoint"] == "application"
        assert info["element_count"] == 2

        root = ET.fromstring(xml_str)
        # Fragment has <view> as direct child of root (for merge compat)
        view = root.find(TAG("view"))
        assert view is not None

        nodes = view.findall(TAG("node"))
        assert len(nodes) == 2
        refs = {n.get("elementRef") for n in nodes}
        assert refs == {"id-ac1", "id-as1"}

        name_el = view.find(TAG("name"))
        assert "Application" in name_el.text

    def test_generate_viewpoint_xml_unknown_raises(self):
        """Unknown viewpoint raises ValueError."""
        from src.aion.tools.yaml_to_xml import generate_viewpoint_xml

        with pytest.raises(ValueError, match="Unknown viewpoint"):
            generate_viewpoint_xml(MULTI_LAYER_YAML, "nonexistent")

    def test_generate_viewpoint_xml_too_few_elements_raises(self):
        """Viewpoint yielding <2 elements raises ValueError."""
        from src.aion.tools.yaml_to_xml import generate_viewpoint_xml

        # MULTI_LAYER_YAML has no Physical elements
        with pytest.raises(ValueError, match="elements"):
            generate_viewpoint_xml(MULTI_LAYER_YAML, "physical")

    def test_generate_viewpoint_merge_roundtrip(self):
        """Full workflow: generate model → viewpoint fragment → merge."""
        from src.aion.tools.archimate import merge_archimate_view, validate_archimate
        from src.aion.tools.yaml_to_xml import generate_viewpoint_xml

        # Generate full model with overview
        model_xml, model_info = yaml_to_archimate_xml(MULTI_LAYER_YAML)

        # Generate application viewpoint fragment
        frag_xml, frag_info = generate_viewpoint_xml(MULTI_LAYER_YAML, "application")

        # Merge
        result = merge_archimate_view(model_xml, frag_xml)
        assert result["success"] is True
        assert result["views_added"] == 1

        # Validate merged XML structure
        merged_root = ET.fromstring(result["merged_xml"])
        views = merged_root.find(TAG("views"))
        diagrams = views.find(TAG("diagrams"))
        all_views = diagrams.findall(TAG("view"))
        assert len(all_views) == 2

        # Overview has all 8 elements, application has 2
        overview_nodes = all_views[0].findall(TAG("node"))
        app_nodes = all_views[1].findall(TAG("node"))
        assert len(overview_nodes) == 8
        assert len(app_nodes) == 2

        # View identifiers are distinct
        ids = {v.get("identifier") for v in all_views}
        assert len(ids) == 2

        # Merged model is valid XML
        val = validate_archimate(result["merged_xml"])
        assert val["valid"], f"Validation errors: {val.get('errors', [])}"


# ---------------------------------------------------------------------------
# Property support tests
# ---------------------------------------------------------------------------

YAML_WITH_PROPS = """\
model:
  name: "Property Test Model"
  documentation: "Model with Dublin Core properties"

elements:
  - id: m1
    type: Principle
    name: "PCP.10 Eventual Consistency"
    documentation: "Eventual consistency for distributed systems."
    properties:
      "dct:identifier": "urn:uuid:abc123"
      "dct:language": "en"
      "dct:type": "archi:Principle"
  - id: m2
    type: Principle
    name: "PCP.11 API First"
    documentation: "All services expose APIs."

relationships:
  - type: Association
    source: m1
    target: m2
    name: "related"
    properties:
      "dct:source": "registry-index.md"
"""


class TestPropertyHelpers:
    """Tests for _validate_properties() and _prop_def_id()."""

    def test_validate_normal_dict(self):
        result = _validate_properties({"dct:lang": "en", "dct:type": "Principle"})
        assert result == {"dct:lang": "en", "dct:type": "Principle"}

    def test_validate_empty_dict(self):
        assert _validate_properties({}) == {}

    def test_validate_none(self):
        assert _validate_properties(None) == {}

    def test_validate_non_dict(self):
        assert _validate_properties("not a dict") == {}
        assert _validate_properties(42) == {}
        assert _validate_properties([]) == {}

    def test_validate_strips_whitespace(self):
        result = _validate_properties({"  dct:lang  ": "  en  "})
        assert result == {"dct:lang": "en"}

    def test_validate_skips_empty_keys(self):
        result = _validate_properties({"": "value", "  ": "value2", "ok": "v"})
        assert result == {"ok": "v"}

    def test_validate_coerces_to_string(self):
        result = _validate_properties({"count": 42, "flag": True})
        assert result == {"count": "42", "flag": "True"}

    def test_prop_def_id_dct_colon(self):
        assert _prop_def_id("dct:identifier") == "propdef-dct-identifier"

    def test_prop_def_id_dct_language(self):
        assert _prop_def_id("dct:language") == "propdef-dct-language"

    def test_prop_def_id_archi_prefix(self):
        assert _prop_def_id("archi:Principle") == "propdef-archi-principle"

    def test_prop_def_id_simple(self):
        assert _prop_def_id("status") == "propdef-status"

    def test_prop_def_id_special_chars(self):
        assert _prop_def_id("my.prop@v2") == "propdef-my-prop-v2"


class TestPropertyRoundTrip:
    """End-to-end property round-trip: YAML → XML → YAML → XML."""

    def test_yaml_to_xml_has_property_definitions(self):
        xml_str, info = yaml_to_archimate_xml(YAML_WITH_PROPS)
        root = ET.fromstring(xml_str)
        pdefs = root.find(TAG("propertyDefinitions"))
        assert pdefs is not None, "Missing <propertyDefinitions>"
        pdef_names = {
            pdef.find(TAG("name")).text
            for pdef in pdefs.findall(TAG("propertyDefinition"))
        }
        assert "dct:identifier" in pdef_names
        assert "dct:language" in pdef_names
        assert "dct:type" in pdef_names
        assert "dct:source" in pdef_names

    def test_yaml_to_xml_has_element_properties(self):
        xml_str, _ = yaml_to_archimate_xml(YAML_WITH_PROPS)
        root = ET.fromstring(xml_str)
        elements = root.find(TAG("elements"))
        m1 = None
        for el in elements.findall(TAG("element")):
            if el.get("identifier") == "id-m1":
                m1 = el
                break
        assert m1 is not None
        # Properties are wrapped in <properties> container per schema
        props_container = m1.find(TAG("properties"))
        assert props_container is not None
        props = props_container.findall(TAG("property"))
        assert len(props) == 3
        # Check one property value
        values = {}
        for p in props:
            ref = p.get("propertyDefinitionRef")
            val = p.find(TAG("value")).text
            values[ref] = val
        assert values.get("propdef-dct-language") == "en"

    def test_yaml_to_xml_has_relationship_properties(self):
        xml_str, _ = yaml_to_archimate_xml(YAML_WITH_PROPS)
        root = ET.fromstring(xml_str)
        rels = root.find(TAG("relationships"))
        rel = rels.findall(TAG("relationship"))[0]
        props_container = rel.find(TAG("properties"))
        assert props_container is not None
        props = props_container.findall(TAG("property"))
        assert len(props) == 1
        assert props[0].find(TAG("value")).text == "registry-index.md"

    def test_element_without_properties_has_none(self):
        xml_str, _ = yaml_to_archimate_xml(YAML_WITH_PROPS)
        root = ET.fromstring(xml_str)
        elements = root.find(TAG("elements"))
        m2 = None
        for el in elements.findall(TAG("element")):
            if el.get("identifier") == "id-m2":
                m2 = el
                break
        assert m2 is not None
        assert m2.find(TAG("properties")) is None

    def test_full_roundtrip_preserves_properties(self):
        """YAML → XML → YAML → XML: properties survive the full cycle."""
        xml1, _ = yaml_to_archimate_xml(YAML_WITH_PROPS)
        yaml_mid = xml_to_yaml(xml1)

        # YAML should contain property keys
        assert "dct:identifier" in yaml_mid
        assert "dct:language" in yaml_mid
        assert "dct:source" in yaml_mid

        # Second pass: YAML → XML again
        xml2, _ = yaml_to_archimate_xml(yaml_mid)
        root2 = ET.fromstring(xml2)

        # Check properties survived
        pdefs = root2.find(TAG("propertyDefinitions"))
        assert pdefs is not None
        pdef_count = len(pdefs.findall(TAG("propertyDefinition")))
        assert pdef_count == 4  # dct:identifier, dct:language, dct:type, dct:source

        # Element properties survived
        elements = root2.find(TAG("elements"))
        m1 = None
        for el in elements.findall(TAG("element")):
            if el.get("identifier") == "id-m1":
                m1 = el
                break
        assert m1 is not None
        m1_props = m1.find(TAG("properties"))
        assert m1_props is not None
        assert len(m1_props.findall(TAG("property"))) == 3

    def test_no_properties_no_property_definitions(self):
        """Models without properties should not get a <propertyDefinitions> block."""
        xml_str, _ = yaml_to_archimate_xml(VALID_YAML)
        root = ET.fromstring(xml_str)
        assert root.find(TAG("propertyDefinitions")) is None


class TestPropertyDiffMerge:
    """Tests for property support in apply_yaml_diff()."""

    def test_modify_element_add_properties(self):
        """Add properties to an existing element via modify."""
        diff = """\
refinement:
  modify:
    b1:
      properties:
        "dct:language": "en"
        "dct:type": "archi:BusinessProcess"
"""
        merged, summary = apply_yaml_diff(VALID_YAML, diff)
        data = yaml.safe_load(merged)
        b1 = next(e for e in data["elements"] if e["id"] == "b1")
        assert b1["properties"]["dct:language"] == "en"
        assert b1["properties"]["dct:type"] == "archi:BusinessProcess"
        assert summary["modified"] == 1

    def test_modify_element_merge_properties(self):
        """Properties merge is additive — existing properties preserved."""
        diff = """\
refinement:
  modify:
    m1:
      properties:
        "dct:creator": "ESA Team"
"""
        merged, summary = apply_yaml_diff(YAML_WITH_PROPS, diff)
        data = yaml.safe_load(merged)
        m1 = next(e for e in data["elements"] if e["id"] == "m1")
        # Original properties preserved
        assert m1["properties"]["dct:identifier"] == "urn:uuid:abc123"
        assert m1["properties"]["dct:language"] == "en"
        # New property added
        assert m1["properties"]["dct:creator"] == "ESA Team"

    def test_modify_element_update_existing_property(self):
        """Updating an existing property value."""
        diff = """\
refinement:
  modify:
    m1:
      properties:
        "dct:language": "nl"
"""
        merged, _ = apply_yaml_diff(YAML_WITH_PROPS, diff)
        data = yaml.safe_load(merged)
        m1 = next(e for e in data["elements"] if e["id"] == "m1")
        assert m1["properties"]["dct:language"] == "nl"
        # Other properties unchanged
        assert m1["properties"]["dct:identifier"] == "urn:uuid:abc123"

    def test_modify_relationship_add_properties(self):
        """Add properties to an existing relationship via rel-source-target key."""
        diff = """\
refinement:
  modify:
    rel-m1-m2:
      properties:
        "dct:creator": "AInstein"
"""
        merged, summary = apply_yaml_diff(YAML_WITH_PROPS, diff)
        data = yaml.safe_load(merged)
        rel = data["relationships"][0]
        # Original property preserved
        assert rel["properties"]["dct:source"] == "registry-index.md"
        # New property added
        assert rel["properties"]["dct:creator"] == "AInstein"
        assert summary["modified"] == 1

    def test_modify_relationship_name(self):
        """Modify relationship name via rel-source-target key."""
        diff = """\
refinement:
  modify:
    rel-m1-m2:
      name: "strongly related"
"""
        merged, summary = apply_yaml_diff(YAML_WITH_PROPS, diff)
        data = yaml.safe_load(merged)
        rel = data["relationships"][0]
        assert rel["name"] == "strongly related"
        assert summary["modified"] == 1

    def test_modify_nonexistent_relationship_fails(self):
        diff = """\
refinement:
  modify:
    rel-m1-m99:
      properties:
        "dct:creator": "test"
"""
        with pytest.raises(ValueError, match="relationship not found"):
            apply_yaml_diff(YAML_WITH_PROPS, diff)

    def test_modify_relationship_invalid_field_fails(self):
        diff = """\
refinement:
  modify:
    rel-m1-m2:
      type: "Serving"
"""
        with pytest.raises(ValueError, match="cannot patch field"):
            apply_yaml_diff(YAML_WITH_PROPS, diff)

    def test_add_element_with_properties(self):
        """Adding a new element with properties in a diff."""
        diff = """\
refinement:
  add:
    elements:
      - id: m3
        type: Principle
        name: "PCP.12 New Principle"
        properties:
          "dct:language": "en"
          "dct:identifier": "urn:uuid:new123"
"""
        merged, summary = apply_yaml_diff(YAML_WITH_PROPS, diff)
        data = yaml.safe_load(merged)
        m3 = next(e for e in data["elements"] if e["id"] == "m3")
        assert m3["properties"]["dct:language"] == "en"
        assert m3["properties"]["dct:identifier"] == "urn:uuid:new123"
        assert summary["added_elements"] == 1

    def test_add_relationship_with_properties(self):
        """Adding a new relationship with properties in a diff."""
        diff = """\
refinement:
  add:
    relationships:
      - type: Influence
        source: m1
        target: m2
        properties:
          "dct:source": "architecture-review.md"
"""
        merged, summary = apply_yaml_diff(YAML_WITH_PROPS, diff)
        data = yaml.safe_load(merged)
        # Find the new relationship (Influence, not the original Association)
        new_rel = next(r for r in data["relationships"] if r["type"] == "Influence")
        assert new_rel["properties"]["dct:source"] == "architecture-review.md"
        assert summary["added_relationships"] == 1

    def test_diff_with_properties_roundtrips_to_valid_xml(self):
        """After a property-adding diff, the merged YAML produces valid XML."""
        diff = """\
refinement:
  modify:
    m1:
      properties:
        "dct:creator": "ESA Team"
    m2:
      properties:
        "dct:language": "en"
    rel-m1-m2:
      properties:
        "dct:creator": "AInstein"
"""
        merged, _ = apply_yaml_diff(YAML_WITH_PROPS, diff)
        xml_str, info = yaml_to_archimate_xml(merged)
        root = ET.fromstring(xml_str)

        # propertyDefinitions should exist
        pdefs = root.find(TAG("propertyDefinitions"))
        assert pdefs is not None

        # All property keys should be defined
        pdef_names = {
            pdef.find(TAG("name")).text
            for pdef in pdefs.findall(TAG("propertyDefinition"))
        }
        assert "dct:creator" in pdef_names
        assert "dct:identifier" in pdef_names
