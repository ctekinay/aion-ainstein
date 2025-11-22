---
parent: Principles
nav_order: "0013"
title: Business-Compliant Storage – Cost-Efficient Tiering
status: proposed
date: 2025-10-27

driver: Cost optimization, scalable infrastructure, business relevance of data
#approvers: ...
contributors: Christian Heuer, Laurent van Groningen, Robert-Jan Peters
#informed: Data owners, system architects, IT operations
---

# Principle: Business-Compliant Storage – Cost-Efficient Tiering

## Statement  
Storage strategies must be optimized based on business relevance and access frequency. Data transitions from hot (frequent access) to warm (occasional access) and cold (archival) storage tiers to reduce infrastructure costs while maintaining availability according to business requirements.

## Rationale  
This principle ensures that storage resources are used efficiently by aligning data placement with actual business usage. It supports scalable data management and reduces unnecessary infrastructure spending.

## Implications  
- Enables scalable and cost-effective data management  
- Business processes must define access patterns and storage needs  
- Supports historical data management through compression, aggregation, or generalization of archived data  
- Requires clear tiering policies and automation for data movement across tiers  
- Infrastructure must support differentiated performance and retention characteristics

<!-- excluded
## Scope  
Applies to all enterprise systems managing structured and unstructured data, including operational, analytical, and archival platforms.

## Related principles  
- Business-Driven Data Availability  
- Business-Compliant Storage – Privacy-Driven Retention  
- Business-Compliant Storage – Derived Data Reproduction
-->
