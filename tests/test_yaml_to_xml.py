"""Tests for the ArchiMate YAML ↔ XML converter."""

import xml.etree.ElementTree as ET

import pytest
import yaml

from src.aion.tools.yaml_to_xml import apply_yaml_diff, xml_to_yaml, yaml_to_archimate_xml

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
