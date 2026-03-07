---
parent: Decisions
nav_order: ADR.NN
dct:
  identifier: urn:uuid:e5f6a7b8-c9d0-4e1f-2a3b-4c5d6e7f8a9b
  title: "Embed knowledge base identifiers in generated artifacts for provenance traceability"
  isVersionOf: proposed
  issued: 2026-03-06
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2026-03/NNNN-knowledge-base-traceability-in-generated-artifacts.html"
  versionInfo: "v1.0.0 (2026-03-06)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Embed knowledge base identifiers in generated artifacts for provenance traceability

## Context and Problem Statement

AI-assisted tooling in the ESA landscape generates structured artifacts (architecture
models, compliance reports, design documents) from knowledge base content — architecture
decisions (ADRs), design principles (PCPs), policies, and standards. Each source
document in the knowledge base has a stable, unique identifier (UUID) assigned by the
knowledge base system (e.g., Weaviate).

When a generated artifact represents or references a knowledge base document (e.g., an
ArchiMate Principle element derived from PCP.10), there is currently no standardized
way to trace the generated element back to its authoritative source. Without this
traceability:

- Architects cannot verify which source document a generated element represents.
- Automated tooling cannot cross-reference generated models with the knowledge base.
- When source documents are updated, there is no mechanism to identify which generated
  artifacts are affected.
- Multiple tools generating from the same knowledge base may use inconsistent
  identifiers, preventing cross-tool traceability.

How should generated artifacts maintain provenance links to their source documents in
the knowledge base?

## Decision Drivers

* Enable architects to trace any generated element back to its authoritative source
  document in the knowledge base.
* Use a W3C standard vocabulary for provenance metadata to ensure interoperability
  across tools and systems.
* Support automated impact analysis — when a source document changes, identify all
  generated artifacts that reference it.
* Ensure the traceability mechanism works across different artifact formats (XML,
  JSON, markdown) and different generation tools.
* Avoid requiring manual annotation — provenance links must be injected automatically
  during generation.

## Considered Options

1. **Dublin Core `dct:identifier` properties with knowledge base UUIDs** — Embed the
   source document's knowledge base UUID as a `dct:identifier` property on the
   generated element, using the Dublin Core metadata standard.

2. **Custom metadata comments** — Add XML/JSON comments containing source references
   (e.g., `<!-- Source: PCP.10, UUID: 78c31f45-... -->`).

3. **Separate provenance manifest** — Generate a companion file mapping generated
   element identifiers to source document identifiers.

4. **Element naming convention** — Encode source document identifiers in element
   names (e.g., "PCP.10 — Eventual Consistency by Design [78c31f45]").

## Decision Outcome

Chosen option: "Dublin Core `dct:identifier` properties with knowledge base UUIDs",
because Dublin Core is a W3C standard already used in the ESA ecosystem (ADR and PCP
documents use `dct:identifier` in their YAML frontmatter), the ArchiMate Open Exchange
Format natively supports custom properties through `<propertyDefinitions>`, and this
approach embeds traceability within the artifact itself — no external manifests or
naming conventions required.

The implementation pattern:

1. At generation time, extract the knowledge base UUID (`obj.uuid`) for each source
   document fetched from the knowledge base.
2. Include the UUID in the LLM prompt context as `KB UUID: urn:uuid:...`.
3. The LLM (or deterministic post-processing) adds a `dct:identifier` property to
   the corresponding generated element with the UUID value.
4. Define a `<propertyDefinition>` for `dct:identifier` in the artifact's property
   definitions section.

### Consequences

* Good, because Dublin Core `dct:identifier` is a W3C standard — any tool that
  understands Dublin Core metadata can interpret the provenance link.
* Good, because the traceability is embedded in the artifact itself — no external
  files to maintain or lose.
* Good, because the same `dct:identifier` vocabulary is already used in ADR and PCP
  YAML frontmatter, creating a consistent identifier chain from source document to
  generated artifact.
* Good, because the URN format (`urn:uuid:...`) is globally unique and
  resolution-independent — it doesn't depend on any specific API endpoint or URL
  scheme.
* Good, because automated tooling can query the knowledge base by UUID to retrieve
  the current version of the source document, enabling change impact analysis.
* Bad, because the knowledge base must provide stable UUIDs — if documents are
  re-ingested with new UUIDs, existing traceability links break.
* Bad, because the LLM must correctly associate the KB UUID from the prompt context
  with the right generated element — misassociation produces incorrect provenance.

### Confirmation

Compliance can be confirmed by verifying that:
1. Every generated element that represents a knowledge base document carries a
   `dct:identifier` property with a valid `urn:uuid:...` value.
2. The UUID in the `dct:identifier` property matches the UUID of the corresponding
   source document in the knowledge base.
3. The artifact's property definitions section includes a `<propertyDefinition>`
   for `dct:identifier`.
4. Provenance links are added automatically during generation — no manual annotation
   required.

## Pros and Cons of the Options

### Dublin Core `dct:identifier` properties with knowledge base UUIDs

Embed source UUIDs as `dct:identifier` properties using the Dublin Core standard.

* Good, because W3C standard — universally understood metadata vocabulary.
* Good, because embedded in the artifact — self-contained provenance.
* Good, because consistent with existing ESA document metadata (ADR/PCP frontmatter).
* Good, because supports the ArchiMate property mechanism natively.
* Neutral, because requires knowledge base UUID stability.
* Bad, because depends on LLM correctly associating UUIDs with elements during
  generation.

### Custom metadata comments

Add source references as XML/JSON comments in the generated artifact.

* Good, because simple to implement — just append comments.
* Bad, because comments are not part of the data model — tools may strip them
  during import/export.
* Bad, because not machine-queryable — requires custom parsing to extract
  provenance information.
* Bad, because no standard vocabulary — each tool invents its own comment format.

### Separate provenance manifest

Generate a companion file mapping element IDs to source document IDs.

* Good, because clear separation of concerns — the artifact is clean, provenance
  is in a dedicated file.
* Good, because the manifest can include additional metadata (generation timestamp,
  model version, confidence scores).
* Bad, because the manifest can become separated from the artifact — provenance is
  lost if the manifest file is not distributed with the artifact.
* Bad, because requires tooling to join the manifest with the artifact for
  traceability queries.
* Bad, because two files to manage instead of one.

### Element naming convention

Encode source identifiers in element names.

* Good, because immediately visible to humans reading element names.
* Bad, because pollutes element names with technical identifiers — "PCP.10 —
  Eventual Consistency by Design [78c31f45]" is not a natural element name.
* Bad, because fragile — downstream editing of element names breaks the
  traceability link.
* Bad, because not machine-queryable without string parsing.

## More Information

### Dublin Core in the ESA Ecosystem

The ESA document framework already uses Dublin Core metadata in YAML frontmatter:

```yaml
dct:
  identifier: urn:uuid:d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f8a
  title: "How to prioritize origins of standardizations"
  isVersionOf: accepted
  issued: 2025-07-17
```

This ADR extends the same vocabulary into generated artifacts, creating an unbroken
identifier chain:

```
Source document (ADR/PCP)         → dct:identifier in YAML frontmatter
Knowledge base object (Weaviate)  → obj.uuid (same UUID)
Generated model element           → dct:identifier property (same UUID)
```

### ArchiMate Property Mechanism

The ArchiMate Open Exchange Format supports custom properties through
`<propertyDefinitions>` and `<properties>`:

```xml
<propertyDefinitions>
  <propertyDefinition identifier="propdef-dct-identifier"
                      name="dct:identifier" type="string"/>
</propertyDefinitions>

<elements>
  <element identifier="id-xxx" xsi:type="Principle">
    <name xml:lang="en">Eventual Consistency by Design</name>
    <properties>
      <property propertyDefinitionRef="propdef-dct-identifier">
        <value xml:lang="en">urn:uuid:78c31f45-4ed7-4025-99d5-b29fa23b54a5</value>
      </property>
    </properties>
  </element>
</elements>
```

After import into a modeling tool, the `dct:identifier` property is visible in the
element's property sheet, providing direct traceability to the source document.

## References

- [Dublin Core Metadata Element Set — W3C](https://www.dublincore.org/specifications/dublin-core/dces/)
- [ADR.10: Prioritize the origins of standardizations](../../data/esa-main-artifacts/doc/decisions/0010-prioritize-the-origins-of-standardizations.md)
- [C3: ArchiMate Open Exchange XML as Interchange Format](C3-archimate-open-exchange-xml-as-interchange-format.md)
