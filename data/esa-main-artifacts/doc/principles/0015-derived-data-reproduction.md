---
parent: Principles
nav_order: "0015"
title: Business-Compliant Storage – Derived Data Reproduction
status: proposed
date: 2025-10-27

driver: Data integrity, reproducibility, storage efficiency
#approvers: ...
contributors: Christian Heuer, Laurent van Groningen, Robert-Jan Peters
#informed: Data owners, system architects, analytics teams
---

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
