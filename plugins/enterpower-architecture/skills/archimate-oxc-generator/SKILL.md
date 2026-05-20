---
name: archimate-oxc-generator
description: "Generates valid ArchiMate 3.2 OXC (Open Exchange) XML models from text input such as code reviews, architecture descriptions, or project documentation. Use this skill whenever the user wants to create an ArchiMate model, generate an .xml exchange file, convert a description to ArchiMate, or export an architecture model in Open Exchange format."
---

**Usage**

- `/archimate-oxc-generator` — generate an ArchiMate 3.2 Open Exchange XML model from the provided input (ADRs, architecture descriptions, code reviews, project documents)

# ArchiMate 3.2 Open Exchange Generator

## When to use this skill

Use `archimate-oxc-generator` when the input is **text, documents, or analysis notes** and the goal is to produce a new ArchiMate model:
- "generate an ArchiMate model from this description / ADR / document"
- "convert this architecture description to ArchiMate"
- "create an ArchiMate model from this"
- Called by `repo-to-archimate` (Phase 2) with repo analysis notes as input

**Do NOT use for these — use a different skill instead:**
- "show me the model" / "visualize" → use `archimate-visual-composer` (browser display)
- "add a view to the model" → use `archimate-oxc-view-generator` (adds diagram to existing XML)
- "analyze this repo and generate ArchiMate" → use `repo-to-archimate` first (Phase 1), then this skill

**Authority note:** This is the authoritative skill for ArchiMate model generation conventions —
YAML schema, element types, ID rules, relationship rules, and documentation requirements. Other
skills that produce ArchiMate models (e.g., `repo-to-archimate`) delegate Phase 2 here.

## Overview

This skill generates valid ArchiMate 3.2 Open Exchange XML from unstructured input (code reviews,
architecture descriptions, project documents, or repo analysis summaries). You produce a
lightweight YAML definition of elements and relationships. A deterministic converter transforms
the YAML into valid XML with auto-generated views — you never write XML directly.

## Defaults

When generating a model, include all layers present in the source document and use the
extended view (implications, security considerations, constraints). Model all actors and
participants.

### Model Comprehensiveness

Always generate comprehensive models. For a single-document input (one ADR or PCP):
- **30–40 elements** across all relevant layers
- **40–60 relationships** connecting them
- Cover Motivation, Strategy, Business, Application, Technology, and Implementation layers
  when the source material warrants it

For multi-document input (e.g., PCP.10 through PCP.15), scale proportionally — each
document should contribute roughly 5–10 unique elements beyond shared infrastructure.

Do NOT generate minimal or abbreviated models. Every concept, constraint, implication,
actor, and technology mentioned in the source should have a corresponding element.

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

Consult `../../shared-references/archimate-shared/archim-3.2-element-types.md` for the complete list of valid `type` values per layer.

### Step 2: Identify Relationships

Map dependencies and interactions to valid ArchiMate relationships:

- **Structural**: `Composition`, `Aggregation`, `Assignment`, `Realization`
- **Dependency**: `Serving`, `Access`, `Influence`, `Association`
- **Dynamic**: `Triggering`, `Flow`
- **Other**: `Specialization`

Consult `../../shared-references/archimate-shared/archim-3.2-allowed-relations.md` for which relationships are allowed between which
element types. Key rules to remember:

- **Serving goes upward**: Technology serves Application, Application serves Business
- **Assignment binds active to behavior**: Actor → Process, Component → Function
- **Realization crosses layers upward**: lower layer realizes higher layer concepts. The REALIZING
  element (concrete) is always the SOURCE, the REALIZED element (abstract) is always the TARGET.
  Example: ApplicationComponent → Requirement, NEVER Requirement → ApplicationComponent
- **Access is only for passive objects**: processes access objects, not services
- **Triggering stays within same layer**: use Association or Flow for cross-layer
- **Association is always allowed** between any two elements (use as fallback)
- **Never invent documentation text**: only include a `documentation` field when the
  architecture notes explicitly contain a description or docstring for that component. If
  no description is available, omit the field entirely — do not guess from the name.
- **SystemSoftware cannot realize ApplicationComponent**: use `Serving` instead (e.g.
  "Python Runtime serves Agents Module"). `Realization` from `SystemSoftware` is only
  valid to `Requirement`.

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
2. Every `type` in elements MUST be a valid ArchiMate 3.2 element type from `../../shared-references/archimate-shared/archim-3.2-element-types.md`
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

## Source Reference

When an element directly represents a source document from the prompt (e.g., a
Principle element for PCP.10), include a `source_ref` field with the document
identifier:

```yaml
elements:
  - id: m1
    type: Principle
    name: "PCP.10 Eventual Consistency by Design"
    source_ref: PCP.10
    documentation: "Eventual consistency principle for distributed systems."
```

Rules:
- Only on elements that DIRECTLY represent a specific source document
- Most elements will NOT have source_ref — only the primary element for each
  source document should have one
- The pipeline automatically adds Dublin Core properties (`dct:identifier`,
  `dct:title`, `dct:creator`) using source_ref — do NOT generate `dct:*`
  properties yourself

## Properties (Optional)

Elements and relationships can include a `properties:` mapping for custom
metadata attributes. Dublin Core properties are added automatically by the
pipeline — do NOT generate them manually.

```yaml
elements:
  - id: m1
    type: Principle
    name: "PCP.10 Eventual Consistency"
    documentation: "Eventual consistency principle for distributed systems."
    properties:
      "custom:priority": "high"
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

---

## Element Reuse

The prompt may include a `KNOWN ELEMENTS` block listing elements from previous
generations. When your model includes an element that matches a known element
(same type and name), **reuse its ID exactly** instead of assigning a new one.

This ensures stable identity across generations — the same conceptual element
gets the same ID whether generated now or in a previous session.

Rules:
- Match by type AND name (case-insensitive)
- If a known element fits your model, use its `id` value as-is
- Only reuse elements that genuinely belong in your model — do not force-fit
- New elements that do not match any known element get fresh short IDs as usual
