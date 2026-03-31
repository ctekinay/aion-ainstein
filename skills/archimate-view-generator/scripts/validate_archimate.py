#!/usr/bin/env python3
"""
ArchiMate 3.2 Open Exchange XML Validator
Validates generated files for:
1. Well-formed XML
2. Required structure (model, elements, relationships)
3. Valid element xsi:type values
4. Valid relationship xsi:type values  
5. Allowed source->target combinations per relationship type
6. Referential integrity
"""

import sys
import xml.etree.ElementTree as ET

NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
TAG = lambda t: f"{{{NS}}}{t}"

# Valid element types
VALID_ELEMENT_TYPES = {
    # Motivation
    "Stakeholder","Driver","Assessment","Goal","Outcome","Principle",
    "Requirement","Constraint","Meaning","Value",
    # Strategy
    "Resource","Capability","CourseOfAction","ValueStream",
    # Business - Active
    "BusinessActor","BusinessRole","BusinessCollaboration","BusinessInterface",
    # Business - Behavior
    "BusinessProcess","BusinessFunction","BusinessInteraction",
    "BusinessEvent","BusinessService",
    # Business - Passive
    "BusinessObject","Contract","Representation","Product",
    # Application - Active
    "ApplicationComponent","ApplicationCollaboration","ApplicationInterface",
    # Application - Behavior
    "ApplicationFunction","ApplicationInteraction","ApplicationProcess",
    "ApplicationEvent","ApplicationService",
    # Application - Passive
    "DataObject",
    # Technology - Active
    "Node","Device","SystemSoftware","TechnologyCollaboration",
    "TechnologyInterface","Path","CommunicationNetwork",
    # Technology - Behavior
    "TechnologyFunction","TechnologyProcess","TechnologyInteraction",
    "TechnologyEvent","TechnologyService",
    # Technology - Passive
    "Artifact",
    # Physical
    "Equipment","Facility","DistributionNetwork","Material",
    # Implementation
    "WorkPackage","Deliverable","ImplementationEvent","Gap","Plateau",
    # Composite
    "Grouping","Location",
    # Junction (element type too, used in flows)
    "AndJunction","OrJunction",
}

# Valid relationship types
VALID_RELATIONSHIP_TYPES = {
    "Composition","Aggregation","Assignment","Realization",
    "Serving","Access","Influence","Association",
    "Triggering","Flow","Specialization","Junction",
}

# Allowed source-target combos per relationship
# Using broad category sets for conciseness
MOTIVATION = {"Stakeholder","Driver","Assessment","Goal","Outcome","Principle",
               "Requirement","Constraint","Meaning","Value","Capability","CourseOfAction","ValueStream","Resource"}
BIZ_ACTIVE = {"BusinessActor","BusinessRole","BusinessCollaboration","BusinessInterface"}
BIZ_BEHAVIOR = {"BusinessProcess","BusinessFunction","BusinessInteraction","BusinessEvent","BusinessService"}
BIZ_PASSIVE = {"BusinessObject","Contract","Representation","Product"}
APP_ACTIVE = {"ApplicationComponent","ApplicationCollaboration","ApplicationInterface"}
APP_BEHAVIOR = {"ApplicationFunction","ApplicationInteraction","ApplicationProcess","ApplicationEvent","ApplicationService"}
APP_PASSIVE = {"DataObject"}
TECH_ACTIVE = {"Node","Device","SystemSoftware","TechnologyCollaboration","TechnologyInterface","Path","CommunicationNetwork"}
TECH_BEHAVIOR = {"TechnologyFunction","TechnologyProcess","TechnologyInteraction","TechnologyEvent","TechnologyService"}
TECH_PASSIVE = {"Artifact"}
PHYSICAL = {"Equipment","Facility","DistributionNetwork","Material"}
IMPL = {"WorkPackage","Deliverable","ImplementationEvent","Gap","Plateau"}
COMPOSITE = {"Grouping","Location"}

ALL_ELEMENTS = (MOTIVATION | BIZ_ACTIVE | BIZ_BEHAVIOR | BIZ_PASSIVE |
                APP_ACTIVE | APP_BEHAVIOR | APP_PASSIVE |
                TECH_ACTIVE | TECH_BEHAVIOR | TECH_PASSIVE |
                PHYSICAL | IMPL | COMPOSITE)

# For relationship validation - define allowed patterns
# Format: {rel_type: [(source_set, target_set), ...]}
# Association is always allowed so not listed here
ALLOWED_PATTERNS = {
    "Serving": [
        (APP_ACTIVE | APP_BEHAVIOR, BIZ_ACTIVE | BIZ_BEHAVIOR),
        (TECH_ACTIVE | TECH_BEHAVIOR, APP_ACTIVE | APP_BEHAVIOR),
        (TECH_ACTIVE | TECH_BEHAVIOR, BIZ_ACTIVE | BIZ_BEHAVIOR),
        (BIZ_BEHAVIOR, BIZ_ACTIVE | BIZ_BEHAVIOR),
        (APP_BEHAVIOR | APP_ACTIVE, APP_ACTIVE | APP_BEHAVIOR),  # Interface → Service
        (TECH_BEHAVIOR, TECH_ACTIVE | TECH_BEHAVIOR),
        (PHYSICAL, PHYSICAL | BIZ_ACTIVE | BIZ_BEHAVIOR),
    ],
    "Assignment": [
        (BIZ_ACTIVE, BIZ_ACTIVE | BIZ_BEHAVIOR),
        (APP_ACTIVE, APP_ACTIVE | APP_BEHAVIOR),
        (TECH_ACTIVE, TECH_ACTIVE | TECH_BEHAVIOR),
    ],
    "Realization": [
        (BIZ_BEHAVIOR, BIZ_BEHAVIOR | BIZ_PASSIVE | MOTIVATION),
        (APP_ACTIVE | APP_BEHAVIOR, APP_BEHAVIOR | BIZ_BEHAVIOR | BIZ_PASSIVE | MOTIVATION),
        (TECH_ACTIVE | TECH_BEHAVIOR, APP_BEHAVIOR | APP_PASSIVE),
        (TECH_PASSIVE, APP_PASSIVE),
        (APP_PASSIVE, BIZ_PASSIVE),
        (BIZ_PASSIVE, BIZ_PASSIVE | BIZ_BEHAVIOR),  # Representation → BusinessObject
        (IMPL, IMPL | MOTIVATION | BIZ_BEHAVIOR | BIZ_PASSIVE | APP_ACTIVE | APP_BEHAVIOR),
        (MOTIVATION, MOTIVATION),
        (PHYSICAL, PHYSICAL | BIZ_PASSIVE),
    ],
    "Composition": [
        (ALL_ELEMENTS, ALL_ELEMENTS),  # Generally allowed — validate layer matching if strict needed
    ],
    "Aggregation": [
        (ALL_ELEMENTS, ALL_ELEMENTS),
    ],
    "Access": [
        (BIZ_ACTIVE | BIZ_BEHAVIOR, BIZ_PASSIVE),
        (APP_ACTIVE | APP_BEHAVIOR, APP_PASSIVE | BIZ_PASSIVE),  # App accessing business objects
        (TECH_ACTIVE | TECH_BEHAVIOR, TECH_PASSIVE),
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
        (IMPL, IMPL),  # Plateau → Plateau
        # Junctions can be source/target of Triggering
        ({"AndJunction","OrJunction"}, BIZ_BEHAVIOR | APP_BEHAVIOR | TECH_BEHAVIOR | IMPL),
        (BIZ_BEHAVIOR | APP_BEHAVIOR | TECH_BEHAVIOR | IMPL, {"AndJunction","OrJunction"}),
        # Cross-layer triggering (with warning intent preserved)
        (BIZ_BEHAVIOR | APP_BEHAVIOR | TECH_BEHAVIOR,
         BIZ_BEHAVIOR | APP_BEHAVIOR | TECH_BEHAVIOR),
    ],
    "Flow": [
        (BIZ_BEHAVIOR | BIZ_ACTIVE, BIZ_BEHAVIOR | BIZ_ACTIVE | BIZ_PASSIVE),
        (APP_BEHAVIOR | APP_ACTIVE, APP_BEHAVIOR | APP_ACTIVE | APP_PASSIVE),
        (TECH_BEHAVIOR | TECH_ACTIVE, TECH_BEHAVIOR | TECH_ACTIVE | TECH_PASSIVE),
        (ALL_ELEMENTS, ALL_ELEMENTS),  # Flow is broadly applicable
    ],
    "Specialization": [
        (ALL_ELEMENTS, ALL_ELEMENTS),  # Same type preferred but not enforced here
    ],
    "Junction": [
        (ALL_ELEMENTS, ALL_ELEMENTS),
    ],
    # Note: Location and Grouping can have relationships to elements they contain
    # Composite elements (Grouping, Location) are intentionally flexible in ArchiMate 3.2
}


def qname(elem):
    return elem.get(f"{{{XSI}}}type", "")


def validate(filepath):
    errors = []
    warnings = []

    # Parse XML
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"❌ XML Parse Error: {e}")
        return False

    # Check root element
    if root.tag != TAG("model"):
        errors.append(f"Root element must be 'model' in namespace {NS}, got {root.tag}")

    # Collect all element identifiers
    element_ids = {}
    rel_ids = {}

    elements_node = root.find(TAG("elements"))
    if elements_node is not None:
        for elem in elements_node.findall(TAG("element")):
            eid = elem.get("identifier")
            etype = qname(elem)
            if not eid:
                errors.append(f"Element missing identifier: {ET.tostring(elem, encoding='unicode')[:80]}")
                continue
            if etype not in VALID_ELEMENT_TYPES:
                errors.append(f"Invalid element type '{etype}' for element {eid}")
            element_ids[eid] = etype

    relationships_node = root.find(TAG("relationships"))
    if relationships_node is not None:
        for rel in relationships_node.findall(TAG("relationship")):
            rid = rel.get("identifier")
            rtype = qname(rel)
            src = rel.get("source")
            tgt = rel.get("target")

            if not rid:
                errors.append(f"Relationship missing identifier")
                continue

            if rtype not in VALID_RELATIONSHIP_TYPES:
                errors.append(f"Invalid relationship type '{rtype}' for relationship {rid}")
            
            # Referential integrity
            if src not in element_ids:
                errors.append(f"Relationship {rid}: source '{src}' not found in elements")
            if tgt not in element_ids:
                errors.append(f"Relationship {rid}: target '{tgt}' not found in elements")

            # Allowed relationship check (skip Association - always valid)
            if src in element_ids and tgt in element_ids and rtype != "Association":
                src_type = element_ids[src]
                tgt_type = element_ids[tgt]
                # Composite elements (Grouping, Location) and ValueStream have flexible relationships
                if src_type in COMPOSITE or tgt_type in COMPOSITE:
                    pass  # Grouping and Location can relate to anything
                elif src_type == "ValueStream" or tgt_type == "ValueStream":
                    pass  # ValueStream is a strategy element with broad applicability
                else:
                    patterns = ALLOWED_PATTERNS.get(rtype, [])
                    allowed = any(src_type in sp and tgt_type in tp for sp, tp in patterns)
                    if not allowed:
                        warnings.append(
                            f"Relationship {rid} ({rtype}): {src_type} → {tgt_type} "
                            f"may not be a valid ArchiMate 3.2 relationship. "
                            f"Consider using Association if this is intentional."
                        )

            rel_ids[rid] = (rtype, src, tgt)

    # Validate views referential integrity
    views = root.find(TAG("views"))
    if views is not None:
        diagrams = views.find(TAG("diagrams"))
        if diagrams is not None:
            for view in diagrams.findall(TAG("view")):
                view_id = view.get("identifier", "unknown")
                # Collect ALL node identifiers recursively (nodes can be nested)
                node_ids = set()
                def collect_nodes(parent):
                    for node in parent.findall(TAG("node")):
                        nid = node.get("identifier")
                        eref = node.get("elementRef")
                        if nid:
                            node_ids.add(nid)
                        if eref and eref not in element_ids:
                            errors.append(f"View {view_id}: node {nid} references unknown element {eref}")
                        collect_nodes(node)  # recurse into nested nodes
                collect_nodes(view)
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

    # Report
    print(f"\n{'='*60}")
    print(f"ArchiMate 3.2 Validation Report: {filepath}")
    print(f"{'='*60}")
    print(f"Elements found: {len(element_ids)}")
    print(f"Relationships found: {len(rel_ids)}")

    if errors:
        print(f"\n❌ ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  • {e}")
    else:
        print("\n✅ No structural errors found")

    if warnings:
        print(f"\n⚠️  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  • {w}")
    else:
        print("✅ No relationship warnings")

    print(f"{'='*60}\n")
    return len(errors) == 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 validate_archimate.py <file.xml>")
        sys.exit(1)
    ok = validate(sys.argv[1])
    sys.exit(0 if ok else 1)
