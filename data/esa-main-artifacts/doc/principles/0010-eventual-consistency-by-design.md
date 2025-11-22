---
parent: Principles
nav_order: "010"
title: Eventual Consistency by Design
status: Proposed
date: 2025-10-24
driver: scalability, operational resilience, distributed system design, CAP theorem
approvers: ...
contributors: Christian Heuer, Laurent van Groningen, Robert-Jan Peters
#informed: proposed: Grid Operations, Data Office, Enterprise Architecture, Strategic Data Sharing Coalition
---

<!-- markdownlint-disable-next-line MD025 -->

# Principle: Eventual Consistency by Design

## Statement

The principle of eventual consistency allows temporary divergence in data and system states that gradually converge over
time to a consistent and reliable global view.

A distributed ICT system is designed so that its computing, data, and control components operate across multiple,
interconnected nodes rather than relying on a single centralized system.

The reason for such a design is to achieve scalability, reliability, flexibility, and resilience — capabilities that are
critical for modern energy system operations and cannot be efficiently provided by a monolithic architecture.

For a Distribution System Operator (DSO), the energy grid is inherently distributed: assets, sensors, and control
systems are geographically dispersed and must interact in different time-intervals. A distributed ICT architecture
reflects this physical and operational reality.

## Rationale

In large-scale distributed systems operated by a DSO, full consistency across all components is rarely possible due to
the limits imposed by network latency, volume of data, and operational scale.

Therefore, the architecture is intentionally designed for eventual consistency — allowing temporary divergence between
local data stores or system states, with mechanisms ensuring that they converge over time to a coherent global view.
Availability is a critical requirement for operational continuity, and therefore, consistency must be relaxed. This
principle aligns with the **CAP theorem**, which states that in the presence of network partitions, a system must choose
between consistency and availability.

By prioritizing availability and tolerating temporary inconsistencies, the usage of this principle ensures:

- **Operational resilience**, allowing systems to continue functioning even under degraded network conditions.
- **Scalability**, enabling the system to grow and adapt without being constrained by synchronous data dependencies.
- **Responsiveness**, supporting real-time decision-making based on “last known good” data while ensuring eventual
  convergence to a coherent global view.

Eventual consistency allows systems to operate asynchronously while still converging toward a coherent state, enabling
business processes to continue without interruption and supporting realistic expectations for data accuracy and
timeliness.

## Implications

To uphold the 'eventual-consistency by design' principle and ensure confidentiality by design, the following
architectural and governance implications apply:

- Manage sufficient corporate awareness that the acceptable levels of inconsistency are context-aware.
  E.g. in Grid Operations, switch commands require extreme-near-zero inconsistency;
  for connectivity data a slightly higher tolerance may be acceptable, and integrations with external systems,
  especially those not under direct control, inconsistency levels may be significantly higher and must be explicitly
  managed.
- Business processes must tolerate temporary inconsistencies and be resilient to delayed updates, ensuring continuity
  even when data is not immediately synchronized.
- Decision-making may rely on “last known good” data, requiring clear timestamping, data provenance, and confidence
  indicators to support trust in asynchronous states.
- Service Level Agreements (SLA) and Key Performance Indicators (KPI) should reflect convergence time rather
  than real-time accuracy, shifting performance metrics toward eventual correctness and system stability.
- Use-case design must embrace asynchronous flows, with business development setting realistic expectations for data
  latency and update propagation.
- Architectural patterns such as event sourcing and 'Command Query and Responsibility Segregation' (CQRS) may be favored
  to support asynchronous updates and eventual consistency across bounded contexts.
- Monitoring and observability must track convergence behavior, including lag metrics, reconciliation success rates, and
  divergence windows.
- Testing strategies must include scenarios for delayed consistency, such as eventual propagation, conflict resolution,
  and rollback handling.
- Data consumers must be designed to handle stale or partial data, with fallback logic or user experience patterns that
  mitigate confusion or error.
- Resilient distributed systems use robust data backup and recovery mechanisms to protect against data loss or
  corruption.

## More Information

* [Event Sourcing](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)
* [Command Query Responsibility Segregation (CQRS)](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs)

<!-- integrate later
## Scope  
Applies to all distributed systems within the DSO landscape, especially those involving asynchronous data flows, external integrations, and operational telemetry.

## Related principles  
- Design for Resilience  
- Timestamp Everything  
- Loose Coupling over Tight Integration 
-->
