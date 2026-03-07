---
parent: Decisions
nav_order: ADR.NN
dct:
  identifier: urn:uuid:c3d4e5f6-a7b8-4c9d-0e1f-2a3b4c5d6e7f
  title: "Use ArchiMate Open Exchange XML as the standard interchange format for generated architecture models"
  isVersionOf: proposed
  issued: 2026-03-06
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2026-03/NNNN-archimate-open-exchange-xml-as-interchange-format.html"
  versionInfo: "v1.0.0 (2026-03-06)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Use ArchiMate Open Exchange XML as the standard interchange format for generated architecture models

## Context and Problem Statement

AI-assisted tooling in the ESA landscape generates architecture models from knowledge
base content — architecture decisions, design principles, policies, and standards.
These generated models must be importable into the modeling tools used by Energy System
Architects for review, refinement, and integration into the enterprise architecture
repository.

Multiple architects may use different modeling tools (Archi, BiZZdesign, MEGA HOPEX,
Sparx Enterprise Architect). If generated models are produced in a tool-specific format,
each tool requires a separate export path, increasing maintenance burden and risking
inconsistency.

What interchange format should generated architecture models use to ensure
tool-agnostic importability across the ESA tooling landscape?

## Decision Drivers

* Ensure generated models are importable by all ArchiMate-compliant modeling tools
  without tool-specific conversion.
* Use an open, internationally recognized standard governed by an independent body
  (consistent with ADR.10: prioritize international standards).
* Support the full ArchiMate metamodel — all element types, relationship types,
  properties, and views.
* Enable schema-based validation of generated models before import, catching
  structural errors deterministically.
* Support metadata and property definitions (Dublin Core, custom properties) for
  traceability and governance annotations.

## Considered Options

1. **ArchiMate Open Exchange XML** — The Open Group's standardized XML format for
   ArchiMate model interchange, defined by an XSD schema. Supported by all major
   ArchiMate tools.

2. **Tool-specific native formats** — Generate models in each tool's native format
   (e.g., Archi's `.archimate` SQLite database, BiZZdesign's proprietary format).

3. **JSON-based custom format** — Define a custom JSON schema for architecture models
   and require tools to implement importers.

4. **PlantUML or textual notation** — Generate architecture descriptions in a textual
   notation that can be rendered visually but requires manual modeling in the target
   tool.

## Decision Outcome

Chosen option: "ArchiMate Open Exchange XML", because it is the only standardized,
tool-agnostic format governed by The Open Group that supports the full ArchiMate
metamodel and is natively supported by all major modeling tools. It aligns with
ADR.10 (prioritize international standards) and enables deterministic schema
validation.

### Consequences

* Good, because any ArchiMate 3.x-compliant tool can import generated models
  directly — no tool-specific adapters needed.
* Good, because the XSD schema enables deterministic validation before import,
  catching structural errors without requiring the target tool.
* Good, because the format supports Dublin Core metadata and custom property
  definitions, enabling traceability annotations (see C5: KB Traceability).
* Good, because the format is governed by The Open Group and versioned independently
  of any tool vendor.
* Bad, because XML is verbose compared to JSON or binary formats, resulting in
  larger file sizes for complex models.
* Bad, because the XSD schema is strict — minor deviations (wrong element ordering,
  missing namespace declarations) cause import failures that are not always
  self-explanatory.

### Confirmation

Compliance can be confirmed by verifying that:
1. Generated models validate against the ArchiMate Open Exchange XSD schema
   without errors.
2. Generated models import successfully into at least two different ArchiMate tools
   (e.g., Archi and BiZZdesign).
3. All elements, relationships, properties, and views in the generated model are
   preserved after import (no data loss).

## Pros and Cons of the Options

### ArchiMate Open Exchange XML

Standardized XML format governed by The Open Group, with XSD schema for validation.

* Good, because natively supported by all major ArchiMate tools.
* Good, because XSD schema enables automated validation.
* Good, because supports the full ArchiMate metamodel including views and properties.
* Good, because governed by an independent standards body.
* Neutral, because the namespace URI uses `3.0` for all 3.x versions, which can
  cause confusion (Archi 5.7.0 validates all 3.x models against the `3.0` XSD).
* Bad, because XML verbosity increases file sizes.
* Bad, because strict schema requires exact element ordering (e.g.,
  `propertyDefinitions` must appear after `relationships`).

### Tool-specific native formats

Generate models in each tool's internal format.

* Good, because maximum fidelity with the target tool's features.
* Bad, because requires separate generation logic per tool.
* Bad, because proprietary formats may change without notice across tool versions.
* Bad, because locks the generation pipeline to specific tool vendors.

### JSON-based custom format

Custom JSON schema for architecture models.

* Good, because JSON is more compact and developer-friendly than XML.
* Good, because schema definition is flexible and can be tailored.
* Bad, because no existing tool supports it — requires custom importers for every
  modeling tool.
* Bad, because maintaining a custom format and its importers is a significant
  ongoing effort.
* Bad, because contradicts ADR.10 (prioritize international standards over custom).

### PlantUML or textual notation

Textual notation rendered as diagrams.

* Good, because human-readable and version-control friendly.
* Good, because lightweight — no XML parsing needed.
* Bad, because not importable into modeling tools as structured models.
* Bad, because loses the formal metamodel — elements and relationships become
  unstructured text.
* Bad, because no schema validation possible.

## More Information

### ArchiMate Open Exchange Format Versions

The ArchiMate Open Exchange Format uses `http://www.opengroup.org/xsd/archimate/3.0/`
as the namespace URI for all 3.x versions (3.0, 3.1, 3.2). This is a deliberate
design choice by The Open Group — the namespace identifies the format family, not
the specific language version. Archi 5.7.0 validates imports against the `3.0`
namespace XSD regardless of whether the model uses ArchiMate 3.2 language constructs.

### Schema Element Ordering

The XSD enforces a strict sequence for top-level elements within `<model>`:

```
name → documentation → metadata → elements → relationships →
organizations → propertyDefinitions → views
```

Deviating from this order (e.g., placing `propertyDefinitions` before `elements`)
causes schema validation failures.

### Property Structure

Elements and relationships may carry custom properties. The schema requires
`<property>` elements to be wrapped in a `<properties>` container:

```xml
<element identifier="id-xxx" xsi:type="Principle">
  <name xml:lang="en">Eventual Consistency by Design</name>
  <properties>
    <property propertyDefinitionRef="propdef-dct-identifier">
      <value xml:lang="en">urn:uuid:78c31f45-...</value>
    </property>
  </properties>
</element>
```

## References

- [ArchiMate 3.2 Specification — The Open Group](https://pubs.opengroup.org/architecture/archimate32-doc/)
- [ArchiMate Model Exchange File Format — The Open Group](https://www.opengroup.org/xsd/archimate/)
- [ADR.10: Prioritize the origins of standardizations](../../data/esa-main-artifacts/doc/decisions/0010-prioritize-the-origins-of-standardizations.md)
