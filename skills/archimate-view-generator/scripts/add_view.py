#!/usr/bin/env python3
"""
ArchiMate 3.2 View Generator
Adds a new view (diagram) to an existing ArchiMate Open Exchange XML file.

Usage:
    python3 add_view.py <input_model.xml> <view_fragment.xml> <output_model.xml>

Arguments:
    input_model.xml   - Existing valid ArchiMate Open Exchange file
    view_fragment.xml - XML file containing one or more <view> elements to add
                        Optionally also contains <elements> and <relationships> to append
    output_model.xml  - Output file path for the updated model

view_fragment.xml format:
    <fragment>
      <!-- Optional: new elements to add to the model -->
      <elements>
        <element identifier="id-xxx" xsi:type="ApplicationComponent">
          <name xml:lang="en">My Component</name>
        </element>
      </elements>
      <!-- Optional: new relationships to add to the model -->
      <relationships>
        <relationship identifier="id-yyy" xsi:type="Serving" source="id-xxx" target="id-zzz">
          <name xml:lang="en"></name>
        </relationship>
      </relationships>
      <!-- Required: one or more views to add -->
      <views>
        <view identifier="id-view-1" xsi:type="Diagram">
          <name xml:lang="en">My New View</name>
          <node identifier="id-node-1" elementRef="id-xxx" xsi:type="Element" x="20" y="20" w="120" h="55"/>
        </view>
      </views>
    </fragment>
"""

import sys
import xml.etree.ElementTree as ET

NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
TAG = lambda t: f"{{{NS}}}{t}"

ET.register_namespace("", NS)
ET.register_namespace("xsi", XSI_NS)


def load_xml(path):
    try:
        tree = ET.parse(path)
        return tree
    except ET.ParseError as e:
        print(f"❌ XML parse error in {path}: {e}")
        sys.exit(1)


def find_or_create(parent, tag):
    """Find child element by local tag name, create if missing."""
    child = parent.find(TAG(tag))
    if child is None:
        child = ET.SubElement(parent, tag)
    return child


def merge(input_path, fragment_path, output_path):
    model_tree = load_xml(input_path)
    fragment_tree = load_xml(fragment_path)

    model_root = model_tree.getroot()
    frag_root = fragment_tree.getroot()

    added_elements = 0
    added_relationships = 0
    added_views = 0

    # --- Append new elements (if any) ---
    frag_elements = frag_root.find("elements") or frag_root.find(TAG("elements"))
    if frag_elements is not None:
        model_elements = find_or_create(model_root, "elements")
        for elem in list(frag_elements):
            model_elements.append(elem)
            added_elements += 1

    # --- Append new relationships (if any) ---
    frag_rels = frag_root.find("relationships") or frag_root.find(TAG("relationships"))
    if frag_rels is not None:
        model_rels = find_or_create(model_root, "relationships")
        for rel in list(frag_rels):
            model_rels.append(rel)
            added_relationships += 1

    # --- Append new views ---
    frag_views_container = frag_root.find("views") or frag_root.find(TAG("views"))
    if frag_views_container is not None:
        model_views = find_or_create(model_root, "views")
        model_diagrams = find_or_create(model_views, "diagrams")
        for view in list(frag_views_container):
            model_diagrams.append(view)
            added_views += 1
    else:
        # Maybe views are direct children of fragment root
        for view in frag_root.findall("view") + frag_root.findall(TAG("view")):
            model_views = find_or_create(model_root, "views")
            model_diagrams = find_or_create(model_views, "diagrams")
            model_diagrams.append(view)
            added_views += 1

    # --- Write output ---
    model_tree.write(output_path, xml_declaration=True, encoding="UTF-8")

    print(f"\n{'='*60}")
    print(f"View Merge Summary")
    print(f"{'='*60}")
    print(f"  Input:              {input_path}")
    print(f"  Fragment:           {fragment_path}")
    print(f"  Output:             {output_path}")
    print(f"  Elements added:     {added_elements}")
    print(f"  Relationships added:{added_relationships}")
    print(f"  Views added:        {added_views}")
    print(f"{'='*60}")
    print(f"✅ Merge complete. Run validate_archimate.py on the output file.\n")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 add_view.py <input_model.xml> <view_fragment.xml> <output_model.xml>")
        sys.exit(1)
    merge(sys.argv[1], sys.argv[2], sys.argv[3])
