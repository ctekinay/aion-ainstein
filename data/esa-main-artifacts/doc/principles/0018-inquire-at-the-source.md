---
parent: Principles
nav_order: PCP.18
dct:
  identifier: urn:uuid:9c0d1e2f-3a4b-4c5d-6e7f-8a9b0c1d2e3f
  title: Inquire at the Source
  isVersionOf: proposed
  issued: 2025-11-12
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/principles/2025-11/0018-inquire-at-the-source.html"
  versionInfo: "v1.0.0 (2025-11-12)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Inquire at the Source

## Statement

The origin of information is authoritative in determining what is correct, actual, and authentic. Business functions and services that produce data are the definitive source of truth for that data, and all consuming processes must defer to the originating source for authoritative information.

## Rationale

Establishing clear data ownership and authority at the source is essential for operational resilience, auditability, and consistent decision-making based on authentic data. By recognizing the originating business function as the authoritative source, the organization avoids the creation of conflicting "truths" and supports the principle of "do it right the first time." This governance approach provides clear accountability for data quality and integrity, ensuring that reliable and high-quality information is available for services and decision-making.

## Implications

- Business functions and services that originate data are designated as the authoritative source for that data
- Data governance models must explicitly identify the source of authority for each data element or dataset
- Consuming processes must query or receive data from the authoritative source, not from derived copies or aggregations, unless explicitly justified
- Data ownership and stewardship responsibilities must be clearly assigned to the originating business function
- Any transformation, aggregation, or derivation of source data must maintain traceability back to the authoritative source
- Conflicts between different versions of data must be resolved by deferring to the authoritative source
- Architectural patterns that create multiple conflicting sources of truth are discouraged

<!-- From this point on optional elements only. Feel free to remove. 
## Scope
Applies to all business-critical data generated at the edge or origin, including but not limited to measurement, telemetry, and operational event data, across both local and central systems.

## Related principles
- Make Uncertainty Explicit to Strengthen Decisions
- Business Specifications Driven Data Ownership
- Business-Compliant Storage – Decision Context Preservation
-->
