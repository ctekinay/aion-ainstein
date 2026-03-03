---
name: archimate-view-generator
description: "Generates ArchiMate 3.2 views (diagrams) for existing models. Use this skill when the user wants to add a new view or diagram to an ArchiMate model, visualize a specific viewpoint, or create a focused diagram from a subset of model elements."
---

# ArchiMate 3.2 View Generator

## Overview

This skill generates ArchiMate 3.2 views (diagrams) that can be added to an existing model or
included in a new model. Views are visual arrangements of elements and connections that show a
specific perspective on the architecture.

Output is valid ArchiMate 3.2 Open Exchange XML — either a complete model with views, or a view
fragment the user can merge into their existing model.

## Workflow

### Step 1: Inspect the Existing Model

When the user provides an existing ArchiMate model (pasted XML or uploaded file content), call the
**`inspect_archimate_model`** tool with the XML string as input.

The tool returns a structured summary:
- All elements grouped by layer
- All relationships grouped by type
- Existing views (to avoid duplicating)
- Element index and relationship index for reference

Use this summary to understand what's in the model before generating a view. Do NOT ask the user
to manually list their elements — the tool does this automatically.

If the user describes their model verbally instead of providing XML, work from their description.

### Step 2: Determine the Viewpoint

Ask the user which viewpoint they want, or suggest one based on their goal. Standard viewpoints:

| Viewpoint | What it shows | Layers included |
|---|---|---|
| **Application Architecture** | Components, services, functions, data objects | Application |
| **Technology Infrastructure** | Nodes, devices, system software, artifacts | Technology |
| **Business Process** | Actors, roles, processes, objects, services | Business |
| **Motivation** | Stakeholders, drivers, goals, principles | Motivation |
| **Strategy** | Capabilities, resources, value streams | Strategy + Motivation |
| **Layered (Full Stack)** | All layers top to bottom | All present layers |
| **Information Structure** | Data objects, business objects, artifacts | Cross-layer (passive) |
| **Service Realization** | How services are realized by lower layers | Cross-layer |

### Step 3: Select Elements and Relationships

Based on the viewpoint and the inspection results, select which elements and relationships to include:

- **Single-layer views**: include all elements of that layer plus relationships between them
- **Cross-layer views**: include elements from relevant layers plus cross-layer relationships
- **Layered views**: include everything, organized by layer

Filter out elements that don't belong to the viewpoint. Not every element needs to appear in every view.

### Step 4: Calculate Layout

Apply layout rules from `references/view-layout.md`:

**Standard element dimensions:**
- Default: w="120" h="55"
- Wide (long names): w="160" h="55"
- Composite: w="160" h="70"

**Vertical layer stacking (Y position):**

| Layer | Y start |
|---|---|
| Motivation | 20 |
| Strategy | 100 |
| Business | 180 |
| Application | 260 |
| Technology | 340 |
| Physical | 420 |
| Implementation | 500 |

For single-layer views, start at y="20".

**Horizontal spacing:**
- Start at x="20"
- Gap between elements: 40px
- X increment: 160 (for default width 120 + gap 40)
- Wrap to new row after 5 elements (add y+80 for next row within same layer)

**Viewpoint-specific layout templates:**

Application Layer:
```
ApplicationComponent(s) at y=20
ApplicationService(s) at y=100
DataObject(s) at y=180
```

Technology Infrastructure:
```
Node / Device at y=20
SystemSoftware at y=100
Artifact(s) at y=180
```

Business Process:
```
BusinessActor / BusinessRole at y=20 (left)
BusinessProcess chain at y=20 (center, left to right)
BusinessObject(s) at y=100
BusinessService at y=180
```

Motivation:
```
Stakeholder at y=20 (left)
Driver at y=20 (right)
Assessment at y=100
Goal(s) at y=180
Principle / Requirement / Constraint at y=260
```

### Step 5: Generate the View XML

Generate the `<view>` element with properly positioned `<node>` and `<connection>` elements.

**Node structure:**
```xml
<node identifier="nv[view]-[elem]" elementRef="id-[elem]"
      xsi:type="Element" x="[x]" y="[y]" w="[w]" h="[h]"/>
```

**Connection structure:**
```xml
<connection identifier="cv[view]-r[n]" relationshipRef="id-r[n]"
            xsi:type="Relationship" source="nv[view]-[src]" target="nv[view]-[tgt]"/>
```

Critical rules:
- Node `identifier` must be unique and different from the element's identifier
- Connection `source` and `target` reference **node identifiers** in this view, not element identifiers
- Connection `relationshipRef` references the relationship identifier from `<relationships>`
- Only include connections for relationships where **both** source and target elements have nodes in this view

### Step 6: Merge or Present

**If the user provided an existing model:**

Call the **`merge_archimate_view`** tool with two inputs:
- `model_xml`: the original model XML string
- `fragment_xml`: the view fragment you generated, wrapped in a `<fragment>` root element:

```xml
<fragment>
  <!-- Optional: new elements needed for this view -->
  <elements>
    <element identifier="id-new1" xsi:type="ApplicationComponent">
      <name xml:lang="en">New Component</name>
    </element>
  </elements>
  <!-- Optional: new relationships -->
  <relationships>
    <relationship identifier="id-rnew1" xsi:type="Serving" source="id-new1" target="id-a1">
      <name xml:lang="en">serves</name>
    </relationship>
  </relationships>
  <!-- Required: the view(s) to add -->
  <views>
    <view identifier="id-v[n]" xsi:type="Diagram">
      <name xml:lang="en">[View Name]</name>
      <!-- nodes and connections here -->
    </view>
  </views>
</fragment>
```

The tool returns the complete merged model XML.

**If this is a standalone view (no existing model):**

Present just the view XML fragment. The user can insert it into their model manually.

### Step 7: Validate

Call the **`validate_archimate`** tool with the final XML (either the merged model or the standalone fragment).

**If errors:** Fix them in the XML, then call `validate_archimate` again. Repeat until `"valid": true`.

**If valid:** Present the output to the user.

Do NOT present XML to the user without calling `validate_archimate` first.

---

## Node Identifier Convention

```
Element identifier:   id-a1
View node identifier: nv1-a1  (view 1, element a1)
View connection id:   cv1-r5  (view 1, relationship r5)
```

Pattern: `nv[view-number]-[element-code]` for nodes, `cv[view-number]-r[relationship-number]` for connections.
