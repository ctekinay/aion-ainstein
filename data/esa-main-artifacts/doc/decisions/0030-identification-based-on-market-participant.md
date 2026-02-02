---
parent: Decisions
nav_order: ADR.30
dct:
  identifier: urn:uuid:e7f8a9b0-c1d2-4e3f-4a5b-6c7d8e9f0a1b
  title: Identification Based on Market Participant Persona
  isVersionOf: proposed
  issued: 2025-12-17
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2025-01/0030-identification-based-on-market-participant.html"
  versionInfo: "v1.0.0 (2025-12-17)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Identification Based on Market Participant Persona

## Context and Problem Statement

In a harmonized European energy market, market participants—such as Flexibility Service Providers (FSPs), Charging Point
Operators (CPOs), and Aggregators—must be uniquely identifiable across all interactions with system operators (DSOs,
TSOs) and other stakeholders. Identification is essential for secure, interoperable, and auditable exchanges in
flexibility markets and grid operations. When engaging in market or contractual transactions, market participants should
be able to:

* Act in multiple roles and manage multiple facilities.
* Establish hierarchical parent-child relationships to represent ownership and operator connections.
* Delegate operational responsibilities to subcontractors as needed.

A facility is a uniquely identifiable physical site with one or more installations that connect to the electricity or
gas network.

These requirements spans multiple dimensions:

* Technical — Identification of systems, assets, and facilities (e.g., through certificates or device-level IDs).
* Administrative — Clear mapping of ownership, contractual responsibilities, and operational roles.
* Financial — Accurate linkage for billing, settlements, and compliance obligations.

The complexity increases as:

* Market participants may operate multiple facilities or service delivery points.
* System integrators often act as intermediaries, adding layers of responsibility.
* DSOs and TSOs need consistent identifiers to maintain grid security and operational integrity.

Current implementations vary widely across platforms and jurisdictions, leading to fragmentation, interoperability
issues, and increased integration costs. How can market participants and their associated facilities be identified in a
standardized, interoperable, and secure way?

## Decision Drivers

The following drivers are key factors that influence and justify the architectural decision process.

* Ensure alignment with contractual obligations, enabling parties to fulfil legally defined responsibilities in a
  consistent and transparent manner, and reducing the risk of disputes or non-compliance during coordinated market
  operations.
* Ensure compatibility with international interoperability frameworks, including the ENTSO-E harmonized role model, to
  facilitate cross-border and cross-market collaboration, and to prevent fragmentation that would increase integration
  and governance overhead.
* Enable representation of multiple roles for market participants — such as operator, owner, or
  aggregator — so that diverse business models and operational responsibilities can be accurately reflected, supporting
  both operational coordination and regulatory reporting.
* Ensure seamless integration with existing market models and IEC standards, reducing duplication of effort, supporting
  interoperability with established systems, and ensuring long-term alignment with industry-wide evolution.
* Enable the modeling of hierarchical relationships between market parties, assets, and facilities, providing a
  consistent representation of ownership, operational control, and aggregation structures, which is crucial for
  traceability, validation, and secure operational decision-making.
* Ensure adherence to established security frameworks, including Public Key Infrastructure (PKI), to maintain trust,
  authenticity, and secure interactions across participants, thereby reducing exposure to cyber threats and supporting
  regulatory compliance.
* Minimize implementation effort and avoid unnecessary complexity, ensuring that the solution is practical to adopt for
  heterogeneous market participants, lowering integration costs, and speeding up widespread market uptake.

## Considered Options

### Option 1 — Use “Market Participant” based identification

A market participant is any legal entity or organization that is formally registered and authorized to engage in
one or more defined roles within the electricity market. These roles include activities such as energy
production, consumption, supply, balancing, metering, aggregation, or system operation. This participant is uniquely
identified and recognized in market processes and operates under regulatory and contractual agreements to ensure the
functioning and integrity of the energy system.

### Option 2 — Use Facility-Based identification

The Dutch energy low (Elektriciteitswet, Gaswet, and related regulatory frameworks) describes a clear,
domain-appropriate definition of “facility” as used in the Dutch energy system. A facility contains one or more metering
points, equipments, or energy-producing or energy-consuming units under the responsibility of a market participant, with
the following characteristics:

- Identify facilities directly using technical IDs (e.g., allocation point IDs, metering point IDs).
- The scope of a facility may vary (e.g., more suppliers behind one energy connection; more connections to one facility,
  etc.)
- Facilities do not reflect the products and legal operational relationships, so explicit mapping between facilities and
  market participants is required for contractual roles.

### Option 3 — Introduce a DER Identifier

A Distributed Energy Resource (DER) is a small- to medium-scale grid-connected asset that can generate, store, or
flexibly modulate electrical energy at the distribution grid level or behind a customer’s connection point. DERs are
typically modular, geographically dispersed, and can be individually or collectively monitored, controlled, or
dispatched to support system operations, flexibility markets, or local energy management.

The DER is the business object that represents a physical or logical service point that is connected to the electricity
or gas network. It is uniquely identified by a DER identifier (DER ID), with the following characteristics:

- Create a dedicated DER entity and identifier.
- Would require defining a new role in the ENTSO-E harmonized role model.
- Would require redesign of models and re-integration with DSOs, aggregators, and market systems.

## Decision Outcome

The outcome is to use the “Market Participant” representation as the primary identifier to operate in the electricity
market.

- **Authoritative model** — “Market Participant” already defines contractual and operational roles.
- **Rich data model** — Includes attributes like EAN18 and other relevant information.
- **Extensibility** — Supports hierarchical relationships, intermediaries, and multiple facilities.
- **Standard alignment** — Leverages an existing IEC standard widely recognized in the energy sector.

### Consequences

* Positive:

- Establishes a transparent governance framework for ownership and operational control of the service delivery points,
  ensuring accountability and clarity across stakeholders.
- Enables scalable business processes, not just technology, by providing consistency in delivering diverse services
  across departments while maintaining validity and compliance.
- Leverages standardized IEC definitions, enhancing interoperability and reducing integration complexity.
- Future-proof design supports role expansion and nested organizational relationships, accommodating evolving market
  structures.
- Simplifies cross-party integration between DSOs, aggregators, and system integrators through harmonized identifiers.


* Negative:

- Introducing nested or cascading relationships can increase complexity in data modeling and system logic.
- Existing application protocols may need significant adjustments to incorporate hierarchical identifiers and delegation
  models.
- Legacy systems that rely on EAN18 identifiers (connection-point, facilities, etc.) will require modifications or
  mapping layers, adding migration effort.
- Governance clarity may come at the cost of increased administrative overhead, especially for maintaining parent-child
  structures and delegation records.


## More Information

### ENTSO-Harmonized Electricity Market Role Model (HEMRM)

The [ENTSO-Harmonized Electricity Market Role Model (HEMRM)](https://www.entsoe.eu/data/cim/role-models/) standardizes terminology for electricity market
roles and domains. It establishes unified vocabulary to support IT development and enable seamless process integration
between system operators and market participants.

### IEC62325 Concepts

IEC62325 provides a harmonized, standards-based information model for market communication in the energy sector. Within
it, the Market Participant (MP) data model defines how actors, roles, organizational structures, and relationships are
represented consistently across European power markets.

### EAN18 identification scheme

In the Dutch energy system, the EAN18 is a long-established, robust way to uniquely identify a Point of Common
Coupling (PCC) or connection point. In relation to the IEC62325 concept, it is used to identify an UsePoint or
MeteringPoint, which depends on the context.

### Distributed Energy Resource (DER)

In the context of IEC standards, a DER corresponds to controllable resources modeled in IEC61850-7-420 (DER logical
nodes), represented as assets/equipments and measurements in IEC61970/61968 (CIM), and exchanging operational data
through IEC62325 for market interactions.

Under the ACER Demand Response Network Code (NC DR), DERs act as flexibility service providers whose controllable infeed
or demand can be activated by distributed system operators (DSO) or market parties to support balancing, congestion
management, and voltage control.
