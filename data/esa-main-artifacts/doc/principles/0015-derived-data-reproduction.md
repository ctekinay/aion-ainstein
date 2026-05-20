---
parent: Principles
nav_order: PCP.15
dct:
  identifier: urn:uuid:6f7a8b9c-0d1e-4f2a-3b4c-5d6e7f8a9b0c
  title: Business-Compliant Storage – Derived Data Reproduction
  isVersionOf: proposed
  issued: 2025-10-27
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/principles/2025-10/0015-derived-data-reproduction.html"
  versionInfo: "v1.0.0 (2025-10-27)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Principle: Business-Compliant Storage – Derived Data Reproduction

## Statement  
The architecture must prioritize reproducibility and integrity over convenience or redundancy. Derived data should only be stored when reproduction from essential, immutable source data is either technically infeasible or would create unacceptable performance degradation.

## Rationale  
Storing derived data introduces risks of inconsistency, duplication, and unnecessary complexity. By ensuring that derived data can be reliably reproduced from trusted sources, the architecture remains lean, transparent, and maintainable. This principle supports long-term data integrity and reduces operational overhead.

## Implications  
- Promotes lean data storage and avoids duplication  
- Encourages immutability and integrity in source data  
- Requires robust data lineage and reproducibility mechanisms  
- Systems must support reproducibility through clear transformation logic and metadata  
- Exceptions must be explicitly justified and documented

<!-- excluded
## Scope  
Applies to all enterprise systems where data is transformed, aggregated, or enriched, including analytics platforms, reporting pipelines, and operational systems.

## Related principles  
- Business-Driven Data Availability  
- Business-Compliant Storage – Decision Snapshot Preservation  
- Data is Designed for Need to Know
-->
