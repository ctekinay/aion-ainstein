#!/usr/bin/env python3
"""Visual inspection of Sugiyama layout output.

Generates several ArchiMate models, converts them to XML, and prints
the view node coordinates for manual inspection. Also writes the XML
files so they can be opened in Archi.
"""

import os
import sys
import xml.etree.ElementTree as ET

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.aion.tools.yaml_to_xml import yaml_to_archimate_xml

NS = "http://www.opengroup.org/xsd/archimate/3.0/"


def extract_view_nodes(xml_str: str) -> list[dict]:
    """Extract node positions from generated XML."""
    root = ET.fromstring(xml_str)
    nodes = []
    for node in root.iter(f"{{{NS}}}node"):
        elem_ref = node.get("elementRef", "")
        x = int(node.get("x", 0))
        y = int(node.get("y", 0))
        w = int(node.get("w", 0))
        h = int(node.get("h", 0))
        nodes.append({"ref": elem_ref, "x": x, "y": y, "w": w, "h": h})
    return nodes


def check_overlaps(nodes: list[dict]) -> list[str]:
    """Check for overlapping bounding boxes."""
    issues = []
    for i, a in enumerate(nodes):
        for j, b in enumerate(nodes):
            if j <= i:
                continue
            if (a["x"] < b["x"] + b["w"] and a["x"] + a["w"] > b["x"] and
                    a["y"] < b["y"] + b["h"] and a["y"] + a["h"] > b["y"]):
                issues.append(f"  OVERLAP: {a['ref']} ({a['x']},{a['y']}) vs {b['ref']} ({b['x']},{b['y']})")
    return issues


def test_model(name: str, yaml_str: str, out_dir: str):
    """Generate model and print layout analysis."""
    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"{'='*70}")
    try:
        xml_str, info = yaml_to_archimate_xml(yaml_str)
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    print(f"  Elements: {info['element_count']}, Relationships: {info['relationship_count']}")

    nodes = extract_view_nodes(xml_str)
    print(f"  View nodes: {len(nodes)}")
    print()

    # Group by Y position (approximate layer)
    by_y = {}
    for n in nodes:
        by_y.setdefault(n["y"], []).append(n)

    for y in sorted(by_y.keys()):
        row_nodes = sorted(by_y[y], key=lambda n: n["x"])
        labels = [f"{n['ref'].replace('id-','')}({n['w']}x{n['h']} @{n['x']},{n['y']})" for n in row_nodes]
        print(f"  Y={y:4d}: {', '.join(labels)}")

    # Check overlaps
    overlaps = check_overlaps(nodes)
    if overlaps:
        print(f"\n  *** OVERLAPS DETECTED ***")
        for o in overlaps:
            print(o)
    else:
        print(f"\n  No overlaps detected.")

    # Bounding box
    if nodes:
        max_x = max(n["x"] + n["w"] for n in nodes)
        max_y = max(n["y"] + n["h"] for n in nodes)
        print(f"  Bounding box: {max_x} x {max_y} px")

    # Write XML
    out_path = os.path.join(out_dir, f"{name.lower().replace(' ', '_')}.xml")
    with open(out_path, "w") as f:
        f.write(xml_str)
    print(f"  Written to: {out_path}")


# ── Test Models ──────────────────────────────────────────────────────────────

MODEL_3LAYER = """\
model:
  name: "Three-Layer Architecture"

elements:
  - id: ba1
    type: BusinessActor
    name: "Customer"
  - id: bp1
    type: BusinessProcess
    name: "Order Processing"
  - id: bs1
    type: BusinessService
    name: "Order Service"
  - id: ac1
    type: ApplicationComponent
    name: "Order System"
  - id: af1
    type: ApplicationFunction
    name: "Process Order"
  - id: as1
    type: ApplicationService
    name: "Order API"
  - id: n1
    type: Node
    name: "App Server"
  - id: ss1
    type: SystemSoftware
    name: "PostgreSQL"
  - id: art1
    type: Artifact
    name: "order-service.jar"

relationships:
  - type: Assignment
    source: ba1
    target: bp1
  - type: Serving
    source: bs1
    target: ba1
  - type: Realization
    source: bp1
    target: bs1
  - type: Assignment
    source: ac1
    target: af1
  - type: Serving
    source: as1
    target: bp1
  - type: Realization
    source: af1
    target: as1
  - type: Assignment
    source: n1
    target: ss1
  - type: Serving
    source: ss1
    target: ac1
  - type: Realization
    source: art1
    target: ac1
"""

MODEL_IEC62443 = """\
model:
  name: "IEC 62443 Security Zone Model"

elements:
  - id: sz1
    type: Grouping
    name: "Production Zone A"
  - id: sz2
    type: Grouping
    name: "DMZ Zone"
  - id: cond1
    type: Path
    name: "Zone A to DMZ Conduit"
  - id: dev1
    type: Device
    name: "PLC Controller"
  - id: dev2
    type: Device
    name: "HMI Workstation"
  - id: sw1
    type: SystemSoftware
    name: "SCADA Server"
  - id: net1
    type: CommunicationNetwork
    name: "OT Network"
  - id: fw1
    type: Node
    name: "Industrial Firewall"
  - id: g1
    type: Goal
    name: "FR1 - Access Control"
  - id: g2
    type: Goal
    name: "FR2 - Use Control"
  - id: req1
    type: Requirement
    name: "SR 1.1 Human User ID"
  - id: req2
    type: Requirement
    name: "SR 2.1 Authorization Enforcement"
  - id: threat1
    type: Assessment
    name: "Unauthorized Access Threat"

relationships:
  - type: Composition
    source: sz1
    target: dev1
  - type: Composition
    source: sz1
    target: dev2
  - type: Assignment
    source: dev2
    target: sw1
  - type: Serving
    source: net1
    target: dev1
  - type: Serving
    source: net1
    target: dev2
  - type: Association
    source: cond1
    target: sz1
  - type: Association
    source: cond1
    target: sz2
  - type: Composition
    source: sz2
    target: fw1
  - type: Realization
    source: req1
    target: g1
  - type: Realization
    source: req2
    target: g2
  - type: Influence
    source: threat1
    target: g1
"""

MODEL_WIDE_NAMES = """\
model:
  name: "Long Name Stress Test"

elements:
  - id: e1
    type: ApplicationComponent
    name: "Authentication Service"
  - id: e2
    type: ApplicationComponent
    name: "API"
  - id: e3
    type: ApplicationComponent
    name: "Enterprise Service Bus Integration Layer"
  - id: e4
    type: ApplicationFunction
    name: "Validate User Credentials Against LDAP"
  - id: e5
    type: DataObject
    name: "User Profile Data Transfer Object"
  - id: e6
    type: BusinessProcess
    name: "Customer Onboarding and Verification"
  - id: e7
    type: BusinessService
    name: "Identity Verification"

relationships:
  - type: Assignment
    source: e1
    target: e4
  - type: Access
    source: e4
    target: e5
  - type: Serving
    source: e7
    target: e6
  - type: Realization
    source: e4
    target: e7
"""

MODEL_MANY_ELEMENTS = """\
model:
  name: "Large Model (14 elements)"

elements:
  - id: ba1
    type: BusinessActor
    name: "Operator"
  - id: ba2
    type: BusinessActor
    name: "Manager"
  - id: br1
    type: BusinessRole
    name: "Grid Operator"
  - id: bp1
    type: BusinessProcess
    name: "Monitor Grid"
  - id: bp2
    type: BusinessProcess
    name: "Dispatch Crew"
  - id: bp3
    type: BusinessProcess
    name: "Report Outage"
  - id: ac1
    type: ApplicationComponent
    name: "SCADA System"
  - id: ac2
    type: ApplicationComponent
    name: "OMS Platform"
  - id: ac3
    type: ApplicationComponent
    name: "GIS Application"
  - id: af1
    type: ApplicationFunction
    name: "Real-time Monitoring"
  - id: af2
    type: ApplicationFunction
    name: "Outage Management"
  - id: n1
    type: Node
    name: "Control Center Server"
  - id: n2
    type: Node
    name: "Field Gateway"
  - id: ss1
    type: SystemSoftware
    name: "RHEL 9"

relationships:
  - type: Assignment
    source: ba1
    target: br1
  - type: Assignment
    source: br1
    target: bp1
  - type: Assignment
    source: ba2
    target: bp2
  - type: Triggering
    source: bp1
    target: bp3
  - type: Triggering
    source: bp3
    target: bp2
  - type: Assignment
    source: ac1
    target: af1
  - type: Assignment
    source: ac2
    target: af2
  - type: Serving
    source: af1
    target: bp1
  - type: Serving
    source: af2
    target: bp2
  - type: Flow
    source: ac1
    target: ac2
  - type: Assignment
    source: n1
    target: ss1
  - type: Serving
    source: ss1
    target: ac1
  - type: Serving
    source: n2
    target: ac3
"""

MODEL_SINGLE_LAYER = """\
model:
  name: "Single Layer (Application Only)"

elements:
  - id: ac1
    type: ApplicationComponent
    name: "Frontend"
  - id: ac2
    type: ApplicationComponent
    name: "Backend"
  - id: ac3
    type: ApplicationComponent
    name: "Database"
  - id: af1
    type: ApplicationFunction
    name: "User Auth"

relationships:
  - type: Serving
    source: ac2
    target: ac1
  - type: Serving
    source: ac3
    target: ac2
  - type: Assignment
    source: ac2
    target: af1
"""

MODEL_DISCONNECTED = """\
model:
  name: "Disconnected Components"

elements:
  - id: bp1
    type: BusinessProcess
    name: "Sales"
  - id: bp2
    type: BusinessProcess
    name: "Billing"
  - id: ac1
    type: ApplicationComponent
    name: "CRM"
  - id: ac2
    type: ApplicationComponent
    name: "ERP"
  - id: n1
    type: Node
    name: "Server A"
  - id: n2
    type: Node
    name: "Server B"

relationships:
  - type: Serving
    source: ac1
    target: bp1
  - type: Serving
    source: ac2
    target: bp2
"""


if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sugiyama_output")
    os.makedirs(out_dir, exist_ok=True)

    test_model("Three-Layer Architecture", MODEL_3LAYER, out_dir)
    test_model("IEC 62443 Security Zones", MODEL_IEC62443, out_dir)
    test_model("Wide Names Stress Test", MODEL_WIDE_NAMES, out_dir)
    test_model("Large Model (14 elements)", MODEL_MANY_ELEMENTS, out_dir)
    test_model("Single Layer", MODEL_SINGLE_LAYER, out_dir)
    test_model("Disconnected Components", MODEL_DISCONNECTED, out_dir)

    print(f"\n\nAll XML files written to: {out_dir}")
