---
name: archimate-generator
description: "Generates valid ArchiMate 3.2 Open Exchange XML models from text input such as code reviews, architecture descriptions, or project documentation. Use this skill whenever the user wants to create an ArchiMate model, generate an .xml exchange file, convert a description to ArchiMate, or export an architecture model in Open Exchange format."
---

# ArchiMate 3.2 Open Exchange Generator

## Overview

This skill generates valid ArchiMate 3.2 Open Exchange XML from unstructured input (code reviews,
architecture descriptions, project documents). The generated XML conforms to the ArchiMate 3.2
Open Exchange specification and can be imported into any ArchiMate-compliant tool (Archi, BiZZdesign,
MEGA, etc.).

## Workflow

### Step 1: Parse Input and Classify Elements

Read the user's input and identify architectural concerns. Map them to ArchiMate layers:

- **Motivation**: Goals, drivers, requirements, constraints, principles, stakeholders
- **Strategy**: Capabilities, courses of action, value streams, resources
- **Business**: Actors, roles, processes, functions, services, events, objects, contracts
- **Application**: Components, services, functions, interfaces, data objects
- **Technology**: Nodes, devices, system software, networks, artifacts, paths
- **Physical**: Equipment, facilities, distribution networks, materials
- **Implementation**: Work packages, deliverables, implementation events, gaps, plateaus

Consult `references/element-types.md` for the complete list of valid `xsi:type` values per layer.

### Step 2: Identify Relationships

Map dependencies and interactions to valid ArchiMate relationships:

- **Structural**: `Composition`, `Aggregation`, `Assignment`, `Realization`
- **Dependency**: `Serving`, `Access`, `Influence`, `Association`
- **Dynamic**: `Triggering`, `Flow`
- **Other**: `Specialization`

Consult `references/allowed-relations.md` for which relationships are allowed between which
element types. Key rules to remember:

- **Serving goes upward**: Technology serves Application, Application serves Business
- **Assignment binds active to behavior**: Actor → Process, Component → Function
- **Realization crosses layers upward**: lower layer realizes higher layer concepts
- **Access is only for passive objects**: processes access objects, not services
- **Triggering stays within same layer**: use Association or Flow for cross-layer
- **Association is always allowed** between any two elements (use as fallback)

### Step 3: Generate the XML

Produce a complete ArchiMate 3.2 Open Exchange XML document.

**Critical XML rules:**

1. Root element `<model>` with namespace `http://www.opengroup.org/xsd/archimate/3.0/`
2. Schema location: `http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.1/archimate3_Diagram.xsd`
3. Every `identifier` attribute must be unique (use `id-` prefix + short code, e.g. `id-a1`, `id-r12`, `id-v1`)
4. `<name xml:lang="en">` required for every element, relationship, and view
5. Only use `xsi:type` values from the approved lists in `references/element-types.md`
6. Relationships need `source` and `target` referencing valid element identifiers
7. Views reference elements via `elementRef` on `<node>` and relationships via `relationshipRef` on `<connection>`
8. Node identifiers in views must be different from element identifiers (use prefix like `nv1-`)
9. Connection `source` and `target` reference **node identifiers** (not element identifiers)

**XML structure:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<model xmlns="http://www.opengroup.org/xsd/archimate/3.0/"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.1/archimate3_Diagram.xsd"
       identifier="id-model-001">
  <name xml:lang="en">[Model Name]</name>
  <documentation xml:lang="en">[Model description]</documentation>

  <elements>
    <element identifier="id-[code]" xsi:type="[ElementType]">
      <name xml:lang="en">[Name]</name>
      <documentation xml:lang="en">[Description]</documentation>
    </element>
  </elements>

  <relationships>
    <relationship identifier="id-r[n]" xsi:type="[RelType]"
                  source="id-[src]" target="id-[tgt]">
      <name xml:lang="en">[verb label]</name>
    </relationship>
  </relationships>

  <views>
    <diagrams>
      <view identifier="id-v[n]" xsi:type="Diagram">
        <name xml:lang="en">[View Name]</name>
        <node identifier="nv[n]-[code]" elementRef="id-[code]"
              xsi:type="Element" x="20" y="20" w="120" h="55"/>
        <connection identifier="cv[n]-r[n]" relationshipRef="id-r[n]"
                    xsi:type="Relationship" source="nv[n]-[src]" target="nv[n]-[tgt]"/>
      </view>
    </diagrams>
  </views>
</model>
```

### Step 4: Validate with Tool

After generating the XML, call the **`validate_archimate`** tool with the complete XML string as input.

The tool checks:
1. Well-formed XML structure
2. Valid element `xsi:type` values
3. Valid relationship `xsi:type` values
4. Allowed source→target combinations per relationship type
5. Referential integrity (all identifiers resolve correctly)
6. View node and connection integrity

**If the tool returns errors:** Fix every reported error in the XML, then call `validate_archimate` again. Repeat until `"valid": true`.

**If the tool returns only warnings:** Present the XML to the user with a note about the warnings. Warnings indicate relationships that may be unusual but are not strictly invalid.

Do NOT present XML to the user without calling `validate_archimate` first.

### Step 5: Present Output

Present the validated XML in the chat response. Inform the user they can:
- Save it as a `.xml` file
- Import it into Archi (File → Import → Open Exchange XML)
- Import it into any ArchiMate 3.2-compliant tool

---

## Quick Reference: Code Review → ArchiMate Mapping

| Code Review Finding | ArchiMate Element |
|---|---|
| Microservice / service | `ApplicationComponent` |
| API / interface | `ApplicationInterface` |
| Database | `DataObject` (app layer) or `Artifact` (tech layer) |
| Message queue | `ApplicationComponent` + `Flow` |
| Frontend app | `ApplicationComponent` |
| User / actor | `BusinessActor` or `BusinessRole` |
| Business process | `BusinessProcess` |
| Infrastructure node | `Node` or `Device` |
| Docker / K8s | `SystemSoftware` |
| Network | `CommunicationNetwork` |
| Library / module | `ApplicationComponent` |
| Use case | `ApplicationFunction` or `BusinessFunction` |
| Deployment | `Artifact` assigned to `Node` |
| Dependency call | `Serving` or `Access` |
| Trigger / event | `ApplicationEvent` or `BusinessEvent` |
| Data flow | `Flow` |

---

## ID Convention

Use short, readable identifiers with layer-prefix codes:

- Motivation: `id-m1`, `id-m2`, ...
- Strategy: `id-s1`, `id-s2`, ...
- Business: `id-b1`, `id-b2`, ...
- Application: `id-a1`, `id-a2`, ...
- Technology: `id-t1`, `id-t2`, ...
- Physical: `id-p1`, `id-p2`, ...
- Implementation: `id-i1`, `id-i2`, ...
- Relationships: `id-r1`, `id-r2`, ...
- Views: `id-v1`, `id-v2`, ...
- View nodes: `nv1-m1`, `nv1-a3`, ... (view number + element code)
- View connections: `cv1-r1`, `cv1-r2`, ... (view number + relationship code)

---

## Known Limitations

### Model capability boundary

ArchiMate XML generation requires a model with strong structured output capabilities. Smaller local models (e.g., GPT-OSS:20B via Ollama) may refuse to generate XML or fall back to textual descriptions instead. Cloud models (e.g., GPT-5.2 via OpenAI) handle this reliably — the same prompts that fail locally produce valid, self-correcting XML with cloud models.

**Recommendation:** Switch to a cloud model (e.g., GPT-5.2 via OpenAI) in the Chat UI settings before requesting ArchiMate generation. Standard KB queries (ADR/PCP/policy search, vocabulary lookups) work fine with local models.
