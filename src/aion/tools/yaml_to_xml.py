"""ArchiMate YAML ↔ XML converter.

Forward (yaml_to_archimate_xml): Converts a lightweight YAML
representation (elements + relationships only) into a complete
ArchiMate 3.2 Open Exchange XML document with auto-generated grid views.

Reverse (xml_to_yaml): Converts ArchiMate Open Exchange XML back to
compact YAML for LLM inspection and reasoning (~90% token reduction).
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


# ---------------------------------------------------------------------------
# Reverse: XML → YAML
# ---------------------------------------------------------------------------

_TAG = lambda t: f"{{{NS}}}{t}"


def xml_to_yaml(xml_str: str) -> str:
    """Convert ArchiMate Open Exchange XML to compact YAML.

    Extracts elements and relationships, discards views (they are
    regenerated deterministically by yaml_to_archimate_xml). Produces
    the same YAML format that yaml_to_archimate_xml accepts as input.

    Args:
        xml_str: Valid ArchiMate 3.2 Open Exchange XML string.

    Returns:
        YAML string with model, elements, and relationships.

    Raises:
        ValueError: If XML cannot be parsed or has no elements.
    """
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML: {e}") from e

    # Model metadata
    name_el = root.find(_TAG("name"))
    model_name = name_el.text.strip() if name_el is not None and name_el.text else "Untitled"
    doc_el = root.find(_TAG("documentation"))
    model_doc = doc_el.text.strip() if doc_el is not None and doc_el.text else ""

    # Elements
    elements_node = root.find(_TAG("elements"))
    if elements_node is None:
        raise ValueError("No <elements> section found in XML")

    elements = []
    element_ids: set[str] = set()
    for elem in elements_node.findall(_TAG("element")):
        eid = elem.get("identifier", "")
        etype = elem.get(f"{{{XSI}}}type", "")
        if not eid or etype not in VALID_ELEMENT_TYPES:
            continue  # Skip junctions and unknown types
        en = elem.find(_TAG("name"))
        ename = en.text.strip() if en is not None and en.text else ""
        if not ename:
            continue
        ed = elem.find(_TAG("documentation"))
        edoc = ed.text.strip() if ed is not None and ed.text else ""

        short_id = eid.removeprefix("id-")
        element_ids.add(eid)
        entry: dict = {"id": short_id, "type": etype, "name": ename}
        if edoc:
            entry["documentation"] = edoc
        elements.append(entry)

    if not elements:
        raise ValueError("No valid elements found in XML")

    # Relationships
    rels_node = root.find(_TAG("relationships"))
    relationships: list[dict] = []
    if rels_node is not None:
        for rel in rels_node.findall(_TAG("relationship")):
            rtype = rel.get(f"{{{XSI}}}type", "")
            source = rel.get("source", "")
            target = rel.get("target", "")
            if not rtype or rtype not in VALID_RELATIONSHIP_TYPES:
                continue
            if source not in element_ids or target not in element_ids:
                continue  # Skip relationships referencing missing elements
            rn = rel.find(_TAG("name"))
            rname = rn.text.strip() if rn is not None and rn.text else ""

            entry = {
                "type": rtype,
                "source": source.removeprefix("id-"),
                "target": target.removeprefix("id-"),
            }
            if rname:
                entry["name"] = rname
            relationships.append(entry)

    # Build YAML string with layer grouping for readability
    lines = ["model:"]
    lines.append(f'  name: "{_yaml_escape(model_name)}"')
    if model_doc:
        lines.append(f'  documentation: "{_yaml_escape(model_doc)}"')
    lines.append("")
    lines.append("elements:")

    # Group by layer for readability
    layer_groups: dict[str, list[dict]] = defaultdict(list)
    for elem in elements:
        layer = LAYER_MAP.get(elem["type"], "Composite")
        layer_groups[layer].append(elem)

    for layer in LAYER_ORDER:
        group = layer_groups.get(layer)
        if not group:
            continue
        lines.append(f"  # {layer}")
        for elem in group:
            lines.append(f"  - id: {elem['id']}")
            lines.append(f"    type: {elem['type']}")
            lines.append(f'    name: "{_yaml_escape(elem["name"])}"')
            if elem.get("documentation"):
                lines.append(f'    documentation: "{_yaml_escape(elem["documentation"])}"')

    lines.append("")
    if relationships:
        lines.append("relationships:")
        for rel in relationships:
            lines.append(f"  - type: {rel['type']}")
            lines.append(f"    source: {rel['source']}")
            lines.append(f"    target: {rel['target']}")
            if rel.get("name"):
                lines.append(f'    name: "{_yaml_escape(rel["name"])}"')
    else:
        lines.append("relationships: []")

    result = "\n".join(lines) + "\n"
    logger.info(
        f"[xml_to_yaml] Converted: {len(elements)} elements, "
        f"{len(relationships)} relationships, {len(result)} chars"
    )
    return result


def _yaml_escape(text: str) -> str:
    """Escape characters that need quoting inside YAML double-quoted strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')
