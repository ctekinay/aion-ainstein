---
name: archimate-generator
description: "Generates valid ArchiMate 3.2 Open Exchange XML models from text input such as code reviews, architecture descriptions, or project documentation. Use this skill whenever the user wants to create an ArchiMate model, generate an .xml exchange file, convert a description to ArchiMate, or export an architecture model in Open Exchange format."
---

# ArchiMate 3.2 Open Exchange Generator

## Overview

This skill generates valid ArchiMate 3.2 Open Exchange XML from unstructured input (code reviews,
architecture descriptions, project documents). You produce a lightweight YAML definition of
elements and relationships. A deterministic converter transforms the YAML into valid XML with
auto-generated views — you never write XML directly.

## Defaults

When generating a model, include all layers present in the source document and use the
extended view (implications, security considerations, constraints). Model all actors and
participants.

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

Consult `references/element-types.md` for the complete list of valid `type` values per layer.

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

### Step 3: Generate YAML Output

Produce a YAML document following this exact schema:

```yaml
model:
  name: "<Model Name>"
  documentation: "<Optional model description>"

elements:
  - id: <short-code>
    type: <ArchiMateElementType>
    name: "<Element Name>"
    documentation: "<1-2 sentence description — required for every element>"
    properties:                              # Optional — only when user requests metadata
      "<property-key>": "<value>"

relationships:
  - type: <ArchiMateRelationshipType>
    source: <element-id>
    target: <element-id>
    name: "<Optional verb label>"
    properties:                              # Optional
      "<property-key>": "<value>"
```

**Strict rules:**

1. Output ONLY `model`, `elements`, and `relationships` — **NO views, NO XML, NO namespaces**
2. Every `type` in elements MUST be a valid ArchiMate 3.2 element type from `references/element-types.md`
3. Every `type` in relationships MUST be one of: `Composition`, `Aggregation`, `Assignment`, `Realization`, `Serving`, `Access`, `Influence`, `Association`, `Triggering`, `Flow`, `Specialization`
4. Every `source` and `target` in relationships MUST reference a valid element `id`
5. Relationships do NOT have an `id` field — identifiers are generated automatically
6. Every element MUST include a `documentation` field with a 1-2 sentence description
7. Do NOT include nested elements or any XML-specific constructs. The `properties` field is supported (see schema above) — only include it when the user explicitly requests metadata fields
8. Wrap the entire output in ```yaml code fences
9. Do NOT include any text before or after the YAML code fence

**Example:**

```yaml
model:
  name: "User Authentication Service"

elements:
  - id: b1
    type: BusinessProcess
    name: "Login Process"
    documentation: "End-to-end user authentication flow including credential validation and session creation."
  - id: a1
    type: ApplicationComponent
    name: "Auth Service"
    documentation: "Central authentication service handling login, token issuance, and session management."
  - id: a2
    type: ApplicationInterface
    name: "Login API"
    documentation: "REST API endpoint accepting credentials and returning authentication tokens."
  - id: t1
    type: SystemSoftware
    name: "OAuth Provider"
    documentation: "Third-party OAuth 2.0 identity provider used for federated authentication."

relationships:
  - type: Serving
    source: a1
    target: b1
    name: "authenticates"
  - type: Composition
    source: a1
    target: a2
  - type: Serving
    source: t1
    target: a1
    name: "provides tokens"
```

---

## Properties (Optional)

Elements and relationships can include a `properties:` mapping for metadata fields like
Dublin Core (`dct:*`) or custom attributes. Only include properties when the user explicitly
requests them.

```yaml
elements:
  - id: m1
    type: Principle
    name: "PCP.10 Eventual Consistency"
    documentation: "Eventual consistency principle for distributed systems."
    properties:
      "dct:identifier": "urn:uuid:abc123"
      "dct:language": "en"
      "dct:type": "archi:Principle"
```

The converter transforms these into standard ArchiMate `<property>` and
`<propertyDefinitions>` XML elements that tools like Archi can read.

---

## ID Convention

Use short, readable identifiers with layer-prefix codes:

- Motivation: `m1`, `m2`, ...
- Strategy: `s1`, `s2`, ...
- Business: `b1`, `b2`, ...
- Application: `a1`, `a2`, ...
- Technology: `t1`, `t2`, ...
- Physical: `p1`, `p2`, ...
- Implementation: `i1`, `i2`, ...

The converter automatically adds the `id-` prefix and generates all XML identifiers,
view nodes, and connections. You only need to define elements and relationships.
