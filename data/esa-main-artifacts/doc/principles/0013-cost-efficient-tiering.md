---
parent: Principles
nav_order: PCP.13
dct:
  identifier: urn:uuid:4d5e6f7a-8b9c-4d0e-1f2a-3b4c5d6e7f8a
  title: Business-Compliant Storage – Cost-Efficient Tiering
  isVersionOf: proposed
  issued: 2025-10-27
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/principles/2025-10/0013-cost-efficient-tiering.html"
  versionInfo: "v1.0.0 (2025-10-27)"
---
<!-- markdownlint-disable-next-line MD025 -->

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
