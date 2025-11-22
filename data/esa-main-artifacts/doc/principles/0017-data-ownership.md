---
parent: Principles
nav_order: "0017"
title:  Business Specifications Driven Data Ownership
status: proposed
date: 2025-10-27

driver: Data governance, accountability, business-aligned provisioning
#approvers: ...
contributors: Christian Heuer, Laurent van Groningen, Robert-Jan Peters
#informed: Data owners, system architects, telemetry service teams
---

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
