"""YAML-to-ArchiMate XML converter.

Converts a lightweight YAML representation (elements + relationships only)
into a complete ArchiMate 3.2 Open Exchange XML document with auto-generated
grid views. The LLM produces YAML; this module handles all XML complexity
deterministically.
"""

import logging
import xml.etree.ElementTree as ET
from collections import defaultdict

import yaml

from src.aion.tools.archimate import (
    LAYER_MAP,
    LAYER_ORDER,
    NS,
    VALID_ELEMENT_TYPES,
    VALID_RELATIONSHIP_TYPES,
    XSI,
)

logger = logging.getLogger(__name__)

# Grid layout constants
NODE_W = 120
NODE_H = 55
PAD_X = 20
PAD_Y = 20
COLS = 4


def yaml_to_archimate_xml(yaml_str: str) -> tuple[str, dict]:
    """Convert YAML model definition to ArchiMate 3.2 Open Exchange XML.

    Args:
        yaml_str: YAML string with model, elements, and relationships.

    Returns:
        Tuple of (xml_string, info_dict) where info_dict contains
        element_count and relationship_count.

    Raises:
        ValueError: If YAML is invalid, missing required fields, or
            contains invalid element/relationship types.
    """
    data = _parse_and_validate(yaml_str)
    root = _build_model(data)
    _generate_view(root, data)

    ET.register_namespace("", NS)
    ET.register_namespace("xsi", XSI)
    xml_str = ET.tostring(root, encoding="unicode", xml_declaration=True)

    info = {
        "element_count": len(data["elements"]),
        "relationship_count": len(data["relationships"]),
    }
    logger.info(
        f"[yaml_to_xml] Converted: {info['element_count']} elements, "
        f"{info['relationship_count']} relationships"
    )
    return xml_str, info


# ---------------------------------------------------------------------------
# Stage 1: Parse and validate YAML
# ---------------------------------------------------------------------------

def _parse_and_validate(yaml_str: str) -> dict:
    """Parse YAML and validate all fields.

    Returns a normalized dict with model, elements, relationships.
    Element IDs are prefixed with 'id-' if not already.
    Relationship IDs are derived as 'id-rel-{source}-{target}'.
    """
    try:
        raw = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML syntax: {e}") from e

    if not isinstance(raw, dict):
        raise ValueError("YAML root must be a mapping")

    # Model metadata
    model = raw.get("model", {})
    if not isinstance(model, dict):
        raise ValueError("'model' must be a mapping with at least 'name'")
    if not model.get("name"):
        raise ValueError("'model.name' is required")

    # Elements
    elements = raw.get("elements", [])
    if not isinstance(elements, list) or not elements:
        raise ValueError("'elements' must be a non-empty list")

    element_ids = set()
    normalized_elements = []
    for i, elem in enumerate(elements):
        if not isinstance(elem, dict):
            raise ValueError(f"Element {i}: must be a mapping")
        eid = str(elem.get("id", "")).strip()
        if not eid:
            raise ValueError(f"Element {i}: 'id' is required")
        etype = str(elem.get("type", "")).strip()
        if not etype:
            raise ValueError(f"Element '{eid}': 'type' is required")
        if etype not in VALID_ELEMENT_TYPES:
            raise ValueError(
                f"Element '{eid}': invalid type '{etype}'. "
                f"Must be one of the valid ArchiMate element types."
            )
        ename = str(elem.get("name", "")).strip()
        if not ename:
            raise ValueError(f"Element '{eid}': 'name' is required")

        # Normalize ID: add 'id-' prefix if missing
        full_id = eid if eid.startswith("id-") else f"id-{eid}"
        if full_id in element_ids:
            raise ValueError(f"Duplicate element id: '{eid}'")
        element_ids.add(full_id)

        normalized_elements.append({
            "id": full_id,
            "type": etype,
            "name": ename,
            "documentation": str(elem.get("documentation", "")).strip(),
        })

    # Relationships
    relationships = raw.get("relationships", [])
    if not isinstance(relationships, list):
        raise ValueError("'relationships' must be a list")

    # Derive deterministic IDs: id-rel-{source}-{target} with -N suffix for dupes
    pair_counts: dict[str, int] = defaultdict(int)
    normalized_rels = []
    for i, rel in enumerate(relationships):
        if not isinstance(rel, dict):
            raise ValueError(f"Relationship {i}: must be a mapping")
        rtype = str(rel.get("type", "")).strip()
        if not rtype:
            raise ValueError(f"Relationship {i}: 'type' is required")
        if rtype not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"Relationship {i}: invalid type '{rtype}'. "
                f"Must be one of the valid ArchiMate relationship types."
            )
        source = str(rel.get("source", "")).strip()
        target = str(rel.get("target", "")).strip()
        if not source or not target:
            raise ValueError(f"Relationship {i}: 'source' and 'target' are required")

        # Normalize source/target IDs
        full_source = source if source.startswith("id-") else f"id-{source}"
        full_target = target if target.startswith("id-") else f"id-{target}"

        if full_source not in element_ids:
            raise ValueError(
                f"Relationship {i}: source '{source}' does not reference "
                f"a valid element id"
            )
        if full_target not in element_ids:
            raise ValueError(
                f"Relationship {i}: target '{target}' does not reference "
                f"a valid element id"
            )

        # Derive deterministic ID
        src_code = full_source.removeprefix("id-")
        tgt_code = full_target.removeprefix("id-")
        pair_key = f"{src_code}-{tgt_code}"
        pair_counts[pair_key] += 1
        count = pair_counts[pair_key]
        rid = f"id-rel-{pair_key}" if count == 1 else f"id-rel-{pair_key}-{count}"

        rname = str(rel.get("name", "")).strip()

        normalized_rels.append({
            "id": rid,
            "type": rtype,
            "source": full_source,
            "target": full_target,
            "name": rname,
        })

    return {
        "model": {
            "name": str(model["name"]).strip(),
            "documentation": str(model.get("documentation", "")).strip(),
        },
        "elements": normalized_elements,
        "relationships": normalized_rels,
    }


# ---------------------------------------------------------------------------
# Stage 2: Build XML model
# ---------------------------------------------------------------------------

_SCHEMA_LOC = (
    f"{NS} "
    "http://www.opengroup.org/xsd/archimate/3.2/archimate3_Diagram.xsd"
)


def _build_model(data: dict) -> ET.Element:
    """Build the XML <model> element with elements and relationships."""
    root = ET.Element(
        f"{{{NS}}}model",
        attrib={
            "identifier": "id-model-001",
            f"{{{XSI}}}schemaLocation": _SCHEMA_LOC,
        },
    )

    # Model name and documentation
    name_el = ET.SubElement(root, f"{{{NS}}}name")
    name_el.set("xml:lang", "en")
    name_el.text = data["model"]["name"]

    if data["model"]["documentation"]:
        doc_el = ET.SubElement(root, f"{{{NS}}}documentation")
        doc_el.set("xml:lang", "en")
        doc_el.text = data["model"]["documentation"]

    # Elements
    elements_el = ET.SubElement(root, f"{{{NS}}}elements")
    for elem in data["elements"]:
        el = ET.SubElement(elements_el, f"{{{NS}}}element")
        el.set("identifier", elem["id"])
        el.set(f"{{{XSI}}}type", elem["type"])
        n = ET.SubElement(el, f"{{{NS}}}name")
        n.set("xml:lang", "en")
        n.text = elem["name"]
        if elem["documentation"]:
            d = ET.SubElement(el, f"{{{NS}}}documentation")
            d.set("xml:lang", "en")
            d.text = elem["documentation"]

    # Relationships
    if data["relationships"]:
        rels_el = ET.SubElement(root, f"{{{NS}}}relationships")
        for rel in data["relationships"]:
            r = ET.SubElement(rels_el, f"{{{NS}}}relationship")
            r.set("identifier", rel["id"])
            r.set(f"{{{XSI}}}type", rel["type"])
            r.set("source", rel["source"])
            r.set("target", rel["target"])
            if rel["name"]:
                n = ET.SubElement(r, f"{{{NS}}}name")
                n.set("xml:lang", "en")
                n.text = rel["name"]

    return root


# ---------------------------------------------------------------------------
# Stage 3: Generate grid view
# ---------------------------------------------------------------------------

def _generate_view(root: ET.Element, data: dict) -> None:
    """Add a single overview view with grid layout grouped by layer."""
    # Group elements by layer
    layer_groups: dict[str, list[dict]] = defaultdict(list)
    for elem in data["elements"]:
        layer = LAYER_MAP.get(elem["type"], "Composite")
        layer_groups[layer].append(elem)

    # Build node map: element_id → node_id
    node_map: dict[str, str] = {}
    nodes: list[dict] = []
    y = PAD_Y

    for layer in LAYER_ORDER:
        elems = layer_groups.get(layer)
        if not elems:
            continue
        for i, elem in enumerate(elems):
            col = i % COLS
            row = i // COLS
            x = PAD_X + col * (NODE_W + PAD_X)
            ny = y + row * (NODE_H + PAD_Y)
            code = elem["id"].removeprefix("id-")
            nid = f"nv1-{code}"
            node_map[elem["id"]] = nid
            nodes.append({
                "id": nid,
                "elementRef": elem["id"],
                "x": str(x),
                "y": str(ny),
                "w": str(NODE_W),
                "h": str(NODE_H),
            })
        # Advance Y past this layer's rows
        row_count = (len(elems) + COLS - 1) // COLS
        y += row_count * (NODE_H + PAD_Y)

    # Build connections for relationships where both endpoints have nodes
    connections: list[dict] = []
    for rel in data["relationships"]:
        src_nid = node_map.get(rel["source"])
        tgt_nid = node_map.get(rel["target"])
        if src_nid and tgt_nid:
            rel_code = rel["id"].removeprefix("id-")
            connections.append({
                "id": f"cv1-{rel_code}",
                "relationshipRef": rel["id"],
                "source": src_nid,
                "target": tgt_nid,
            })

    # Assemble XML view structure
    views_el = ET.SubElement(root, f"{{{NS}}}views")
    diagrams_el = ET.SubElement(views_el, f"{{{NS}}}diagrams")
    view_el = ET.SubElement(diagrams_el, f"{{{NS}}}view")
    view_el.set("identifier", "id-v1")
    view_el.set(f"{{{XSI}}}type", "Diagram")
    vname = ET.SubElement(view_el, f"{{{NS}}}name")
    vname.set("xml:lang", "en")
    vname.text = f"{data['model']['name']} — Overview"

    for node in nodes:
        n = ET.SubElement(view_el, f"{{{NS}}}node")
        n.set("identifier", node["id"])
        n.set("elementRef", node["elementRef"])
        n.set(f"{{{XSI}}}type", "Element")
        n.set("x", node["x"])
        n.set("y", node["y"])
        n.set("w", node["w"])
        n.set("h", node["h"])

    for conn in connections:
        c = ET.SubElement(view_el, f"{{{NS}}}connection")
        c.set("identifier", conn["id"])
        c.set("relationshipRef", conn["relationshipRef"])
        c.set(f"{{{XSI}}}type", "Relationship")
        c.set("source", conn["source"])
        c.set("target", conn["target"])
