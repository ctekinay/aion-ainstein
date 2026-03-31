---
parent: Principles
nav_order: PCP.17
dct:
  identifier: urn:uuid:8b9c0d1e-2f3a-4b4c-5d6e-7f8a9b0c1d2e
  title: Business Specifications Driven Data Ownership
  isVersionOf: proposed
  issued: 2025-10-27
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/principles/2025-10/0017-data-ownership.html"
  versionInfo: "v1.0.0 (2025-10-27)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Principle: Business Specifications Driven Data Ownership

## Statement  
The designated data owner is accountable for ensuring the availability of their data in accordance with agreed business specifications. This responsibility applies regardless of how the data is technically provisioned—whether through internal systems, external integrations, or support from telemetry services. Technical services may assist but do not assume ownership unless delegated.

## Rationale  
Clear ownership ensures that data availability aligns with business needs and governance expectations. It prevents ambiguity about who is responsible for data quality, timeliness, and completeness. By maintaining accountability at the business level, the architecture supports flexible implementation while preserving integrity and traceability.

## Implications  
- Data owners must define and communicate availability requirements, including performance expectations and quality thresholds  
- These specifications may be formalized through contracts, SLAs, or governance agreements  
- Data owners may delegate implementation but retain responsibility for outcomes  
- When new derived data is created, ownership is established for that derived dataset, distinct from the ownership of its source data
- Reduces ambiguity in data governance and strengthens accountability across systems  
- Exceptions (e.g., shared ownership, platform-managed data) must be explicitly resolved through governance mechanisms

<!-- Excluded for now
## Scope  
Applies enterprise-wide, especially in domains where data provisioning supports operational, analytical, or compliance-critical processes.

## Related principles  
- Business-Driven Data Availability  
- Business-Compliant Storage – Derived Data Reproduction  
- Make Uncertainty Explicit to Strengthen Decisions
-->
