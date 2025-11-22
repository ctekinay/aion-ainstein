---
# Configuration for the Jekyll template "Just the Docs"
parent: Decisions
nav_order: 23
title: Flexibility Service Provider Initiates Pull-Based Operational Constraints
status: proposed
date: 2025-09-19

driver: Robert-Jan Peters <robert-jan.peters@alliander.com>
#approvers: list everyone with the final say in this ADR.
contributors: Laurent van Groningen <laurent.van.groningen@alliander.com>
#informed: list every one who need to be aware of the decision once made. 

# These are optional elements. Feel free to remove any of them.
# additional decision-makers: {list everyone involved in the decision}
---

<!-- markdownlint-disable-next-line MD025 -->

# Flexibility Service Provider is responsible to acquire operational constraints

## Context and Problem Statement

To keep the risk of a System Operator to an acceptable level, remedial actions may be planned, such as curtailment,
redispatch and switching actions. The Remedial Action Plan (RAP) defines all required remedial actions to be executed
by the system operator itself, by service providers, or by other market participants in the energy system.

A remedial action is typically expressed as an operational constraint that is provided by system operators (DSO or TSO)
and is shared with market participants, including flexibility providers (FSP). In the flexibility market model,
this Flexibility Service Provider (FSP) is a registered market participant responsible for operating distributed energy
resources (DERs) or flexible loads according to the agreed schedules and operational constraints.

Timely access to operational constraints (belonging to the remedial actions) is essential to ensure that FSPs can adapt
dispatch plans and control actions to meet grid security requirements. The communication profile for retrieving the
operational constraint should support interoperability, scalability, and secure access across platforms. A standardized
approach is needed to manage the timing and responsibility of data exchange.

## Decision Drivers

* Enable autonomy of operation, where each flexibility service provider determines its own retrieval schedule within
  agreed timelines, enabling alignment with internal control and optimization processes.
* Enable scalability, where this reduces the need for the system operators to push updates to all participants
  simultaneously, avoiding potential congestion in communication infrastructure.
* Ensure interoperability across platforms and alignment with i.e., IEC 62325 principles for market participant
  initiated transactions.
* Ensure system reliability and stability for operating capacity management, while enabling market participation in grid
  balancing and congestion management.
* Ensure system resilience, to allow retry and recovery mechanisms to be implemented by the flexibility service provider
  in case of transient or communication failures.
* Ensure traceability, where each retrieval event must have a unique ID, timestamp, and linked FSP request to enable
  audit trails and operational sequence reconstruction.
* Ensure auditability, where logging of data exchanges between system operator and flexibility provider systems,
  capturing request-response details, version history, and timing for audit trails and compliance reporting.
* Ensure the non-discriminatory provision of services to FSPs
* Ensure alignment with Alliander's measurement and control strategy, specifically regarding the roles in constraint
  publication and retrieval processes.

## Considered Options

There are two functional options to exchange operating constraints:

- The system operator pushes (sends) the constraints to the market participant.
- The market participant pulls (retrieves) the constraints from the system operator.

The different options also affect who is taking the initiation of having all requirements in place being able to push
or pull.
I.e., when the system operator needs to send the messages, it would be consistent he creates the connection.
I.e., when the market participant needs to pull the messages, it would be consistent he contacts the system operator.

In that regard, push-based mechanisms can be problematic in open or federated environments due to firewall restrictions,
endpoint unpredictability, and difficulties in guaranteeing delivery. A pull-based model simplifies client security,
logging, and retry logic.

## Decision Outcome

The market participant, when acting as a flexibility service provider, must initiate to retrieve the relevant
operational constraints and that it must follow.

The system operator will expose a standardized technical interface that enables secure, authenticated, and traceable
access to operating constraints.

### Consequences

* Good, because { a positive consequence, e.g., improvement of one or more desired qualities, … }
  ✅ Market participants can implement a uniform, secure retrieval pattern regardless of the system operator.
  ✅ Proper distribution that both DSO and FSP take their role in exchange for remedial action.
  ✅ Simplifies auditing, logging, and resilience through retries and acknowledgements.

* Bad, because { a negative consequence, e.g., compromising one or more desired qualities, … }
  ⚠ Requires the system operator to expose and maintain a reliable, up-to-date API.
  ⚠ Puts the responsibility on the market participant to poll or subscribe appropriately to changes in constraints.
  ⚠ Real-time changes in constraints may require efficient caching or notification mechanisms.

### Note

Emergency situations may allow system operators to initiate communications. This ADR permits system operators to send
emergency signals instructing FSPs to retrieve their operational constraints.
