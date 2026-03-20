---
parent: Principles
nav_order: PCP.11
dct:
  identifier: urn:uuid:2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e
  title: Data is Designed for Need to Know
  isVersionOf: proposed
  issued: 2025-10-27
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/principles/2025-10/0011-data-design-need-to-know.html"
  versionInfo: "v1.0.0 (2025-10-27)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Principle: Need to Know

## Statement  
The need-to-know principle limits access to only the information required for legal, contractual, or operational duties. Data must be structured to ensure confidentiality and privacy by default, while allowing flexibility for a “need-to-share” approach when transparency or collaboration is necessary.

## Rationale
The rationale behind the need-to-know principle is to minimize the risk of unauthorized access, misuse, or leakage of sensitive information. By restricting access only to those who require it for their duties, organizations:

* Ensures compliance with privacy and security standards such as GDPR, ISO 27001, and other regulatory frameworks. 
* It builds trust among stakeholders and protects sensitive information from unauthorized access.
* Reduce security exposure by minimizing the amount of sensitive information accessible to any person, system, or process.
* Promoting accountability where every instance of information access is traceable, purposeful, and defensible, where access rights are granted only for a clearly defined operational needs.


Furthermore, defining privacy restrictions upfront is essential for designing business processes and information systems correctly—without these constraints, proper architecture and governance cannot be established.

## Implications
To uphold the need-to-know principle and ensure confidentiality by design, the following architectural and governance implications apply:

- Access control mechanisms must be embedded in the overall architecture.  
- Information classification and tagging are mandatory to enforce confidentiality rules.  
- Systems must support configurable and granular access modes (e.g., “need to share”) that enable controlled collaboration while maintaining data protection.  
- Governance processes must include privacy impact assessments during both design and operation phases.
- Retention policies (data storage/persistence) must be aligned with legal and ethical standards, ensuring information is deleted when no longer justified.
- Examples of implementation patterns for confidentiality (not prescriptive):  
  - Role-Based Access Control (RBAC)  
  - Attribute-Based Access Control (ABAC)  
  - Data masking and tokenization for sensitive fields  
  - Encryption at rest and in transit  
  - Segregation of duties in system administration  

## Scope
Enterprise-wide, with emphasis on telemetry and operational data.

## Related principles
- Data Protection by Design  
- Transparency and Accountability

## More information
* [Need to know](https://en.wikipedia.org/wiki/Need_to_know)