# ArchiMate 3.2 Open Exchange XML Template

This template is derived from the official Open Group ArchiMate 3.2 example file.
Every pattern shown here is confirmed to appear in that reference file.

---

## Complete Annotated Model Template

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  NAMESPACES: Copy these EXACTLY. The schemaLocation URLs are normative.
  - Primary namespace: http://www.opengroup.org/xsd/archimate/3.0/
  - XSD location points to archimate3_Diagram.xsd (covers model + diagrams)
  - Dublin Core (dc:) is optional metadata — include if you want rich metadata
-->
<model
  xmlns="http://www.opengroup.org/xsd/archimate/3.0/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="
    http://www.opengroup.org/xsd/archimate/3.0/
      http://www.opengroup.org/xsd/archimate/3.1/archimate3_Diagram.xsd
    http://purl.org/dc/elements/1.1/
      http://www.opengroup.org/xsd/archimate/3.1/dc.xsd"
  identifier="id-[UUID]">
  <!--
    identifier: must be globally unique. Use "id-" prefix + UUID4.
    Use Python: "id-" + str(uuid.uuid4())
  -->

  <!-- MODEL NAME: required. xml:lang is required. -->
  <name xml:lang="en">My Architecture Model</name>

  <!-- DOCUMENTATION: optional but recommended -->
  <documentation xml:lang="en">
    Description of the model, its scope and purpose.
  </documentation>

  <!-- METADATA: optional Dublin Core block -->
  <metadata>
    <schema>Dublin Core</schema>
    <schemaversion>1.1</schemaversion>
    <dc:title>My Architecture Model</dc:title>
    <dc:creator>Author Name</dc:creator>
    <dc:subject>Subject description</dc:subject>
    <dc:description>Model description</dc:description>
    <dc:date>2024-01-01</dc:date>
    <dc:format>The Open Group ArchiMate Exchange File Format V3.1</dc:format>
  </metadata>

  <!-- ============================================================
       ELEMENTS
       - Each element needs a unique identifier and xsi:type
       - name is required, documentation is optional
       - See element-types.md for all valid xsi:type values
       ============================================================ -->
  <elements>

    <!-- MOTIVATION LAYER -->
    <element identifier="id-[UUID]" xsi:type="Goal">
      <name xml:lang="en">Improve system reliability</name>
      <documentation xml:lang="en">Optional detailed description.</documentation>
    </element>

    <element identifier="id-[UUID]" xsi:type="Requirement">
      <name xml:lang="en">System must achieve 99.9% uptime</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="Principle">
      <name xml:lang="en">API-first design</name>
    </element>

    <!-- STRATEGY LAYER -->
    <element identifier="id-[UUID]" xsi:type="Capability">
      <name xml:lang="en">Order Management</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="ValueStream">
      <name xml:lang="en">Customer order fulfillment</name>
    </element>

    <!-- BUSINESS LAYER — Active Structure -->
    <element identifier="id-[UUID]" xsi:type="BusinessActor">
      <name xml:lang="en">Customer</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="BusinessRole">
      <name xml:lang="en">Order Manager</name>
    </element>

    <!-- BUSINESS LAYER — Behavior -->
    <element identifier="id-[UUID]" xsi:type="BusinessProcess">
      <name xml:lang="en">Process customer order</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="BusinessFunction">
      <name xml:lang="en">Customer relationship management</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="BusinessService">
      <name xml:lang="en">Order placement service</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="BusinessEvent">
      <name xml:lang="en">New customer order received</name>
    </element>

    <!-- BUSINESS LAYER — Passive Structure -->
    <element identifier="id-[UUID]" xsi:type="BusinessObject">
      <name xml:lang="en">Customer Order</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="Contract">
      <name xml:lang="en">Service Level Agreement</name>
    </element>

    <!-- APPLICATION LAYER — Active Structure -->
    <element identifier="id-[UUID]" xsi:type="ApplicationComponent">
      <name xml:lang="en">Order Management System</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="ApplicationInterface">
      <name xml:lang="en">Order REST API</name>
    </element>

    <!-- APPLICATION LAYER — Behavior -->
    <element identifier="id-[UUID]" xsi:type="ApplicationFunction">
      <name xml:lang="en">Validate order</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="ApplicationService">
      <name xml:lang="en">Order submission service</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="ApplicationEvent">
      <name xml:lang="en">Order submitted</name>
    </element>

    <!-- APPLICATION LAYER — Passive Structure -->
    <element identifier="id-[UUID]" xsi:type="DataObject">
      <name xml:lang="en">Order record</name>
    </element>

    <!-- TECHNOLOGY LAYER — Active Structure -->
    <element identifier="id-[UUID]" xsi:type="Node">
      <name xml:lang="en">Application server</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="Device">
      <name xml:lang="en">Database server</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="SystemSoftware">
      <name xml:lang="en">Kubernetes</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="CommunicationNetwork">
      <name xml:lang="en">Internal network</name>
    </element>

    <!-- TECHNOLOGY LAYER — Behavior -->
    <element identifier="id-[UUID]" xsi:type="TechnologyService">
      <name xml:lang="en">Container hosting service</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="TechnologyFunction">
      <name xml:lang="en">Container orchestration</name>
    </element>

    <!-- TECHNOLOGY LAYER — Passive Structure -->
    <element identifier="id-[UUID]" xsi:type="Artifact">
      <name xml:lang="en">order-service.jar</name>
    </element>

    <!-- IMPLEMENTATION & MIGRATION LAYER -->
    <element identifier="id-[UUID]" xsi:type="WorkPackage">
      <name xml:lang="en">Migrate to microservices</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="Deliverable">
      <name xml:lang="en">Deployed order service</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="Plateau">
      <name xml:lang="en">Phase 1: Core services</name>
    </element>

    <!-- COMPOSITE -->
    <element identifier="id-[UUID]" xsi:type="Grouping">
      <name xml:lang="en">Order domain</name>
    </element>

    <element identifier="id-[UUID]" xsi:type="Location">
      <name xml:lang="en">Amsterdam datacenter</name>
    </element>

  </elements>

  <!-- ============================================================
       RELATIONSHIPS
       - source and target must reference existing element identifiers
       - See allowed-relations.md for valid source→target per type
       - name is optional for relationships
       - Self-closing tag allowed when no children: <relationship ... />
       ============================================================ -->
  <relationships>

    <!-- COMPOSITION: strong ownership, child cannot exist without parent -->
    <relationship identifier="id-[UUID]"
      xsi:type="Composition"
      source="id-[parent]"
      target="id-[child]" />

    <!-- AGGREGATION: weaker containment, child can exist independently -->
    <relationship identifier="id-[UUID]"
      xsi:type="Aggregation"
      source="id-[parent]"
      target="id-[child]" />

    <!-- ASSIGNMENT: who performs what (actor→role or actor/role→behavior) -->
    <relationship identifier="id-[UUID]"
      xsi:type="Assignment"
      source="id-[BusinessRole]"
      target="id-[BusinessProcess]" />

    <!-- REALIZATION: lower layer realizes higher layer concept -->
    <relationship identifier="id-[UUID]"
      xsi:type="Realization"
      source="id-[ApplicationComponent]"
      target="id-[BusinessService]" />

    <!-- SERVING: B serves A (technology→application, application→business) -->
    <relationship identifier="id-[UUID]"
      xsi:type="Serving"
      source="id-[ApplicationService]"
      target="id-[BusinessProcess]" />

    <!-- ACCESS: active element accesses passive element
         accessType options: Read | Write | ReadWrite (omit for unspecified) -->
    <relationship identifier="id-[UUID]"
      xsi:type="Access"
      accessType="ReadWrite"
      source="id-[ApplicationFunction]"
      target="id-[DataObject]" />

    <!-- ACCESS without accessType (valid — means access direction unspecified) -->
    <relationship identifier="id-[UUID]"
      xsi:type="Access"
      source="id-[BusinessProcess]"
      target="id-[BusinessObject]" />

    <!-- INFLUENCE: motivation elements influencing each other or other elements
         modifier options: + (positive) | - (negative) | omit for neutral -->
    <relationship identifier="id-[UUID]"
      xsi:type="Influence"
      source="id-[Driver]"
      target="id-[Goal]" />

    <!-- ASSOCIATION: generic, always valid, can be directed or undirected -->
    <relationship identifier="id-[UUID]"
      xsi:type="Association"
      source="id-[elemA]"
      target="id-[elemB]" />

    <!-- ASSOCIATION: directed variant -->
    <relationship identifier="id-[UUID]"
      xsi:type="Association"
      isDirected="true"
      source="id-[elemA]"
      target="id-[elemB]" />

    <!-- TRIGGERING: sequential causation between behavior elements (same layer) -->
    <relationship identifier="id-[UUID]"
      xsi:type="Triggering"
      source="id-[BusinessEvent]"
      target="id-[BusinessProcess]" />

    <!-- FLOW: information or material flow, can have a name -->
    <relationship identifier="id-[UUID]"
      xsi:type="Flow"
      source="id-[BusinessFunction-A]"
      target="id-[BusinessFunction-B]">
      <name xml:lang="en">Shipping order</name>
    </relationship>

    <!-- SPECIALIZATION: subtype, source is specialization of target -->
    <relationship identifier="id-[UUID]"
      xsi:type="Specialization"
      source="id-[SpecificProcess]"
      target="id-[GenericProcess]" />

  </relationships>

  <!-- ============================================================
       VIEWS (DIAGRAMS) — optional but strongly recommended
       - Each view is a diagram showing a selection of elements/relations
       - Nodes reference elements via elementRef
       - Connections reference relationships via relationshipRef
       - Connections source/target reference NODE identifiers (not element ids)
       - Nodes can be nested (for grouping/container visual representation)
       - x, y, w, h are integer pixel coordinates
       ============================================================ -->
  <views>
    <diagrams>

      <!-- SIMPLE FLAT VIEW: all nodes at same level -->
      <view identifier="id-[UUID]" xsi:type="Diagram">
        <name xml:lang="en">Application Layer Overview</name>
        <documentation xml:lang="en">Shows main application components and their services.</documentation>

        <!-- NODE: visual representation of an element in this view
             x/y = top-left position, w/h = width/height in pixels
             Recommended sizes: elements 120x55, large containers 300x200 -->
        <node identifier="id-[nodeA]"
          elementRef="id-[ApplicationComponent]"
          xsi:type="Element"
          x="0" y="0" w="120" h="55">
          <style>
            <fillColor r="181" g="255" b="255" a="100"/>
            <lineColor r="0" g="0" b="0" a="100"/>
            <font name="Arial Narrow" size="12">
              <color r="0" g="0" b="0"/>
            </font>
          </style>
        </node>

        <node identifier="id-[nodeB]"
          elementRef="id-[ApplicationService]"
          xsi:type="Element"
          x="200" y="0" w="120" h="55">
          <style>
            <fillColor r="181" g="255" b="255" a="100"/>
            <lineColor r="0" g="0" b="0" a="100"/>
            <font name="Arial Narrow" size="12">
              <color r="0" g="0" b="0"/>
            </font>
          </style>
        </node>

        <node identifier="id-[nodeC]"
          elementRef="id-[BusinessProcess]"
          xsi:type="Element"
          x="400" y="0" w="120" h="55">
          <style>
            <fillColor r="255" g="255" b="181" a="100"/>
            <lineColor r="0" g="0" b="0" a="100"/>
            <font name="Arial Narrow" size="12">
              <color r="0" g="0" b="0"/>
            </font>
          </style>
        </node>

        <!-- CONNECTION: visual line between two nodes in this view
             source/target reference NODE identifiers (id-[nodeX]), NOT element ids
             relationshipRef references the relationship identifier from <relationships> -->
        <connection identifier="id-[connAB]"
          relationshipRef="id-[Serving-rel]"
          xsi:type="Relationship"
          source="id-[nodeA]"
          target="id-[nodeB]">
          <style>
            <lineColor r="0" g="0" b="0"/>
            <font name="Arial Narrow" size="12">
              <color r="0" g="0" b="0"/>
            </font>
          </style>
        </connection>

        <connection identifier="id-[connBC]"
          relationshipRef="id-[Serving-rel-2]"
          xsi:type="Relationship"
          source="id-[nodeB]"
          target="id-[nodeC]">
          <style>
            <lineColor r="0" g="0" b="0"/>
            <font name="Arial Narrow" size="12">
              <color r="0" g="0" b="0"/>
            </font>
          </style>
        </connection>

      </view>

      <!-- NESTED VIEW: nodes inside a parent node (container/grouping visual) -->
      <view identifier="id-[UUID]" xsi:type="Diagram">
        <name xml:lang="en">Technology Infrastructure</name>

        <!-- PARENT NODE: large container element -->
        <node identifier="id-[nodeParent]"
          elementRef="id-[Node]"
          xsi:type="Element"
          x="0" y="0" w="400" h="200">
          <style>
            <fillColor r="240" g="240" b="240" a="100"/>
            <lineColor r="0" g="0" b="0" a="100"/>
            <font name="Arial Narrow" size="12">
              <color r="0" g="0" b="0"/>
            </font>
          </style>

          <!-- CHILD NODE: nested inside parent node
               x/y coordinates are RELATIVE to parent node's top-left corner -->
          <node identifier="id-[nodeChild1]"
            elementRef="id-[SystemSoftware]"
            xsi:type="Element"
            x="20" y="60" w="120" h="55">
            <style>
              <fillColor r="201" g="231" b="183" a="100"/>
              <lineColor r="0" g="0" b="0" a="100"/>
              <font name="Arial Narrow" size="12">
                <color r="0" g="0" b="0"/>
              </font>
            </style>
          </node>

          <node identifier="id-[nodeChild2]"
            elementRef="id-[Artifact]"
            xsi:type="Element"
            x="200" y="60" w="120" h="55">
            <style>
              <fillColor r="201" g="231" b="183" a="100"/>
              <lineColor r="0" g="0" b="0" a="100"/>
              <font name="Arial Narrow" size="12">
                <color r="0" g="0" b="0"/>
              </font>
            </style>
          </node>

        </node>

        <!-- Connections still appear at view level, even if nodes are nested -->
        <connection identifier="id-[conn1]"
          relationshipRef="id-[Assignment-rel]"
          xsi:type="Relationship"
          source="id-[nodeChild1]"
          target="id-[nodeChild2]">
          <style>
            <lineColor r="0" g="0" b="0"/>
            <font name="Arial Narrow" size="12">
              <color r="0" g="0" b="0"/>
            </font>
          </style>
        </connection>

      </view>

    </diagrams>
  </views>

</model>
```

---

## Critical Syntax Notes

### The `<name>` closing tag
The `<name>` element uses the standard XML closing tag `</name>`:
```xml
<name xml:lang="en">My element name</name>
```

### Node coordinates in views
- Top-level nodes: `x`/`y` are absolute pixel coordinates from the view's top-left
- Nested child nodes: `x`/`y` are **relative** to the parent node's position
- Recommended default sizes: `w="120" h="55"` for elements, larger for containers

### Connection source/target vs elementRef
```xml
<!-- relationship references an element directly -->
<relationship identifier="id-rel1" xsi:type="Serving"
  source="id-elem1"   <!-- element identifier -->
  target="id-elem2"/> <!-- element identifier -->

<!-- connection in a view references NODES (not elements) -->
<connection identifier="id-conn1" relationshipRef="id-rel1" xsi:type="Relationship"
  source="id-node1"   <!-- node identifier in THIS view -->
  target="id-node2"/> <!-- node identifier in THIS view -->
```

### Style colors by layer (ArchiMate convention)
| Layer | Fill color (r,g,b) | Hex |
|---|---|---|
| Motivation | `204, 204, 255` (purple/lavender) | #CCCCFF |
| Strategy | `245, 222, 179` (wheat) | #F5DEB3 |
| Business | `255, 255, 181` (yellow) | #FFFFB5 |
| Application | `181, 255, 255` (cyan) | #B5FFFF |
| Technology | `201, 231, 183` (green) | #C9E7B7 |
| Physical | `201, 231, 183` (green) | #C9E7B7 |
| Implementation | `255, 181, 192` (pink) | #FFB5C0 |

---

## Minimal Valid File (no views, no metadata)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<model xmlns="http://www.opengroup.org/xsd/archimate/3.0/"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.1/archimate3_Diagram.xsd"
       identifier="id-[UUID]">
  <name xml:lang="en">Minimal Model</name>
  <elements>
    <element identifier="id-001" xsi:type="ApplicationComponent">
      <name xml:lang="en">Order Service</name>
    </element>
    <element identifier="id-002" xsi:type="ApplicationComponent">
      <name xml:lang="en">Payment Service</name>
    </element>
    <element identifier="id-003" xsi:type="DataObject">
      <name xml:lang="en">Order</name>
    </element>
  </elements>
  <relationships>
    <relationship identifier="id-rel-001" xsi:type="Serving"
      source="id-001" target="id-002" />
    <relationship identifier="id-rel-002" xsi:type="Access"
      accessType="ReadWrite" source="id-001" target="id-003" />
  </relationships>
</model>
```
