"""ArchiMate YAML ↔ XML converter.

Forward (yaml_to_archimate_xml): Converts a lightweight YAML
representation (elements + relationships only) into a complete
ArchiMate 3.2 Open Exchange XML document with auto-generated views
using Sugiyama hierarchical layout (layer grouping, barycenter
crossing reduction, row wrapping).

Reverse (xml_to_yaml): Converts ArchiMate Open Exchange XML back to
compact YAML for LLM inspection and reasoning (~90% token reduction).
"""

import logging
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

import yaml

from aion.tools.archimate import (
    ALLOWED_PATTERNS,
    APP_ACTIVE,
    APP_BEHAVIOR,
    APP_PASSIVE,
    BIZ_ACTIVE,
    BIZ_BEHAVIOR,
    BIZ_PASSIVE,
    COMPOSITE,
    IMPL,
    LAYER_MAP,
    LAYER_ORDER,
    MOTIVATION,
    NS,
    PHYSICAL,
    TECH_ACTIVE,
    TECH_BEHAVIOR,
    TECH_PASSIVE,
    TYPE_RANK,
    VALID_ELEMENT_TYPES,
    VALID_RELATIONSHIP_TYPES,
    XSI,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layout constants (Sugiyama hierarchical layout)
# ---------------------------------------------------------------------------
ELEMENT_W = 120           # standard element width (px)
ELEMENT_W_WIDE = 160      # wide element for long names (px)
ELEMENT_H = 55            # element height (px)
GAP_H = 40               # horizontal gap between elements (px)
GAP_V = 25               # vertical gap between rows within a layer (px)
MARGIN_X = 20             # left margin (px)
MARGIN_Y = 20             # top margin (px)
CELL_H = ELEMENT_H + GAP_V   # 80 px per row
WRAP_THRESHOLD = 5        # max elements per row before wrapping
WIDE_NAME_THRESHOLD = 15  # name length triggering wide element
LAYER_GAP = 40            # extra vertical gap between layers (px)

# ---------------------------------------------------------------------------
# Viewpoint definitions — element type sets per standard ArchiMate viewpoint
# ---------------------------------------------------------------------------
VIEWPOINTS: dict[str, set[str] | None] = {
    "application": APP_ACTIVE | APP_BEHAVIOR | APP_PASSIVE,
    "technology": TECH_ACTIVE | TECH_BEHAVIOR | TECH_PASSIVE,
    "business": BIZ_ACTIVE | BIZ_BEHAVIOR | BIZ_PASSIVE,
    "motivation": MOTIVATION,
    "physical": PHYSICAL,
    "implementation": IMPL,
    "application_cooperation": (
        APP_ACTIVE | APP_BEHAVIOR | APP_PASSIVE
        | TECH_ACTIVE | TECH_BEHAVIOR
    ),
    "layered": None,  # None = all elements (same as overview)
}

# Deterministic view indices per viewpoint (overview = 1, viewpoints start at 2)
_VP_VIEW_INDEX = {name: idx + 2 for idx, name in enumerate(sorted(VIEWPOINTS))}


def _filter_for_viewpoint(data: dict, viewpoint: str) -> dict:
    """Return data with elements/relationships filtered to a viewpoint.

    Elements not in the viewpoint's type set are removed.
    Relationships where either endpoint was removed are also removed.
    """
    allowed_types = VIEWPOINTS.get(viewpoint)
    if allowed_types is None:
        return data  # None = all elements (e.g. "layered")

    filtered_elements = [e for e in data["elements"] if e["type"] in allowed_types]
    kept_ids = {e["id"] for e in filtered_elements}
    filtered_rels = [
        r for r in data["relationships"]
        if r["source"] in kept_ids and r["target"] in kept_ids
    ]

    return {
        "model": data["model"],
        "elements": filtered_elements,
        "relationships": filtered_rels,
    }


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


def generate_viewpoint_xml(
    yaml_str: str,
    viewpoint: str,
) -> tuple[str, dict]:
    """Generate a single viewpoint view as an XML fragment.

    The returned XML is a <model> wrapper containing only the <views>
    section with a single view diagram. Use merge_archimate_view() to
    add it to an existing model.

    Args:
        yaml_str: Same YAML format as yaml_to_archimate_xml().
        viewpoint: One of VIEWPOINTS keys (e.g. "application",
            "technology", "business").

    Returns:
        Tuple of (xml_fragment, info_dict).

    Raises:
        ValueError: If viewpoint is unknown or yields <2 elements.
    """
    vp_lower = viewpoint.lower().replace(" ", "_")
    if vp_lower not in VIEWPOINTS:
        raise ValueError(
            f"Unknown viewpoint '{viewpoint}'. "
            f"Valid: {', '.join(sorted(VIEWPOINTS))}"
        )

    data = _parse_and_validate(yaml_str)
    filtered = _filter_for_viewpoint(data, vp_lower)
    if len(filtered["elements"]) < 2:
        raise ValueError(
            f"Viewpoint '{viewpoint}' yields {len(filtered['elements'])} "
            f"elements (minimum 2 required)"
        )

    # Build the view via _generate_view, then extract the <view> element
    # and place it as a direct child of root. merge_archimate_view()
    # handles this via its fallback path (frag_root.findall(TAG("view")))
    root = ET.Element(f"{{{NS}}}model", attrib={"identifier": "id-fragment"})
    vp_label = viewpoint.replace("_", " ").title()
    vp_index = _VP_VIEW_INDEX[vp_lower]
    _generate_view(root, filtered, view_index=vp_index, viewpoint_name=vp_label)

    # Restructure: move <view> out of <views>/<diagrams> to root level
    views_el = root.find(f"{{{NS}}}views")
    if views_el is not None:
        diagrams_el = views_el.find(f"{{{NS}}}diagrams")
        if diagrams_el is not None:
            for view_el in list(diagrams_el):
                root.append(view_el)
        root.remove(views_el)

    ET.register_namespace("", NS)
    ET.register_namespace("xsi", XSI)
    xml_str = ET.tostring(root, encoding="unicode", xml_declaration=True)

    info = {
        "viewpoint": vp_lower,
        "element_count": len(filtered["elements"]),
        "relationship_count": len(filtered["relationships"]),
    }
    logger.info(
        f"[yaml_to_xml] Viewpoint '{vp_lower}': "
        f"{info['element_count']} elements, "
        f"{info['relationship_count']} relationships"
    )
    return xml_str, info


# ---------------------------------------------------------------------------
# Property helpers
# ---------------------------------------------------------------------------

def _validate_properties(raw) -> dict[str, str]:
    """Validate and normalize a properties mapping.

    Accepts a dict of key→value pairs. Non-dict input returns empty dict.
    Keys and values are coerced to strings and stripped.
    """
    if not raw or not isinstance(raw, dict):
        return {}
    result = {}
    for k, v in raw.items():
        k_str = str(k).strip()
        if not k_str:
            continue
        result[k_str] = str(v).strip()
    return result


def _prop_def_id(key: str) -> str:
    """Convert a property key to an XML-safe propertyDefinition identifier.

    E.g., 'dct:identifier' → 'propdef-dct-identifier'

    Note: Keys that differ only by separator (e.g., 'dct:type' vs 'dct-type')
    would collide. In practice all ArchiMate property keys use colon notation
    (Dublin Core dct:*, ArchiMate archi:*), so this is acceptable.
    """
    sanitized = re.sub(r'[^a-zA-Z0-9-]', '-', key).strip('-').lower()
    return f"propdef-{sanitized}"


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

        if not elem.get("documentation", "").strip():
            logger.warning(
                f"[yaml_to_xml] Element '{eid}' ({etype}) has no documentation"
            )

        # Normalize ID: add 'id-' prefix if missing
        full_id = eid if eid.startswith("id-") else f"id-{eid}"
        if full_id in element_ids:
            raise ValueError(f"Duplicate element id: '{eid}'")
        element_ids.add(full_id)

        entry = {
            "id": full_id,
            "type": etype,
            "name": ename,
            "documentation": str(elem.get("documentation", "")).strip(),
        }
        props = _validate_properties(elem.get("properties"))
        if props:
            entry["properties"] = props
        normalized_elements.append(entry)

    # Build element type index for relationship validation
    element_type_index = {e["id"]: e["type"] for e in normalized_elements}

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
            logger.warning(
                f"Relationship {i}: source '{source}' does not reference "
                f"a valid element id — dropping relationship"
            )
            continue
        if full_target not in element_ids:
            logger.warning(
                f"Relationship {i}: target '{target}' does not reference "
                f"a valid element id — dropping relationship"
            )
            continue

        # Validate source→target pair against ALLOWED_PATTERNS
        if rtype != "Association":
            src_type = element_type_index.get(full_source, "")
            tgt_type = element_type_index.get(full_target, "")
            if src_type not in COMPOSITE and tgt_type not in COMPOSITE:
                patterns = ALLOWED_PATTERNS.get(rtype, [])
                allowed = any(
                    src_type in sp and tgt_type in tp for sp, tp in patterns
                )
                if not allowed:
                    logger.warning(
                        f"[yaml_to_xml] Relationship {i} ({rtype}): "
                        f"{src_type} -> {tgt_type} may not be a valid "
                        f"ArchiMate 3.2 relationship"
                    )

        # Derive deterministic ID
        src_code = full_source.removeprefix("id-")
        tgt_code = full_target.removeprefix("id-")
        pair_key = f"{src_code}-{tgt_code}"
        pair_counts[pair_key] += 1
        count = pair_counts[pair_key]
        rid = f"id-rel-{pair_key}" if count == 1 else f"id-rel-{pair_key}-{count}"

        rname = str(rel.get("name", "")).strip()

        rel_entry = {
            "id": rid,
            "type": rtype,
            "source": full_source,
            "target": full_target,
            "name": rname,
        }
        rel_props = _validate_properties(rel.get("properties"))
        if rel_props:
            rel_entry["properties"] = rel_props
        normalized_rels.append(rel_entry)

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
    "http://www.opengroup.org/xsd/archimate/3.0/archimate3_Diagram.xsd"
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

    # Collect all property keys (needed for propertyDefinitionRef on elements
    # and relationships). The <propertyDefinitions> block itself is emitted
    # AFTER <relationships> per ArchiMate Open Exchange schema ordering:
    # name, documentation, elements, relationships, organizations,
    # propertyDefinitions, views.
    all_prop_keys: dict[str, str] = {}  # key → propertyDefinitionRef ID
    for elem in data["elements"]:
        for k in elem.get("properties", {}):
            if k not in all_prop_keys:
                all_prop_keys[k] = _prop_def_id(k)
    for rel in data["relationships"]:
        for k in rel.get("properties", {}):
            if k not in all_prop_keys:
                all_prop_keys[k] = _prop_def_id(k)

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
        elem_props = elem.get("properties", {})
        if elem_props:
            props_el = ET.SubElement(el, f"{{{NS}}}properties")
            for pkey, pval in elem_props.items():
                ref_id = all_prop_keys.get(pkey, _prop_def_id(pkey))
                prop = ET.SubElement(
                    props_el, f"{{{NS}}}property",
                    attrib={"propertyDefinitionRef": ref_id},
                )
                v = ET.SubElement(prop, f"{{{NS}}}value")
                v.set("xml:lang", "en")
                v.text = pval

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
            rel_props = rel.get("properties", {})
            if rel_props:
                rprops_el = ET.SubElement(r, f"{{{NS}}}properties")
                for pkey, pval in rel_props.items():
                    ref_id = all_prop_keys.get(pkey, _prop_def_id(pkey))
                    prop = ET.SubElement(
                        rprops_el, f"{{{NS}}}property",
                        attrib={"propertyDefinitionRef": ref_id},
                    )
                    v = ET.SubElement(prop, f"{{{NS}}}value")
                    v.set("xml:lang", "en")
                    v.text = pval

    # Property definitions — after relationships, before views (schema order)
    if all_prop_keys:
        pdefs_el = ET.SubElement(root, f"{{{NS}}}propertyDefinitions")
        for key, ref_id in sorted(all_prop_keys.items()):
            pdef = ET.SubElement(
                pdefs_el, f"{{{NS}}}propertyDefinition",
                attrib={"identifier": ref_id, "type": "string"},
            )
            pn = ET.SubElement(pdef, f"{{{NS}}}name")
            pn.set("xml:lang", "en")
            pn.text = key

    return root


# ---------------------------------------------------------------------------
# Stage 3: Sugiyama hierarchical layout + view generation
#
# Implements the same conceptual steps as Dagre (archi-scripts):
#   1. Layer assignment — fixed by ArchiMate element type (LAYER_MAP)
#   2. Initial ordering — type_rank ASC, degree DESC, name ASC
#   3. Crossing reduction — 3 alternating barycenter sweeps
#   4. Row wrapping — max WRAP_THRESHOLD elements per row
#   5. Dynamic Y spacing — each layer starts after the previous ends + gap
# ---------------------------------------------------------------------------


def _elem_width(name: str) -> int:
    """Element width: wider box for long names to avoid label clipping."""
    return ELEMENT_W_WIDE if len(name) > WIDE_NAME_THRESHOLD else ELEMENT_W


def _sugiyama_positions(
    data: dict,
) -> tuple[list[dict], list[dict]]:
    """Compute node positions using Sugiyama hierarchical layout.

    Args:
        data: Parsed model dict with 'elements' and 'relationships'.

    Returns:
        Tuple of (positioned_nodes, connections) where each node has
        elementRef, x, y, w, h and each connection has relationshipRef,
        source (element ID), target (element ID).
    """
    # Build element lookup: element_id → {type, name, layer}
    elem_lookup: dict[str, dict] = {}
    for elem in data["elements"]:
        elem_lookup[elem["id"]] = {
            "type": elem["type"],
            "name": elem["name"],
            "layer": LAYER_MAP.get(elem["type"], "Composite"),
        }
    elem_ids = set(elem_lookup)

    # Build adjacency (undirected, for barycenter computation)
    adj: dict[str, set] = defaultdict(set)
    valid_rels: list[dict] = []
    for rel in data["relationships"]:
        s, t = rel["source"], rel["target"]
        if s in elem_ids and t in elem_ids and s != t:
            adj[s].add(t)
            adj[t].add(s)
            valid_rels.append(rel)

    degree = {eid: len(adj[eid]) for eid in elem_ids}

    # Group by layer, keep only active layers in canonical order
    active_layers = [
        lay for lay in LAYER_ORDER
        if any(elem_lookup[eid]["layer"] == lay for eid in elem_ids)
    ]
    layer_elems: dict[str, list[str]] = defaultdict(list)
    for eid in elem_ids:
        layer_elems[elem_lookup[eid]["layer"]].append(eid)

    # Initial ordering: type_rank ASC, degree DESC, name ASC
    for lay in active_layers:
        layer_elems[lay].sort(key=lambda eid: (
            TYPE_RANK.get(elem_lookup[eid]["type"], 50),
            -degree[eid],
            elem_lookup[eid]["name"],
        ))

    # Barycenter crossing reduction (3 alternating sweeps)
    def barycenter(eid: str, ref_pos: dict[str, int]) -> float | None:
        nbrs = [ref_pos[n] for n in adj[eid] if n in ref_pos]
        return sum(nbrs) / len(nbrs) if nbrs else None

    def reorder(layer_idx: int, direction: str) -> None:
        if direction == "down" and layer_idx == 0:
            return
        if direction == "up" and layer_idx == len(active_layers) - 1:
            return
        ref_lay = active_layers[
            layer_idx - 1 if direction == "down" else layer_idx + 1
        ]
        ref_pos = {eid: i for i, eid in enumerate(layer_elems[ref_lay])}
        cur_lay = active_layers[layer_idx]

        def sort_key(eid: str):
            b = barycenter(eid, ref_pos)
            if b is None:
                # No cross-layer edge: preserve type_rank / degree / alpha
                return (1, TYPE_RANK.get(elem_lookup[eid]["type"], 50),
                        -degree[eid], elem_lookup[eid]["name"])
            return (0, b, TYPE_RANK.get(elem_lookup[eid]["type"], 50),
                    elem_lookup[eid]["name"])

        layer_elems[cur_lay].sort(key=sort_key)

    for _ in range(3):
        for i in range(1, len(active_layers)):
            reorder(i, "down")
        for i in range(len(active_layers) - 2, -1, -1):
            reorder(i, "up")

    # Determine cell width from widest element
    max_w = max(
        (_elem_width(elem_lookup[eid]["name"]) for eid in elem_ids),
        default=ELEMENT_W,
    )
    cell_w = max_w + GAP_H

    # Dynamic layer Y starts
    layer_y: dict[str, int] = {}
    cur_y = MARGIN_Y
    for lay in active_layers:
        layer_y[lay] = cur_y
        n_rows = max(1, math.ceil(len(layer_elems[lay]) / WRAP_THRESHOLD))
        cur_y += n_rows * CELL_H + LAYER_GAP

    # Compute node positions
    nodes: list[dict] = []
    for lay in active_layers:
        for flat_idx, eid in enumerate(layer_elems[lay]):
            col = flat_idx % WRAP_THRESHOLD
            row = flat_idx // WRAP_THRESHOLD
            nodes.append({
                "elementRef": eid,
                "x": MARGIN_X + col * cell_w,
                "y": layer_y[lay] + row * CELL_H,
                "w": _elem_width(elem_lookup[eid]["name"]),
                "h": ELEMENT_H,
            })

    # Connections between elements that both have nodes
    connections: list[dict] = []
    for rel in valid_rels:
        connections.append({
            "relationshipRef": rel["id"],
            "source": rel["source"],
            "target": rel["target"],
        })

    return nodes, connections


def _generate_view(
    root: ET.Element,
    data: dict,
    view_index: int = 1,
    viewpoint_name: str = "Overview",
) -> None:
    """Add a view using Sugiyama hierarchical layout.

    Can be called multiple times on the same root to add multiple views
    with different viewpoint_name and view_index values.
    """
    nodes, connections = _sugiyama_positions(data)

    # Assign node IDs: nv{view_index}-{short_code}
    node_map: dict[str, str] = {}  # element_id → node_id
    for node in nodes:
        code = node["elementRef"].removeprefix("id-")
        nid = f"nv{view_index}-{code}"
        node_map[node["elementRef"]] = nid
        node["id"] = nid

    # Resolve connection node references
    for conn in connections:
        conn["id"] = f"cv{view_index}-{conn['relationshipRef'].removeprefix('id-')}"
        conn["source_nid"] = node_map[conn["source"]]
        conn["target_nid"] = node_map[conn["target"]]

    # Find or create <views>/<diagrams> (safe for multiple calls)
    views_el = root.find(f"{{{NS}}}views")
    if views_el is None:
        views_el = ET.SubElement(root, f"{{{NS}}}views")
    diagrams_el = views_el.find(f"{{{NS}}}diagrams")
    if diagrams_el is None:
        diagrams_el = ET.SubElement(views_el, f"{{{NS}}}diagrams")

    view_el = ET.SubElement(diagrams_el, f"{{{NS}}}view")
    view_el.set("identifier", f"id-v{view_index}")
    view_el.set(f"{{{XSI}}}type", "Diagram")
    vname = ET.SubElement(view_el, f"{{{NS}}}name")
    vname.set("xml:lang", "en")
    vname.text = f"{data['model']['name']} — {viewpoint_name}"

    for node in nodes:
        n = ET.SubElement(view_el, f"{{{NS}}}node")
        n.set("identifier", node["id"])
        n.set("elementRef", node["elementRef"])
        n.set(f"{{{XSI}}}type", "Element")
        n.set("x", str(node["x"]))
        n.set("y", str(node["y"]))
        n.set("w", str(node["w"]))
        n.set("h", str(node["h"]))

    for conn in connections:
        c = ET.SubElement(view_el, f"{{{NS}}}connection")
        c.set("identifier", conn["id"])
        c.set("relationshipRef", conn["relationshipRef"])
        c.set(f"{{{XSI}}}type", "Relationship")
        c.set("source", conn["source_nid"])
        c.set("target", conn["target_nid"])


# ---------------------------------------------------------------------------
# Reverse: XML → YAML
# ---------------------------------------------------------------------------

def _TAG(t): return f"{{{NS}}}{t}"  # noqa: N802


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

    # Property definitions: map propertyDefinitionRef → human-readable key
    prop_defs: dict[str, str] = {}
    prop_defs_node = root.find(_TAG("propertyDefinitions"))
    if prop_defs_node is not None:
        for pdef in prop_defs_node.findall(_TAG("propertyDefinition")):
            pdef_id = pdef.get("identifier", "")
            pdef_name_el = pdef.find(_TAG("name"))
            if pdef_id and pdef_name_el is not None and pdef_name_el.text:
                prop_defs[pdef_id] = pdef_name_el.text.strip()

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
        # Parse <properties><property> children (schema-correct wrapper)
        props = {}
        props_container = elem.find(_TAG("properties"))
        prop_source = props_container if props_container is not None else elem
        for prop_el in prop_source.findall(_TAG("property")):
            ref = prop_el.get("propertyDefinitionRef", "")
            val_el = prop_el.find(_TAG("value"))
            val = val_el.text.strip() if val_el is not None and val_el.text else ""
            key = prop_defs.get(ref, ref)
            if key and val:
                props[key] = val
        if props:
            entry["properties"] = props
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
            # Parse <properties><property> children (schema-correct wrapper)
            rel_props = {}
            rel_props_container = rel.find(_TAG("properties"))
            rel_prop_source = rel_props_container if rel_props_container is not None else rel
            for prop_el in rel_prop_source.findall(_TAG("property")):
                ref = prop_el.get("propertyDefinitionRef", "")
                val_el = prop_el.find(_TAG("value"))
                val = val_el.text.strip() if val_el is not None and val_el.text else ""
                key = prop_defs.get(ref, ref)
                if key and val:
                    rel_props[key] = val
            if rel_props:
                entry["properties"] = rel_props
            relationships.append(entry)

    result = _serialize_yaml(
        {"name": model_name, "documentation": model_doc},
        elements,
        relationships,
    )
    logger.info(
        f"[xml_to_yaml] Converted: {len(elements)} elements, "
        f"{len(relationships)} relationships, {len(result)} chars"
    )
    return result


def _serialize_yaml(
    model: dict, elements: list[dict], relationships: list[dict],
) -> str:
    """Serialize model data to human-readable YAML string with layer grouping.

    Args:
        model: Dict with 'name' and optional 'documentation'.
        elements: List of element dicts with short IDs (no 'id-' prefix).
        relationships: List of relationship dicts with short source/target IDs.

    Returns:
        YAML string ready for round-tripping through _parse_and_validate().
    """
    lines = ["model:"]
    lines.append(f'  name: "{_yaml_escape(model["name"])}"')
    if model.get("documentation"):
        lines.append(f'  documentation: "{_yaml_escape(model["documentation"])}"')
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
            if elem.get("properties"):
                lines.append("    properties:")
                for pkey, pval in elem["properties"].items():
                    lines.append(f'      "{_yaml_escape(pkey)}": "{_yaml_escape(pval)}"')

    lines.append("")
    if relationships:
        lines.append("relationships:")
        for rel in relationships:
            lines.append(f"  - type: {rel['type']}")
            lines.append(f"    source: {rel['source']}")
            lines.append(f"    target: {rel['target']}")
            if rel.get("name"):
                lines.append(f'    name: "{_yaml_escape(rel["name"])}"')
            if rel.get("properties"):
                lines.append("    properties:")
                for pkey, pval in rel["properties"].items():
                    lines.append(f'      "{_yaml_escape(pkey)}": "{_yaml_escape(pval)}"')
    else:
        lines.append("relationships: []")

    return "\n".join(lines) + "\n"


def _yaml_escape(text: str) -> str:
    """Escape characters that need quoting inside YAML double-quoted strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# Diff-based refinement: merge engine
# ---------------------------------------------------------------------------

# Fields that can be patched via modify (not id — that's the lookup key,
# not type — changing ArchiMate layer should be remove+add).
# "properties" requires special handling in the modify loop: additive merge
# instead of str() replacement. The set only gates which field names are
# accepted — the if/else in the loop handles the type difference.
_PATCHABLE_ELEMENT_FIELDS = {"name", "documentation", "properties"}


def apply_yaml_diff(base_yaml: str, diff_yaml: str) -> tuple[str, dict]:
    """Apply a structured YAML diff envelope to an existing ArchiMate model.

    The diff envelope uses a ``refinement:`` root key with ``add``,
    ``modify``, and ``remove`` sections.  All operations are validated
    before any mutation; if any operation is invalid the entire diff is
    rejected (all-or-nothing).

    Args:
        base_yaml: Existing model as YAML (short IDs, no ``id-`` prefix).
        diff_yaml: Diff envelope with ``refinement:`` root key.

    Returns:
        Tuple of (merged_yaml_string, change_summary_dict).

    Raises:
        ValueError: If the diff is structurally invalid or references
            nonexistent IDs.
    """
    # -- Parse inputs -------------------------------------------------------
    try:
        base = yaml.safe_load(base_yaml)
    except yaml.YAMLError as e:
        raise ValueError(f"Base YAML parse error: {e}") from e
    try:
        diff = yaml.safe_load(diff_yaml)
    except yaml.YAMLError as e:
        raise ValueError(f"Diff YAML parse error: {e}") from e

    if not isinstance(diff, dict) or "refinement" not in diff:
        raise ValueError("Diff must have a 'refinement' root key")

    ref = diff["refinement"]
    if not isinstance(ref, dict):
        raise ValueError("'refinement' must be a mapping")

    # -- Build mutable structures from base ---------------------------------
    model = dict(base.get("model", {}))
    elements: list[dict] = [dict(e) for e in base.get("elements", [])]
    relationships: list[dict] = [dict(r) for r in base.get("relationships", [])]

    # Index by short ID (strip id- prefix if present in base)
    element_index: dict[str, dict] = {}
    for elem in elements:
        sid = str(elem.get("id", "")).removeprefix("id-")
        elem["id"] = sid  # normalize to short
        element_index[sid] = elem

    # Normalize relationship source/target to short IDs
    for rel in relationships:
        rel["source"] = str(rel.get("source", "")).removeprefix("id-")
        rel["target"] = str(rel.get("target", "")).removeprefix("id-")

    # Derive relationship IDs from base model (before adds).
    # Modify keys must reference these base IDs, not post-add IDs.
    pair_counts: dict[str, int] = defaultdict(int)
    rel_index: dict[str, dict] = {}
    for rel in relationships:
        pair_key = f"{rel['source']}-{rel['target']}"
        pair_counts[pair_key] += 1
        count = pair_counts[pair_key]
        derived = f"rel-{pair_key}" if count == 1 else f"rel-{pair_key}-{count}"
        rel_index[derived] = rel

    summary = {
        "added_elements": 0,
        "added_relationships": 0,
        "modified": 0,
        "removed_elements": 0,
        "removed_relationships": 0,
        "cascade_notes": [],
        "warnings": [],
    }

    # -- ADD elements (before relationships so new IDs are available) --------
    add_section = ref.get("add", {}) or {}
    for new_elem in add_section.get("elements", []) or []:
        if not isinstance(new_elem, dict):
            raise ValueError("Each added element must be a mapping")
        eid = str(new_elem.get("id", "")).strip().removeprefix("id-")
        if not eid:
            raise ValueError("Added element missing 'id'")
        etype = str(new_elem.get("type", "")).strip()
        if etype not in VALID_ELEMENT_TYPES:
            raise ValueError(
                f"Added element '{eid}': invalid type '{etype}'"
            )
        ename = str(new_elem.get("name", "")).strip()
        if not ename:
            raise ValueError(f"Added element '{eid}': 'name' is required")
        if eid in element_index:
            raise ValueError(f"Added element '{eid}': ID already exists in model")

        entry = {"id": eid, "type": etype, "name": ename}
        edoc = str(new_elem.get("documentation", "")).strip()
        if edoc:
            entry["documentation"] = edoc
        entry_props = _validate_properties(new_elem.get("properties"))
        if entry_props:
            entry["properties"] = entry_props
        elements.append(entry)
        element_index[eid] = entry
        summary["added_elements"] += 1

    # -- ADD relationships --------------------------------------------------
    for new_rel in add_section.get("relationships", []) or []:
        if not isinstance(new_rel, dict):
            raise ValueError("Each added relationship must be a mapping")
        rtype = str(new_rel.get("type", "")).strip()
        if rtype not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(f"Added relationship: invalid type '{rtype}'")
        src = str(new_rel.get("source", "")).strip().removeprefix("id-")
        tgt = str(new_rel.get("target", "")).strip().removeprefix("id-")
        if not src or not tgt:
            raise ValueError("Added relationship: 'source' and 'target' required")
        if src not in element_index:
            raise ValueError(
                f"Added relationship: source '{src}' not found in model"
            )
        if tgt not in element_index:
            raise ValueError(
                f"Added relationship: target '{tgt}' not found in model"
            )
        entry = {"type": rtype, "source": src, "target": tgt}
        rname = str(new_rel.get("name", "")).strip()
        if rname:
            entry["name"] = rname
        rel_props = _validate_properties(new_rel.get("properties"))
        if rel_props:
            entry["properties"] = rel_props
        relationships.append(entry)
        summary["added_relationships"] += 1

    # -- MODIFY elements, relationships, + model metadata --------------------
    modify_section = ref.get("modify", {}) or {}
    for key, patches in modify_section.items():
        if not isinstance(patches, dict):
            raise ValueError(f"Modify '{key}': value must be a mapping of fields")

        if key == "model":
            # Patch model metadata
            for field, value in patches.items():
                if field not in {"name", "documentation"}:
                    raise ValueError(
                        f"Modify model: unknown field '{field}' "
                        f"(allowed: name, documentation)"
                    )
                model[field] = str(value).strip()
            summary["modified"] += 1
            continue

        # Relationship modify: key starts with "rel-"
        if key.startswith("rel-"):
            if key not in rel_index:
                raise ValueError(f"Modify '{key}': relationship not found in model")
            target_rel = rel_index[key]
            for field, value in patches.items():
                if field == "properties":
                    existing = target_rel.get("properties", {})
                    if not isinstance(existing, dict):
                        existing = {}
                    existing.update(_validate_properties(value))
                    target_rel["properties"] = existing
                elif field == "name":
                    target_rel["name"] = str(value).strip()
                else:
                    raise ValueError(
                        f"Modify '{key}': cannot patch field '{field}' on relationship "
                        f"(allowed: name, properties)"
                    )
            summary["modified"] += 1
            continue

        # Element modify
        eid = str(key).strip().removeprefix("id-")
        if eid not in element_index:
            raise ValueError(f"Modify '{eid}': element not found in model")
        elem = element_index[eid]
        for field, value in patches.items():
            if field not in _PATCHABLE_ELEMENT_FIELDS:
                raise ValueError(
                    f"Modify '{eid}': cannot patch field '{field}' "
                    f"(allowed: {', '.join(sorted(_PATCHABLE_ELEMENT_FIELDS))})"
                )
            if field == "properties":
                existing = elem.get("properties", {})
                if not isinstance(existing, dict):
                    existing = {}
                existing.update(_validate_properties(value))
                elem["properties"] = existing
            else:
                elem[field] = str(value).strip()
        summary["modified"] += 1

    # -- REMOVE elements (with cascade) -------------------------------------
    # Warn-and-skip for nonexistent IDs (LLM may reference stale elements).
    # Valid removals still apply. Add/modify remain strict.
    remove_section = ref.get("remove", {}) or {}
    for rid in remove_section.get("elements", []) or []:
        eid = str(rid).strip().removeprefix("id-")
        if eid not in element_index:
            warning = f"Remove '{eid}': element not found in model (skipped)"
            logger.warning(f"[apply_yaml_diff] {warning}")
            summary["warnings"].append(warning)
            continue

        # Remove element
        del element_index[eid]
        elements[:] = [e for e in elements if e["id"] != eid]
        summary["removed_elements"] += 1

        # Cascade: remove dangling relationships
        kept = []
        for rel in relationships:
            if rel["source"] == eid or rel["target"] == eid:
                summary["removed_relationships"] += 1
                summary["cascade_notes"].append(
                    f"Removed {rel['type']} relationship: "
                    f"{rel['source']}\u2192{rel['target']} "
                    f"(dangling after {eid} removal)"
                )
            else:
                kept.append(rel)
        relationships[:] = kept

    # -- Serialize and validate ---------------------------------------------
    merged_yaml = _serialize_yaml(model, elements, relationships)

    # Run through _parse_and_validate to catch any structural issues
    _parse_and_validate(merged_yaml)

    logger.info(
        f"[apply_yaml_diff] Merged: "
        f"+{summary['added_elements']}e +{summary['added_relationships']}r, "
        f"~{summary['modified']}mod, "
        f"-{summary['removed_elements']}e -{summary['removed_relationships']}r"
    )
    return merged_yaml, summary
