#!/usr/bin/env python3
"""
ArchiMate 3.2 Model Inspector
Parses an existing Open Exchange XML file and prints a structured summary of:
- Elements per layer
- Relationships per type
- Existing views

Usage:
    python3 inspect_model.py <model.xml>

Output is used to understand the existing model before generating a new view.
"""

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
TAG = lambda t: f"{{{NS}}}{t}"

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

LAYER_ORDER = ["Motivation", "Strategy", "Business", "Application",
               "Technology", "Physical", "Implementation", "Composite"]


def get_name(elem):
    name_el = elem.find(TAG("name"))
    if name_el is not None and name_el.text:
        return name_el.text.strip()
    return "(unnamed)"


def get_type(elem):
    return elem.get(f"{{{XSI_NS}}}type", "Unknown")


def inspect(filepath):
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"❌ XML Parse Error: {e}")
        sys.exit(1)

    model_name = get_name(root)
    model_id = root.get("identifier", "?")

    elements = {}
    rels = {}
    by_layer = defaultdict(list)

    elements_node = root.find(TAG("elements"))
    if elements_node is not None:
        for elem in elements_node.findall(TAG("element")):
            eid = elem.get("identifier")
            etype = get_type(elem)
            ename = get_name(elem)
            elements[eid] = {"type": etype, "name": ename}
            layer = LAYER_MAP.get(etype, "Unknown")
            by_layer[layer].append({"id": eid, "type": etype, "name": ename})

    rels_node = root.find(TAG("relationships"))
    if rels_node is not None:
        by_rel_type = defaultdict(int)
        for rel in rels_node.findall(TAG("relationship")):
            rid = rel.get("identifier")
            rtype = get_type(rel)
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
                vname = get_name(view)
                node_count = len(list(view.findall(TAG("node"))))
                conn_count = len(list(view.findall(TAG("connection"))))
                existing_views.append({
                    "id": vid, "name": vname,
                    "nodes": node_count, "connections": conn_count
                })

    # --- Print report ---
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"ArchiMate Model Inspector: {filepath}")
    print(sep)
    print(f"Model name : {model_name}")
    print(f"Model ID   : {model_id}")
    print(f"Elements   : {len(elements)}")
    print(f"Relations  : {len(rels)}")
    print(f"Views      : {len(existing_views)}")

    print(f"\n{'-'*60}")
    print("ELEMENTS BY LAYER:")
    for layer in LAYER_ORDER:
        items = by_layer.get(layer, [])
        if items:
            print(f"\n  [{layer} Layer] ({len(items)} elements)")
            for item in items:
                print(f"    - {item['name']} ({item['type']}) [{item['id']}]")

    print(f"\n{'-'*60}")
    print("RELATIONSHIPS BY TYPE:")
    if rels:
        for rtype, count in sorted(by_rel_type.items()):
            print(f"  {rtype}: {count}")
    else:
        print("  (none)")

    print(f"\n{'-'*60}")
    print("EXISTING VIEWS:")
    if existing_views:
        for v in existing_views:
            print(f"  - \"{v['name']}\" [{v['id']}]  ({v['nodes']} nodes, {v['connections']} connections)")
    else:
        print("  (none)")

    print(f"\n{sep}\n")

    # Machine-readable element list for view generation
    print("ELEMENT INDEX (for view generation):")
    for eid, edata in elements.items():
        layer = LAYER_MAP.get(edata["type"], "Unknown")
        print(f"  {eid} | {edata['type']} | {layer} | {edata['name']}")

    print(f"\nRELATIONSHIP INDEX (for view generation):")
    for rid, rdata in rels.items():
        src_name = elements.get(rdata["source"], {}).get("name", "?")
        tgt_name = elements.get(rdata["target"], {}).get("name", "?")
        print(f"  {rid} | {rdata['type']} | {rdata['source']} ({src_name}) → {rdata['target']} ({tgt_name})")

    print(f"\n{sep}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 inspect_model.py <model.xml>")
        sys.exit(1)
    inspect(sys.argv[1])
