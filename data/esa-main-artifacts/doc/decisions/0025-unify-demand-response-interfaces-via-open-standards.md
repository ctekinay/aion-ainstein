---
# Configuration for the Jekyll template "Just the Docs"
parent: Decisions
nav_order: 25
title: Provide a unified Demand/Response product interface for market and grid coordination
status: proposed
date: YYYY-MM-DD when the decision was last updated

driver: Robert-Jan Peters  <robert-jan.peters@alliander.com>, Laurent van Groningen <laurent.van.groningen@alliander.com>
#approvers: list everyone with the final say in this ADR.
contributors: Mitchel Haeve <mitchel.haeve@alliander.com>, Thijs Nugteren<thijs.nugteren@alliander.com>, Cagri Tekinay<cagri.tekinay@alliander.com>
#informed: list every one who need to be aware of the decision once made. 

# These are optional elements. Feel free to remove any of them.
# additional decision-makers: {list everyone involved in the decision}
---

<!-- markdownlint-disable-next-line MD025 -->

# Provide a unified Demand/Response product interface for market and grid coordination

## Context and Problem Statement

European regulations require a standardized approach to mitigation measures for operational capacity problems (such as
balancing, congestion management, and voltage control). Within different Demand/Response products, there is a growing
need for interoperability between grid operators (DSOs) and market participants such as CPOs.

Current implementations of Demand-Response (D/R) interfaces vary widely across vendors, platforms, and use cases. This
fragmentation hampers interoperability, increases development costs, limited scalability, and slows down market-wide
deployment of flexible energy services. With increasing regulatory pressure (e.g., EU 2022/2555), digitalization of the
energy sector, and the rise of distributed energy resources (DERs), a unified and standardized D/R interface has become
essential.

## Decision Drivers

* Drive scalable integration of market participants
* Control operational costs while supporting diverse market participant business and technical interfaces.
* Ensure consistent interpretation of energy-related concepts preventing misinterpretations with the scope of the EU
  market, especially in multivendor and multi-domain environments.
* Ensure energy system reliability and stability to support secure, uninterrupted power delivery and maintain grid
  integrity under all operating conditions.
* Ensure compliance and consistency with international standards.

The following selection of architecture and design principles are relevant for unifying a Demand/Response (D/R)
interface across market combinations (e.g., TSO-with-DSO, TSO-with-aggregator, DSO-with-aggregator, DSO-with-customer,
aggregator-with-customer, customer-with-customer) and supporting white-label d. The intention is **not** to discuss
these underlying principles but ensuring consistency and clear guidance. The reader should note that Not all
combinations are currently in practice, but the design should adhere to the considerations stated below:

1. Dedicated interface per Business **Interaction Type**<br>
   Principle: The business interfaces should be scoped to distinctly responsible business processes (e.q. D/R product
   activation, availability declaration, submit D/R capacity need, settlement)<br>
   Rationale: Promotes clarity, reusability, and avoids overloading interfaces with unrelated business functionality.
2. A unified technical interface per Market Role Combination<br>
   Principle: Each unique combination of interacting roles (e.g., DSO ↔ Flexibility Provider, DSO ↔ Aggregator, DSO ↔
   Customer) should use a single, consistent business interface based on a common semantic model.<br>
   Rationale: Reduces duplication, prevents fragmentation, enables common cybersecurity measures, and simplifies
   integration for each actor.
4. Standard before Custom<br>
   Principle: Use open, internationally recognized standards where available before designing new protocols.<br>
   Rationale: Ensure interoperability, future-proofing, and regulatory alignment.
5. Information Model Alignment<br>
   Principle: All interfaces must align with common, extensible information models (e.q. CIM, IEC 61850)<br>
   Rationale: Ensures semantic consistency, interoperability at the information level, and operational clarity.
6. Explicit Semantics of Roles<br>
   Principle: All interfaces must be clearly defined in terms of actor roles (e.q. DSO, TSO, flexibility provider,
   aggregator) as recognized in the EU (ENTSO-E Harmonized Energy Market Role Model) and national regulation.<br>
   Rationale: Prevents ambiguity in message interpretation/meaning and clarifies corresponding responsibilities.
7. Security and Authorization by Design<br>
   Principle: The unified technical interface must include strong authentication, authorization, and encryption
   mechanisms.<br>
   Rationale: Complies with the cybersecurity regulations (e.g., NIS2) and protects assets, customer privacy and ensure
   energy system reliability and stability.
8. Event-Driven First<br>
   Principle: The demand / response product business interface should favor event-based communication (e.g. D/R events,
   telemetry) and not active polling.<br>
   Rationale: This improves the responsiveness and scalability, especially in real-time or near real-time interaction.
9. Market-Agnostic Core with Configurable Profiles<br>
   Principle: A common base interface should support configuration, and extension of the different demand / response
   products and specific rules or constraints. <br>
   Rationale: Supports white label D/R products and enables synergy among them through shared functionality through the
   reuse of the same logic across different products/markets.
10. Backward compatibility and Evolution<br>
    Principle: Interfaces must support evolution through versioning and maintain backward compatibility wherever
    needed/possible.
    Rationale: Supports gradual migrations and long-term maintainability.
11. Machine-Readable Contracts and Validation<br>
    Principle: Use machine-readable interface specifications (e.q. OpenAPI, JSON Schema, SHACL) to automate validation
    and easy integration.<br>
    Rationale: Reduces errors, speeds up development, and enables automated testing/validation.
12. Govern interfaces with Transparent and Inclusive Operational Ownership
    Principle: The DSO must lead interface governance, but must do so with transparent documentation, multi-actor
    alignment, and supported onboarding paths for third parties.
    Rationale: The unified interface is tightly coupled to DSO internal operations (e.q. capacity management, congestion
    forecasting, demand/response activation logic) and should not depend on external governance.
13. Identify and Mitigate Operational Risk Introduced by Intermediaries<b>
    Principle: When using intermediaries between critical actors (e.g., between DSO and flexibility operator), the
    system architecture must identify, limit, and mitigate operational risks stemming from loss of transparency, timing
    delays, data distortion, or dependency on third-party / intermediaries control logic.<b>
    Rationale: The inclusion of intermediaries — such as aggregation platforms, third-party gateways, or flexibility
    service providers — introduces operational risks that can undermine energy system reliability, safety, and
    transparency if not properly governed.

> [!NOTE]
> In the interaction between the DSO, acting as the System Operator, and a Market Participant providing flexibility
> services, a single unified technical interface should be used. Since the Market Participant fulfills the same role in
> both cases, products such as Capacity Limiting Contract (CBC-A) and Redispatch should be supported via the same
> interface. The use of the GOPACS platform is an implementation detail and should not influence this principle.

> [!NOTE]
> A **business interface** represents the point of interaction where a business role, actor, or organizational unit
> offers or consumes a service in a business context.
> It defines what is exchanged (the value or service), why (the purpose or business goal), and under what conditions (
> policies, contracts, responsibilities) — not how it is technically implemented.

> [!NOTE]
> A **technical interface** defines the means of interaction between application components, systems, or devices.
> It specifies how information is exchanged — the protocols, endpoints, data structures, and message formats.

## Considered Options

Several open standards already exist that address various aspects of operating demand-response products. However, no
single interface is universally adopted, and overlapping implementations create ambiguity in projects and system
integration.

## Decision Outcome

The adoption and promotion of a unified Demand-Response interface (business, technical) based on existing open
standards, ensuring compatibility with market actors, regulatory requirements, and grid operator systems.

### Consequences

Supporting guidelines are:

#### Governance & Coordination

Clear governance ownership

* System Operator owns the operational rules and the configuration of the technical interface.
* Changes must follow a structured change management process involving stakeholders.
* Stakeholders should be represented in steering or feedback groups.
* Coordination centralized in one place with a mandate for developing communication tools.
* Involvement of external stakeholders to ensure the customer perspective is taken into account.
* Involving architecture and security colleagues to set technical requirements (e.g., resilience).

Vision and positioning

* Choices about communication tools and prioritization should be made early in the demand/response product funnel.
* Positioning of communication tools in relation to target groups and applications should be clearly defined.
* Decisions are made with a clear understanding of how each communication tool is intended to be used.

#### Transparency & Requirements

Operational transparency

* System Operator must publish interface documentation, service level agreements, and logic that affects external
  actors.
* Clear requirements for internet-based communication with customers.
* Awareness of trends in other countries for communication between network operators and customers/market parties.

#### Testing & Development

Test and sandbox environments

* Provide non-production environments to validate integration and simulate operational responses.
* Identify functional and non-functional development needs for each communication tool.
* Provide reference implementations for each communication tool.

> [!NOTE]
> [MFFBAS](https://www.mffbas.nl/) provides standardized guidelines and regulations for these topics.

## More Information

Several open standards are available:

* IEC 61850-7-420 (DER models)
* IEC 62746 (Systems interface between customer and energy management system)
* IEC 62325 (Market communication profiles)
* IEEE 2030.5 (Smart Energy Profile)
* IEC 61850- (SCL models) - **(NBNL | D/R
  product / [RTIv1, RTIv2](https://www.netbeheernederland.nl/netcapaciteit-en-flexibiliteit/realtime-interface))**
* [Open Automated Demand Response (OpenADR)](https://www.openadr.org/) - **(eLaad | D/R product / NFA)**
* [S2standard (Smart Energy For the Zero Emission Century)](https://s2standard.org/)
* [Universal Smart Energy Framework (USEF|UFTP)](https://github.com/USEF-Foundation/UFTP) - **(GOPACS | D/R product /
  capacity limiting products)**
* [Intra-Day Congestion Spreads (IDCONS)](https://www.gopacs.eu/en/documents-and-manuals/) - **(GOPAC S| D/R product /
  redispatch products)**
* [Open Smart Charge Protocol (OSCP)](https://openchargealliance.org/)
* [Distributed Network Protocol (DNP3)](https://www.dnp.org/)
* Hub for Energy Distribution and Excess Resource Allocation (Hedera) - **(Alliander | D/R product / NFA)**
* etc

Reference information:

- [Netbeheer Nederland Overzicht flex-producten](https://www.rvo.nl/sites/default/files/2025-04/20241118_NBNL_Overzicht-Flexproducten_Productcatalogus.pdf)
- [ENTSO-E Harmonized Energy Market Role Model (HEMRM)](https://www.entsoe.eu/data/cim/role-models/)
