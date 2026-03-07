---
parent: Decisions
nav_order: ADR.NN
dct:
  identifier: urn:uuid:d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f8a
  title: "Separate LLM generation from deterministic validation and repair in artifact pipelines"
  isVersionOf: proposed
  issued: 2026-03-06
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2026-03/NNNN-llm-generation-with-deterministic-validation.html"
  versionInfo: "v1.0.0 (2026-03-06)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Separate LLM generation from deterministic validation and repair in artifact pipelines

## Context and Problem Statement

AI-assisted tooling generates structured artifacts (ArchiMate XML models, YAML
configurations, structured reports) from knowledge base content using Large Language
Models. LLMs produce output that may contain syntactic errors (malformed XML,
unclosed tags), semantic errors (invalid relationship types, duplicate identifiers),
or structural violations (wrong element ordering per schema).

Relying on the LLM to self-correct these errors through prompt engineering is
non-deterministic — the same prompt may produce valid output one time and invalid
output the next. Iteratively reprompting the LLM to fix syntactic issues is
token-expensive and slow, especially with local models.

How should the pipeline handle structural correctness of LLM-generated artifacts?

## Decision Drivers

* Ensure generated artifacts conform to their target schema (e.g., ArchiMate XSD)
  reliably, regardless of LLM model tier or temperature.
* Minimize token usage and latency for structural corrections — syntactic fixes
  should not require LLM inference.
* Keep validation deterministic and reproducible — the same artifact should always
  produce the same validation result.
* Support iterative refinement where the LLM focuses on semantic improvements
  (better element names, missing relationships) while mechanical tooling handles
  structural compliance.
* Avoid coupling validation logic to any specific LLM provider or model version.

## Considered Options

1. **LLM self-correction via reprompting** — When validation fails, feed the error
   back to the LLM and ask it to fix the output. Repeat until valid or max retries.

2. **Schema-constrained generation** — Use structured output / function calling to
   force the LLM to produce schema-valid output on the first attempt.

3. **Deterministic post-processing pipeline** — The LLM generates content freely.
   Deterministic tooling validates, sanitizes, and repairs the output in a fixed
   sequence. LLM retries are reserved for semantic issues only.

4. **Template-based generation** — Pre-define XML templates with placeholders. The
   LLM fills in values. Structural correctness is guaranteed by the template.

## Decision Outcome

Chosen option: "Deterministic post-processing pipeline", because it cleanly separates
the LLM's strength (semantic content generation) from deterministic tooling's strength
(structural compliance), minimizes token usage for mechanical fixes, and maintains
validation independence from the LLM provider.

The pipeline follows a fixed sequence:

1. **Generate** — LLM produces structured content (YAML intermediate representation).
2. **Convert** — Deterministic tooling converts YAML to target format (XML).
3. **Sanitize** — Fix known mechanical issues (namespace declarations, element
   ordering, identifier prefixes, property wrapper elements).
4. **Validate** — Schema validation against the target XSD.
5. **Retry** — Only if semantic errors remain after mechanical fixes, reprompt the
   LLM with targeted feedback.

### Consequences

* Good, because mechanical fixes (element reordering, namespace correction, property
  wrapper insertion) are instant and deterministic — no token cost, no latency.
* Good, because validation quality is consistent regardless of model tier — a local
  9B model's output receives the same mechanical repair as a cloud model's.
* Good, because the intermediate YAML representation enables diff-based refinement
  (96.5% token reduction for iterative edits vs. full regeneration).
* Good, because the sanitization step accumulates fixes over time — each schema
  compliance issue discovered is fixed once in code and never recurs.
* Bad, because the sanitization layer must be updated whenever a new structural
  pattern is discovered (e.g., the `<properties>` wrapper requirement was only
  found through Archi import testing).
* Bad, because the YAML intermediate representation adds a conversion step that
  could introduce its own errors if the converter has bugs.

### Confirmation

Compliance can be confirmed by verifying that:
1. Generated artifacts pass XSD schema validation before being offered for download.
2. The sanitization step handles at least: namespace declarations, element ordering,
   identifier prefix normalization, and property wrapper elements.
3. LLM retries are only triggered for semantic issues (missing elements,
   invalid relationship types), never for structural/syntactic issues.
4. Validation results are deterministic — the same artifact always produces the
   same validation outcome.

## Pros and Cons of the Options

### LLM self-correction via reprompting

Feed validation errors back to the LLM and ask it to produce corrected output.

* Good, because no additional tooling needed — the LLM handles everything.
* Bad, because non-deterministic — the LLM may introduce new errors while fixing
  others.
* Bad, because token-expensive — each retry requires regenerating the full artifact
  (thousands of tokens for an ArchiMate model).
* Bad, because slow with local models — each retry adds 15–30 seconds of inference.
* Bad, because the same structural error recurs across generations since the LLM
  doesn't learn from previous corrections.

### Schema-constrained generation

Use structured output or function calling to enforce schema compliance at generation
time.

* Good, because output is valid by construction.
* Bad, because ArchiMate XML is too complex for current structured output
  implementations — the schema has recursive structures, optional elements, and
  ordering constraints that exceed function calling capabilities.
* Bad, because locks the pipeline to LLM providers that support structured output.
* Bad, because constraining the output format limits the LLM's ability to express
  rich architectural semantics.

### Deterministic post-processing pipeline

LLM generates freely; deterministic tooling validates and repairs.

* Good, because clean separation of concerns — LLM focuses on semantics, tooling
  handles structure.
* Good, because mechanical fixes are instant, deterministic, and free of token cost.
* Good, because accumulated fixes prevent recurrence of known issues.
* Good, because supports an intermediate representation (YAML) enabling diff-based
  refinement.
* Neutral, because the sanitization layer grows over time as new patterns are
  discovered.
* Bad, because requires maintaining a conversion and sanitization codebase.

### Template-based generation

Pre-defined templates with LLM-filled placeholders.

* Good, because structural correctness is guaranteed by the template.
* Bad, because templates constrain the model's expressiveness — the LLM cannot add
  elements, relationships, or views beyond what the template allows.
* Bad, because each new model type requires a new template.
* Bad, because architectural models vary widely in structure and size — a fixed
  template cannot accommodate this variation.

## More Information

### Intermediate YAML Representation

AInstein uses a YAML intermediate representation between LLM generation and XML
output. This design enables:

- **Diff-based refinement:** When the user requests changes to an existing model,
  the LLM returns a compact YAML diff (~163 tokens) instead of regenerating the full
  model (~4,625 tokens). A deterministic merge engine applies the diff to the
  existing YAML, then reconverts to XML. This achieves 96.5% token reduction and
  91.5% latency reduction for iterative refinement.

- **Easier LLM generation:** YAML is less syntactically demanding than XML for LLMs
  — no namespace prefixes, no closing tags, no attribute quoting rules.

- **Deterministic XML conversion:** The YAML-to-XML converter handles all structural
  requirements (namespace declarations, element ordering, identifier prefixes,
  property wrappers) consistently, regardless of what the LLM produced.

### Known Mechanical Fixes

As of March 2026, the sanitization layer handles:
- Namespace declaration and schemaLocation normalization
- Element ordering per XSD sequence (`elements` → `relationships` →
  `propertyDefinitions` → `views`)
- Identifier prefix enforcement (`id-` prefix on all identifiers)
- `<properties>` wrapper insertion for `<property>` elements on elements and
  relationships
- `xml:lang` attribute enforcement on `<name>` and `<value>` elements
