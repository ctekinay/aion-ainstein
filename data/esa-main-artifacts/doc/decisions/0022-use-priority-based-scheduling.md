---
parent: Decisions
nav_order: ADR.22
dct:
  identifier: urn:uuid:c9d0e1f2-a3b4-4c5d-6e7f-8a9b0c1d2e3f
  title: Use priority based scheduling
  isVersionOf: proposed
  issued: 2025-07-21
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2025-07/0022-use-priority-based-scheduling.html"
  versionInfo: "v1.0.0 (2025-07-21)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Use priority based scheduling

## Context and Problem Statement

Scheduling plays a critical role in operating demand response (DR) products, especially within energy systems that must
coordinate flexible loads, distributed energy resources (DER), or energy storage.

From a system operator perspective (e.g., DSO), scheduling and prioritization are core to the operational process of
capacity management. Priorities must be clearly defined and unambiguous to ensure grid safety. This is especially
important when schedules from multiple sources (e.g., DSO and third parties) are aggregated. Misinterpretation of
priority levels could lead to unsafe operational conditions.

## Decision Drivers

The following drivers are key factors that influence and justify the architectural decision proces.

* Ensure regulatory compliance (e.q. EU / NL network codes)
* Ensure system reliability and stability for operating capacity management, while enabling market participation in grid
  balancing and congestion management
* Ensure compliance and consistency with international standards
* Ensure system scalability to handle large amount of schedules
* Ensure performance to support real-time scheduling decisions

## Considered Options

Priority mechanisms are used in multiple international standards for scheduling and event coordination in power and
energy systems:

* IEC 61850-90-10: Defines models for scheduling and explicitly specifies priority handling within a Schedule
  Controller. This standard aligns with real-time system practices and includes safe-mode considerations.
* IEC 62325: Refers to priorities in market communication but does not mandate specific behavior, leaving interpretation
  to the implementer.
    * IEC 62746-10-1: Part of IEC 62325 series, focussing on the demand-side energy management, DER control, and DR (
      Demand Response) and introduces 'priority of use' to describe how flexibility loads and DERs are ranked for
      control actions.

## Decision Outcome

The IEC 61850-90-10 is adopted as priority-based scheduling model as the basis for scheduling across all relevant
business services, such as flexibility activation, load control, and capacity allocation.

Specifically:

* The Schedule Controller will interpret and manage priorities according to IEC 61850-90-10.
* Priorities will be modeled numerically, with higher numbers indicating higher priority; to avoid
  misinterpretation of priority values in combination with third parties and provide a deterministic gracefully
  reduction of load/generation.
* A default priority of 0 is defined as no priority; to ensure safe default behavior.
* System Operator originated schedules will always take precedence over those from third parties.
* The architecture will enforce range validation (e.g., only priorities above a threshold such as 150 can only be issued
  by a System Operator).
* Priority conflicts will be resolved within the business function layer using explicit, deterministic rules.

### Consequences

Positive

* Standards Alignment: Fully aligns with IEC 61850 scheduling model.
* Interoperability: Avoids inconsistencies across implementations, especially between System Operator and third-party systems.
* Safety and Control: Clear priority semantics prevent conflicting schedules that could endanger grid security.
* Extensibility: The model supports future evolution, such as additional priority levels or dynamic override mechanisms.
* Clarity: Reduces ambiguity in multi-party systems, consistent with domain-driven architecture principles.

Negative

* Complexity: Requires that all actors interpret and enforce priority semantics uniformly.
* Compatibility: Existing implementations based on IEC 62325 and subsidiaries may require adaptation.
* Governance: Requires agreement on priority ranges and allocation across actors, possibly needing regulatory support.

## More Information

*  The decision matches NetBeheer Nederland RTIv2 schedules concept.