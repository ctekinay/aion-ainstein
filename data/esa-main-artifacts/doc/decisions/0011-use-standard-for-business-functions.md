---
# Configuration for the Jekyll template "Just the Docs"
parent: Decisions
nav_order: 11

status: "accepted"
# date: {YYYY-MM-DD when the decision was last updated}
# decision-makers: {list everyone involved in the decision}
# consulted: {list everyone whose opinions are sought (typically subject-matter experts); and with whom there is a two-way communication}
# consulted: {list everyone whose opinions are sought (typically subject-matter experts); and with whom there is a two-way communication}
# informed: {list everyone who is kept up-to-date on progress; and with whom there is a one-way communication}
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

