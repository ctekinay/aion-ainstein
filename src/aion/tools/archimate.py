"""ArchiMate 3.2 Open Exchange XML tool wrappers.

Wraps the validation, inspection, and merge scripts from
skills/archimate-*/scripts/ as string-in/dict-out functions for
RAG agent tool registration.

Original scripts are kept as-is for standalone CLI use.
"""

import logging
import xml.etree.ElementTree as ET
from collections import defaultdict

logger = logging.getLogger(__name__)

# ArchiMate Open Exchange Format namespace — 3.0 URI is used for all 3.x
# versions (3.0, 3.1, 3.2). Archi validates imports against this namespace.
NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
def TAG(t): return f"{{{NS}}}{t}"  # noqa: N802

ET.register_namespace("", NS)
ET.register_namespace("xsi", XSI)

# ---------------------------------------------------------------------------
# Constants from validate_archimate.py
# ---------------------------------------------------------------------------

VALID_ELEMENT_TYPES = {
    "Stakeholder", "Driver", "Assessment", "Goal", "Outcome", "Principle",
    "Requirement", "Constraint", "Meaning", "Value",
    "Resource", "Capability", "CourseOfAction", "ValueStream",
    "BusinessActor", "BusinessRole", "BusinessCollaboration", "BusinessInterface",
    "BusinessProcess", "BusinessFunction", "BusinessInteraction",
    "BusinessEvent", "BusinessService",
    "BusinessObject", "Contract", "Representation", "Product",
    "ApplicationComponent", "ApplicationCollaboration", "ApplicationInterface",
    "ApplicationFunction", "ApplicationInteraction", "ApplicationProcess",
    "ApplicationEvent", "ApplicationService",
    "DataObject",
    "Node", "Device", "SystemSoftware", "TechnologyCollaboration",
    "TechnologyInterface", "Path", "CommunicationNetwork",
    "TechnologyFunction", "TechnologyProcess", "TechnologyInteraction",
    "TechnologyEvent", "TechnologyService",
    "Artifact",
    "Equipment", "Facility", "DistributionNetwork", "Material",
    "WorkPackage", "Deliverable", "ImplementationEvent", "Gap", "Plateau",
    "Grouping", "Location",
    "AndJunction", "OrJunction",
}

VALID_RELATIONSHIP_TYPES = {
    "Composition", "Aggregation", "Assignment", "Realization",
    "Serving", "Access", "Influence", "Association",
    "Triggering", "Flow", "Specialization", "Junction",
}

# Category sets for relationship validation
MOTIVATION = {
    "Stakeholder", "Driver", "Assessment", "Goal", "Outcome", "Principle",
    "Requirement", "Constraint", "Meaning", "Value", "Capability",
    "CourseOfAction", "ValueStream", "Resource",
}
BIZ_ACTIVE = {"BusinessActor", "BusinessRole", "BusinessCollaboration", "BusinessInterface"}
BIZ_BEHAVIOR = {"BusinessProcess", "BusinessFunction", "BusinessInteraction", "BusinessEvent", "BusinessService"}
BIZ_PASSIVE = {"BusinessObject", "Contract", "Representation", "Product"}
APP_ACTIVE = {"ApplicationComponent", "ApplicationCollaboration", "ApplicationInterface"}
APP_BEHAVIOR = {"ApplicationFunction", "ApplicationInteraction", "ApplicationProcess", "ApplicationEvent", "ApplicationService"}
APP_PASSIVE = {"DataObject"}
TECH_ACTIVE = {"Node", "Device", "SystemSoftware", "TechnologyCollaboration", "TechnologyInterface", "Path", "CommunicationNetwork"}
TECH_BEHAVIOR = {"TechnologyFunction", "TechnologyProcess", "TechnologyInteraction", "TechnologyEvent", "TechnologyService"}
TECH_PASSIVE = {"Artifact"}
PHYSICAL = {"Equipment", "Facility", "DistributionNetwork", "Material"}
IMPL = {"WorkPackage", "Deliverable", "ImplementationEvent", "Gap", "Plateau"}
COMPOSITE = {"Grouping", "Location"}
ALL_ELEMENTS = (
    MOTIVATION | BIZ_ACTIVE | BIZ_BEHAVIOR | BIZ_PASSIVE |
    APP_ACTIVE | APP_BEHAVIOR | APP_PASSIVE |
    TECH_ACTIVE | TECH_BEHAVIOR | TECH_PASSIVE |
    PHYSICAL | IMPL | COMPOSITE
)

ALLOWED_PATTERNS = {
    "Serving": [
        (APP_ACTIVE | APP_BEHAVIOR, BIZ_ACTIVE | BIZ_BEHAVIOR),
        (TECH_ACTIVE | TECH_BEHAVIOR, APP_ACTIVE | APP_BEHAVIOR),
        (TECH_ACTIVE | TECH_BEHAVIOR, BIZ_ACTIVE | BIZ_BEHAVIOR),
        (BIZ_BEHAVIOR, BIZ_ACTIVE | BIZ_BEHAVIOR),
        (APP_BEHAVIOR | APP_ACTIVE, APP_ACTIVE | APP_BEHAVIOR),
        (TECH_BEHAVIOR, TECH_ACTIVE | TECH_BEHAVIOR),
        (PHYSICAL, PHYSICAL | BIZ_ACTIVE | BIZ_BEHAVIOR),
    ],
    "Assignment": [
        (BIZ_ACTIVE, BIZ_ACTIVE | BIZ_BEHAVIOR),
        (APP_ACTIVE, APP_ACTIVE | APP_BEHAVIOR),
        (TECH_ACTIVE, TECH_ACTIVE | TECH_BEHAVIOR | APP_ACTIVE | APP_BEHAVIOR),
    ],
    "Realization": [
        (BIZ_BEHAVIOR, BIZ_BEHAVIOR | BIZ_PASSIVE | MOTIVATION),
        (APP_ACTIVE | APP_BEHAVIOR, APP_BEHAVIOR | BIZ_BEHAVIOR | BIZ_PASSIVE | MOTIVATION),
        (TECH_ACTIVE | TECH_BEHAVIOR, APP_BEHAVIOR | APP_PASSIVE),
        (TECH_PASSIVE, APP_PASSIVE),
        (APP_PASSIVE, BIZ_PASSIVE),
        (BIZ_PASSIVE, BIZ_PASSIVE | BIZ_BEHAVIOR),
        (IMPL, IMPL | MOTIVATION | BIZ_BEHAVIOR | BIZ_PASSIVE | APP_ACTIVE | APP_BEHAVIOR),
        (MOTIVATION, MOTIVATION | BIZ_BEHAVIOR | BIZ_PASSIVE),
        (PHYSICAL, PHYSICAL | BIZ_PASSIVE),
        ({"Material"}, {"Equipment"}),  # 3.2: Material realizes Equipment
    ],
    "Composition": [(ALL_ELEMENTS, ALL_ELEMENTS)],
    "Aggregation": [(ALL_ELEMENTS, ALL_ELEMENTS)],
    "Access": [
        (BIZ_ACTIVE | BIZ_BEHAVIOR, BIZ_PASSIVE),
        (APP_ACTIVE | APP_BEHAVIOR, APP_PASSIVE | BIZ_PASSIVE),
        (TECH_ACTIVE | TECH_BEHAVIOR, TECH_PASSIVE | APP_PASSIVE),
        (PHYSICAL, PHYSICAL | BIZ_PASSIVE),
    ],
    "Influence": [
        (MOTIVATION | ALL_ELEMENTS, MOTIVATION),
        (MOTIVATION, ALL_ELEMENTS),
    ],
    "Triggering": [
        (BIZ_BEHAVIOR, BIZ_BEHAVIOR),
        (APP_BEHAVIOR, APP_BEHAVIOR),
        (TECH_BEHAVIOR, TECH_BEHAVIOR),
        (IMPL, IMPL),
        ({"AndJunction", "OrJunction"}, BIZ_BEHAVIOR | APP_BEHAVIOR | TECH_BEHAVIOR | IMPL),
        (BIZ_BEHAVIOR | APP_BEHAVIOR | TECH_BEHAVIOR | IMPL, {"AndJunction", "OrJunction"}),
        (BIZ_BEHAVIOR | APP_BEHAVIOR | TECH_BEHAVIOR, BIZ_BEHAVIOR | APP_BEHAVIOR | TECH_BEHAVIOR),
    ],
    "Flow": [
        (BIZ_BEHAVIOR | BIZ_ACTIVE, BIZ_BEHAVIOR | BIZ_ACTIVE | BIZ_PASSIVE),
        (APP_BEHAVIOR | APP_ACTIVE, APP_BEHAVIOR | APP_ACTIVE | APP_PASSIVE),
        (TECH_BEHAVIOR | TECH_ACTIVE, TECH_BEHAVIOR | TECH_ACTIVE | TECH_PASSIVE),
        (ALL_ELEMENTS, ALL_ELEMENTS),
    ],
    "Specialization": [(ALL_ELEMENTS, ALL_ELEMENTS)],
    "Junction": [(ALL_ELEMENTS, ALL_ELEMENTS)],
}

# ---------------------------------------------------------------------------
# Constants from inspect_model.py
# ---------------------------------------------------------------------------

LAYER_MAP = {
    "Stakeholder": "Motivation", "Driver": "Motivation", "Assessment": "Motivation",
    "Goal": "Motivation", "Outcome": "Motivation", "Principle": "Motivation",
    "Requirement": "Motivation", "Constraint": "Motivation", "Meaning": "Motivation",
    "Value": "Motivation",
    "Resource": "Strategy", "Capability": "Strategy", "CourseOfAction": "Strategy",
    "ValueStream": "Strategy",
    "BusinessActor": "Business", "BusinessRole": "Business", "BusinessCollaboration": "Business",
    "BusinessInterface": "Business", "BusinessProcess": "Business", "BusinessFunction": "Business",
    "BusinessInteraction": "Business", "BusinessEvent": "Business", "BusinessService": "Business",
    "BusinessObject": "Business", "Contract": "Business", "Representation": "Business",
    "Product": "Business",
    "ApplicationComponent": "Application", "ApplicationCollaboration": "Application",
    "ApplicationInterface": "Application", "ApplicationFunction": "Application",
    "ApplicationInteraction": "Application", "ApplicationProcess": "Application",
    "ApplicationEvent": "Application", "ApplicationService": "Application",
    "DataObject": "Application",
    "Node": "Technology", "Device": "Technology", "SystemSoftware": "Technology",
    "TechnologyCollaboration": "Technology", "TechnologyInterface": "Technology",
    "Path": "Technology", "CommunicationNetwork": "Technology",
    "TechnologyFunction": "Technology", "TechnologyProcess": "Technology",
    "TechnologyInteraction": "Technology", "TechnologyEvent": "Technology",
    "TechnologyService": "Technology", "Artifact": "Technology",
    "Equipment": "Physical", "Facility": "Physical", "DistributionNetwork": "Physical",
    "Material": "Physical",
    "WorkPackage": "Implementation", "Deliverable": "Implementation",
    "ImplementationEvent": "Implementation", "Gap": "Implementation", "Plateau": "Implementation",
    "Grouping": "Composite", "Location": "Composite",
    "AndJunction": "Composite", "OrJunction": "Composite",
}

LAYER_ORDER = [
    "Motivation", "Strategy", "Business", "Application",
    "Technology", "Physical", "Implementation", "Composite",
]

# Within-layer sort priority for Sugiyama layout (lower = placed first).
# Grouped by semantic role so related element types cluster visually.
TYPE_RANK = {
    "Driver": 10, "Goal": 10, "Outcome": 10,
    "Principle": 11, "Value": 11,
    "Requirement": 12, "Constraint": 12,
    "Stakeholder": 15, "Assessment": 15, "Meaning": 15,
    "Resource": 20, "Capability": 20, "CourseOfAction": 20, "ValueStream": 20,
    "BusinessActor": 30, "BusinessRole": 30, "BusinessCollaboration": 30,
    "BusinessInterface": 31, "BusinessProcess": 31,
    "BusinessEvent": 32, "BusinessService": 32, "BusinessObject": 32,
    "BusinessFunction": 33, "BusinessInteraction": 33,
    "Contract": 35, "Representation": 35, "Product": 35,
    "ApplicationInterface": 40, "ApplicationProcess": 40,
    "ApplicationEvent": 41, "ApplicationService": 41, "DataObject": 41,
    "ApplicationComponent": 42, "ApplicationCollaboration": 42,
    "ApplicationFunction": 42, "ApplicationInteraction": 42,
    "Node": 50, "Device": 50, "SystemSoftware": 50, "TechnologyCollaboration": 50,
    "TechnologyInterface": 51, "Path": 51, "CommunicationNetwork": 51,
    "TechnologyProcess": 52, "TechnologyEvent": 52, "TechnologyService": 52,
    "TechnologyFunction": 53, "TechnologyInteraction": 53, "Artifact": 53,
    "Equipment": 60, "Facility": 60,
    "DistributionNetwork": 61, "Material": 62,
    "WorkPackage": 70, "ImplementationEvent": 70, "Plateau": 70,
    "Deliverable": 71, "Gap": 71,
    "Grouping": 99, "Location": 99,
    "AndJunction": 99, "OrJunction": 99,
}


# ---------------------------------------------------------------------------
# Tool 1: validate_archimate
# ---------------------------------------------------------------------------

def _qname(elem: ET.Element) -> str:
    return elem.get(f"{{{XSI}}}type", "")


def validate_archimate(xml_content: str) -> dict:
    """Validate ArchiMate 3.2 Open Exchange XML content.

    Returns a structured result with validity status, counts, errors,
    and warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        return {
            "valid": False,
            "element_count": 0,
            "relationship_count": 0,
            "errors": [f"XML parse error: {e}"],
            "warnings": [],
        }

    if root.tag != TAG("model"):
        errors.append(f"Root element must be 'model' in namespace {NS}, got {root.tag}")

    element_ids: dict[str, str] = {}
    rel_ids: dict[str, tuple] = {}

    elements_node = root.find(TAG("elements"))
    if elements_node is not None:
        for elem in elements_node.findall(TAG("element")):
            eid = elem.get("identifier")
            etype = _qname(elem)
            if not eid:
                errors.append(f"Element missing identifier: {ET.tostring(elem, encoding='unicode')[:80]}")
                continue
            if etype not in VALID_ELEMENT_TYPES:
                errors.append(f"Invalid element type '{etype}' for element {eid}")
            doc_el = elem.find(TAG("documentation"))
            if doc_el is None or not (doc_el.text or "").strip():
                warnings.append(f"Element {eid} has no documentation")
            element_ids[eid] = etype

    relationships_node = root.find(TAG("relationships"))
    if relationships_node is not None:
        for rel in relationships_node.findall(TAG("relationship")):
            rid = rel.get("identifier")
            rtype = _qname(rel)
            src = rel.get("source")
            tgt = rel.get("target")

            if not rid:
                errors.append("Relationship missing identifier")
                continue

            if rtype not in VALID_RELATIONSHIP_TYPES:
                errors.append(f"Invalid relationship type '{rtype}' for relationship {rid}")

            if src not in element_ids:
                errors.append(f"Relationship {rid}: source '{src}' not found in elements")
            if tgt not in element_ids:
                errors.append(f"Relationship {rid}: target '{tgt}' not found in elements")

            if src in element_ids and tgt in element_ids and rtype != "Association":
                src_type = element_ids[src]
                tgt_type = element_ids[tgt]
                if src_type not in COMPOSITE and tgt_type not in COMPOSITE:
                    if src_type != "ValueStream" and tgt_type != "ValueStream":
                        patterns = ALLOWED_PATTERNS.get(rtype, [])
                        allowed = any(src_type in sp and tgt_type in tp for sp, tp in patterns)
                        if not allowed:
                            warnings.append(
                                f"Relationship {rid} ({rtype}): {src_type} -> {tgt_type} "
                                f"may not be a valid ArchiMate 3.2 relationship"
                            )

            rel_ids[rid] = (rtype, src, tgt)

    # View referential integrity
    views = root.find(TAG("views"))
    if views is not None:
        diagrams = views.find(TAG("diagrams"))
        if diagrams is not None:
            for view in diagrams.findall(TAG("view")):
                view_id = view.get("identifier", "unknown")
                node_ids: set[str] = set()

                def _collect_nodes(parent: ET.Element) -> None:
                    for node in parent.findall(TAG("node")):
                        nid = node.get("identifier")
                        eref = node.get("elementRef")
                        if nid:
                            node_ids.add(nid)
                        if eref and eref not in element_ids:
                            errors.append(f"View {view_id}: node {nid} references unknown element {eref}")
                        _collect_nodes(node)

                _collect_nodes(view)

                for conn in view.findall(TAG("connection")):
                    cid = conn.get("identifier", "?")
                    rref = conn.get("relationshipRef")
                    csrc = conn.get("source")
                    ctgt = conn.get("target")
                    if rref and rref not in rel_ids:
                        errors.append(f"View {view_id}: connection {cid} references unknown relationship {rref}")
                    if csrc and csrc not in node_ids:
                        errors.append(f"View {view_id}: connection {cid} source node {csrc} not found in view")
                    if ctgt and ctgt not in node_ids:
                        errors.append(f"View {view_id}: connection {cid} target node {ctgt} not found in view")

    return {
        "valid": len(errors) == 0,
        "element_count": len(element_ids),
        "relationship_count": len(rel_ids),
        "errors": errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Tool 2: inspect_archimate_model
# ---------------------------------------------------------------------------

def _get_name(elem: ET.Element) -> str:
    name_el = elem.find(TAG("name"))
    if name_el is not None and name_el.text:
        return name_el.text.strip()
    return "(unnamed)"


def inspect_archimate_model(xml_content: str) -> dict:
    """Inspect an ArchiMate model and return a structured summary.

    Returns elements by layer, relationships by type, existing views,
    and machine-readable indexes.
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}"}

    model_name = _get_name(root)
    elements: dict[str, dict] = {}
    by_layer: dict[str, list] = defaultdict(list)

    elements_node = root.find(TAG("elements"))
    if elements_node is not None:
        for elem in elements_node.findall(TAG("element")):
            eid = elem.get("identifier")
            etype = _qname(elem)
            ename = _get_name(elem)
            elements[eid] = {"type": etype, "name": ename}
            layer = LAYER_MAP.get(etype, "Unknown")
            by_layer[layer].append({"id": eid, "type": etype, "name": ename})

    rels: dict[str, dict] = {}
    by_rel_type: dict[str, int] = defaultdict(int)

    rels_node = root.find(TAG("relationships"))
    if rels_node is not None:
        for rel in rels_node.findall(TAG("relationship")):
            rid = rel.get("identifier")
            rtype = _qname(rel)
            src = rel.get("source")
            tgt = rel.get("target")
            rels[rid] = {"type": rtype, "source": src, "target": tgt}
            by_rel_type[rtype] += 1

    existing_views = []
    views_node = root.find(TAG("views"))
    if views_node is not None:
        diagrams = views_node.find(TAG("diagrams"))
        if diagrams is not None:
            for view in diagrams.findall(TAG("view")):
                vid = view.get("identifier")
                vname = _get_name(view)
                node_count = len(list(view.findall(TAG("node"))))
                conn_count = len(list(view.findall(TAG("connection"))))
                existing_views.append({
                    "id": vid, "name": vname,
                    "nodes": node_count, "connections": conn_count,
                })

    # Build ordered elements_by_layer
    elements_by_layer = {}
    for layer in LAYER_ORDER:
        items = by_layer.get(layer)
        if items:
            elements_by_layer[layer] = items

    # Machine-readable indexes
    element_index = [
        f"{eid} | {edata['type']} | {LAYER_MAP.get(edata['type'], 'Unknown')} | {edata['name']}"
        for eid, edata in elements.items()
    ]
    relationship_index = [
        f"{rid} | {rdata['type']} | {rdata['source']} ({elements.get(rdata['source'], {}).get('name', '?')}) -> {rdata['target']} ({elements.get(rdata['target'], {}).get('name', '?')})"
        for rid, rdata in rels.items()
    ]

    return {
        "model_name": model_name,
        "element_count": len(elements),
        "relationship_count": len(rels),
        "elements_by_layer": elements_by_layer,
        "relationships_by_type": dict(by_rel_type),
        "existing_views": existing_views,
        "element_index": element_index,
        "relationship_index": relationship_index,
    }


# ---------------------------------------------------------------------------
# Tool 3: merge_archimate_view
# ---------------------------------------------------------------------------

def _find_or_create(parent: ET.Element, tag: str) -> ET.Element:
    child = parent.find(TAG(tag))
    if child is None:
        child = ET.SubElement(parent, TAG(tag))
    return child


def merge_archimate_view(model_xml: str, fragment_xml: str) -> dict:
    """Merge a view fragment into an existing ArchiMate model.

    The fragment may contain new elements, relationships, and views.
    Returns the merged model XML and counts of added items.
    """
    try:
        model_root = ET.fromstring(model_xml)
    except ET.ParseError as e:
        return {"success": False, "error": f"Model XML parse error: {e}",
                "merged_xml": None, "elements_added": 0,
                "relationships_added": 0, "views_added": 0}

    try:
        frag_root = ET.fromstring(fragment_xml)
    except ET.ParseError as e:
        return {"success": False, "error": f"Fragment XML parse error: {e}",
                "merged_xml": None, "elements_added": 0,
                "relationships_added": 0, "views_added": 0}

    added_elements = 0
    added_relationships = 0
    added_views = 0

    # Append new elements
    frag_elements = frag_root.find("elements") or frag_root.find(TAG("elements"))
    if frag_elements is not None:
        model_elements = _find_or_create(model_root, "elements")
        for elem in list(frag_elements):
            model_elements.append(elem)
            added_elements += 1

    # Append new relationships
    frag_rels = frag_root.find("relationships") or frag_root.find(TAG("relationships"))
    if frag_rels is not None:
        model_rels = _find_or_create(model_root, "relationships")
        for rel in list(frag_rels):
            model_rels.append(rel)
            added_relationships += 1

    # Append new views
    frag_views = frag_root.find("views") or frag_root.find(TAG("views"))
    if frag_views is not None:
        model_views = _find_or_create(model_root, "views")
        model_diagrams = _find_or_create(model_views, "diagrams")
        for view in list(frag_views):
            model_diagrams.append(view)
            added_views += 1
    else:
        for view in frag_root.findall("view") + frag_root.findall(TAG("view")):
            model_views = _find_or_create(model_root, "views")
            model_diagrams = _find_or_create(model_views, "diagrams")
            model_diagrams.append(view)
            added_views += 1

    merged_xml = ET.tostring(model_root, encoding="unicode", xml_declaration=True)

    return {
        "success": True,
        "merged_xml": merged_xml,
        "elements_added": added_elements,
        "relationships_added": added_relationships,
        "views_added": added_views,
        "error": None,
    }
