---
parent: Decisions
nav_order: ADR.12
dct:
  identifier: urn:uuid:f6a7b8c9-d0e1-4f2a-3b4c-5d6e7f8a9b0c
  title: Use CIM (IEC 61970/61968/62325) as default domain language
  isVersionOf: accepted
  issued: 2025-01-01
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2025-01/0012-use-CIM-as-default-domain-language.html"
  versionInfo: "v1.0.0 (2025-01-01)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Use CIM (IEC 61970/61968/62325) as default domain language

## Context and Problem Statement

The energy transition demands the integration of diverse systems—ranging from traditional power grids to renewable
energy sources, smart meters, electric vehicles, and distributed energy resources. These systems are developed by
different stakeholders using heterogeneous data models, leading to interoperability challenges

Despite the availability of standards, semantic interoperability remains a major barrier in the digitalization of energy
systems. Stakeholders often use inconsistent terminologies, data structures, and communication protocols, making it
difficult to:

* Integrate and exchange data across systems and organizations
* Ensure consistent interpretation of energy-related concepts
* Enable automation, analytics, and decision-making at scale

## Decision Drivers

* Achieve Semantic Interoperability,<br>involving the sharing of information and knowledge between organization, through
  the business processes they support, by the exchange of information/data between their ICT systems. </br>
  SOURCE: https://ec.europa.eu/isa2/sites/isa/files/eif_brochure_final.pdf
* Reusability, <br>involving business process definitions is becoming increasingly important as part of digital
  transformation and regulatory alignment efforts to enable:
    * consistency across energy sector operations
    * easier compliance with EU-wide and domestic regulations
    * faster deployment of digital services
    * easier auditability and traceability of processes and decisions

## Considered Options

* IEC standard (IEC 61970/61968/62325)—can be adopted as a domain language
* Alliander Logical Data Model

## Decision Outcome

Chosen option: IEC as standard domain language (IEC 61970/61968/62325), because

* Aligns with another international standardized metamodel to achieve semantic interoperability, like the CIM
  information model.
* The adopted approach will be informed by the ongoing work of relevant IEC working groups, ensuring compatibility with
  emerging international standards at the IEC level.
* Compliance with the EU Network Codes will be a guiding requirement, particularly in relation to operational procedures
  and system interoperability.
* Where applicable, standardisation in software—such as grid planning tools and data exchange models—will be prioritized
  to improve maintainability, interoperability, and vendor neutrality.
* The solution architecture will adhere to Domain-Driven Design (DDD) principles, promoting a clear separation of bounded contexts and aligning software structure with the
  business domain.
* Ability to model key concepts (e.g. assets, measurements, market roles, electrotechnical components )
* Facilitating interoperability through semantic alignment across systems and stakeholders
* Usable in co-operation with international business partners.

### Consequences

However, implementing CIM as a shared semantic layer introduces its own challenges:

* Complexity of the CIM ontology and its evolving structure
* Mapping legacy or proprietary data models to CIM
* Ensuring stakeholder alignment on concept usage
* Tooling and infrastructure for managing and publishing CIM-based vocabularies
