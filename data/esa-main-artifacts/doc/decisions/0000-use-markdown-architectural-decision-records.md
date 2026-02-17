---
parent: Decisions
nav_order: ADR.0
dct:
  identifier: urn:uuid:a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
  title: Use Markdown Architectural Decision Records
  isVersionOf: accepted
  issued: 2025-06-01
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2025-06/0000-use-markdown-architectural-decision-records.html"
  versionInfo: "v1.0.0 (2025-06-01)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Use Markdown Architectural Decision Records

## Context and Problem Statement

As ESA want to record architectural decisions made independently, whether decisions concern the architecture ("
architectural decision record"), the business, or other fields.

Which format and structure should these records follow?

## Considered Options

* [MADR](https://adr.github.io/madr/) 4.0.0 – The Markdown Architectural Decision Records
* [Michael Nygard's template](http://thinkrelevance.com/blog/2011/11/15/documenting-architecture-decisions) – The first
  incarnation of the term "ADR"
* [Sustainable Architectural Decisions](https://www.infoq.com/articles/sustainable-architectural-design-decisions) – The
  Y-Statements
* Other templates listed at <https://github.com/joelparkerhenderson/architecture_decision_record>
* Formless – No conventions for file format and structure

## Decision Outcome

Chosen option: "MADR 4.0.0", because

* Implicit assumptions should be made explicit.
  Design documentation is important to enable people understanding the decisions later on.
  See also ["A rational design process: How and why to fake it"](https://doi.org/10.1109/TSE.1986.6312940).
* MADR allows for structured capturing of any decision.
* The MADR format is lean and fits our development style.
* The MADR structure is comprehensible and facilitates usage & maintenance.
* The MADR project is vivid.
