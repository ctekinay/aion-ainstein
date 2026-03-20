---
parent: Principles
nav_order: PCP.12
dct:
  identifier: urn:uuid:3c4d5e6f-7a8b-4c9d-0e1f-2a3b4c5d6e7f
  title: Business-Driven Data Readiness
  isVersionOf: proposed
  issued: 2025-10-27
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/principles/2025-10/0012-business-driven-data-readyness.html"
  versionInfo: "v1.0.0 (2025-10-27)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Principle: Business-Driven Data Readiness

## Statement  
Business services must initiate and explicitly communicate their data needs—both current and future—in a structured way to supporting data-centric services. This ensures that providers understand the complete business requirements and can deliver aligned capabilities, avoiding fragmented or duplicated data management efforts.

## Rationale  
- Ensures the **right data** is established—neither too much nor too little—to meet functional and operational needs.  
- Makes **service level expectations explicit**, enabling predictable and reliable data delivery.  
- Supports **privacy and compliance control** by clarifying what data is required and why.  
- Aligns data capabilities with business context, fostering consistency and reducing redundancy across services.  

## Implications  
- Business services must achieve a **high level of maturity in their definition and scope**, as they now define and own data needs.  
- Data-centric services must adapt their capabilities to meet articulated business requirements and agreed service levels.  
- Data retention (data storage) must be explicitly justified by business need and comply with privacy regulations; unjustified data may be deleted.
- Governance processes must enforce structured communication between business and IT to prevent siloed data collection and harmonization.  
- Data must align to business services with **unambiguous semantics**, ensuring shared understanding of meaning and usage.  
- Architectural designs must prioritize reuse and consistency of data across services.   
