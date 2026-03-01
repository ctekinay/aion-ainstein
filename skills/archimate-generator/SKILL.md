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
    documentation: "<Optional description>"

relationships:
  - type: <ArchiMateRelationshipType>
    source: <element-id>
    target: <element-id>
    name: "<Optional verb label>"
```

**Strict rules:**

1. Output ONLY `model`, `elements`, and `relationships` — **NO views, NO XML, NO namespaces**
2. Every `type` in elements MUST be a valid ArchiMate 3.2 element type from `references/element-types.md`
3. Every `type` in relationships MUST be one of: `Composition`, `Aggregation`, `Assignment`, `Realization`, `Serving`, `Access`, `Influence`, `Association`, `Triggering`, `Flow`, `Specialization`
4. Every `source` and `target` in relationships MUST reference a valid element `id`
5. Relationships do NOT have an `id` field — identifiers are generated automatically
6. Do NOT include nested elements, property tags, or any XML-specific constructs
7. Wrap the entire output in ```yaml code fences
8. Do NOT include any text before or after the YAML code fence

**Example:**

```yaml
model:
  name: "User Authentication Service"

elements:
  - id: b1
    type: BusinessProcess
    name: "Login Process"
  - id: a1
    type: ApplicationComponent
    name: "Auth Service"
  - id: a2
    type: ApplicationInterface
    name: "Login API"
  - id: t1
    type: SystemSoftware
    name: "OAuth Provider"

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

## Known Limitations

### Model capability boundary

ArchiMate generation requires a model with strong structured output capabilities. Smaller local models (e.g., GPT-OSS:20B via Ollama) may refuse to generate YAML or fall back to textual descriptions instead. Cloud models (e.g., GPT-5.2 via OpenAI) handle this reliably.

**Recommendation:** Switch to a cloud model (e.g., GPT-5.2 via OpenAI) in the Chat UI settings before requesting ArchiMate generation. Standard KB queries (ADR/PCP/policy search, vocabulary lookups) work fine with local models.
