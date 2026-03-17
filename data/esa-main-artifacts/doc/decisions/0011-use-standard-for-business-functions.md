---
parent: Decisions
nav_order: ADR.11
dct:
  identifier: urn:uuid:e5f6a7b8-c9d0-4e1f-2a3b-4c5d6e7f8a9b
  title: Use standard for describing business functions
  isVersionOf: accepted
  issued: 2025-01-01
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2025-01/0011-use-standard-for-business-functions.html"
  versionInfo: "v1.0.0 (2025-01-01)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Use standard for describing business functions

## Context and Problem Statement

There are many metamodels defined to describe the functional area for the electricity distribution networks. 

Which one of those metamodels to use for describing the energy system architecture? 

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

* [nbility](https://www.edsn.nl/nbility-model/)<br>
  NBility is a comprehensive capability model designed for Dutch grid operators. It was developed to streamline
  collaboration within the utility sector and with the suppliers and advisors of grid operators.


* IEC 61968-1 Business Packages / Functions<br>This describes the functions of the distribution management domain covers
  all aspects of management of utility electrical distribution networks. A distribution utility will have some or all of
  the responsibility for monitoring and control of equipment for power delivery, management
  processes to ensure system reliability, voltage management, demand-side management,
  outage management, work management, network model management, facilities management,
  and metering

## Decision Outcome

Chosen option: IEC 61968-1 Business Packages / Functions is leading, because

* Aligns with another international standardized metamodel to achieve semantic interoperability, like the CIM information
  model.
* The metamodel accurately describes the functions of a DSO as part of the IEC organisation.
* Usable in co-operation with international business partners.

Other frameworks may still be used as long as there is architectural consistency with IEC 61968-1 as basis.

