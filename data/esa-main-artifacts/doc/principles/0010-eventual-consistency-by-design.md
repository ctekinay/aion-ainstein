---
parent: Principles
nav_order: PCP.10
dct:
  identifier: urn:uuid:1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d
  title: Eventual Consistency by Design
  isVersionOf: proposed
  issued: 2025-10-24
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/principles/2025-10/0010-eventual-consistency-by-design.html"
  versionInfo: "v1.0.0 (2025-10-24)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Principle: Eventual Consistency by Design

## Statement  
In distributed systems operated by a DSO, full consistency across components is rarely feasible due to scale and latency. The architecture is therefore intentionally designed for eventual consistency, allowing temporary divergence in data and system states that converge over time.

## Rationale  
Partitioning in distributed systems is often a given—especially in large-scale, multi-node environments such as those operated by a DSO. Availability is a critical requirement for operational continuity, and therefore, consistency must be relaxed. This principle aligns with the **CAP theorem**, which states that in the presence of network partitions, a system must choose between consistency and availability.

By prioritizing availability and tolerating temporary inconsistencies, the architecture ensures:
- **Operational resilience**, allowing systems to continue functioning even under degraded network conditions.
- **Scalability**, enabling the system to grow and adapt without being constrained by synchronous data dependencies.
- **Responsiveness**, supporting real-time decision-making based on “last known good” data while ensuring eventual convergence.

Eventual consistency allows systems to operate asynchronously while still converging toward a coherent state, enabling business processes to continue without interruption and supporting realistic expectations for data accuracy and timeliness.

## Implications  
- Manage sufficient corporate awareness that the acceptable levels of inconsistency are context-aware.
  E.g. in Grid Operations, switch commands require extreme-near-zero inconsistency;
  for connectivity data a slightly higher tolerance may be acceptable and
  integrations with external systems, especially those not under direct control, inconsistency levels may be significantly higher and must be explicitly managed.
- Business processes must tolerate temporary inconsistencies and be resilient to delayed updates, ensuring continuity even when data is not immediately synchronized.  
- Decision-making may rely on “last known good” data, requiring clear timestamping, data provenance, and confidence indicators to support trust in asynchronous states.  
- SLAs and KPIs should reflect convergence time rather than real-time accuracy, shifting performance metrics toward eventual correctness and system stability.  
- Use-case design must embrace asynchronous flows, with business development setting realistic expectations for data latency and update propagation.  
- Architectural patterns such as event sourcing and CQRS may be favored to support asynchronous updates and eventual consistency across bounded contexts.  
- Monitoring and observability must track convergence behavior, including lag metrics, reconciliation success rates, and divergence windows.  
- Testing strategies must include scenarios for delayed consistency, such as eventual propagation, conflict resolution, and rollback handling.  
- Data consumers must be designed to handle stale or partial data, with fallback logic or user experience patterns that mitigate confusion or error.  

<!-- integrate later
## Scope  
Applies to all distributed systems within the DSO landscape, especially those involving asynchronous data flows, external integrations, and operational telemetry.

## Related principles  
- Design for Resilience  
- Timestamp Everything  
- Loose Coupling over Tight Integration 
-->
