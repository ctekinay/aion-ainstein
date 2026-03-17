---
parent: Decisions
nav_order: ADR.21
dct:
  identifier: urn:uuid:b8c9d0e1-f2a3-4b4c-5d6e-7f8a9b0c1d2e
  title: Use sign convention for current direction
  isVersionOf: accepted
  issued: 2025-07-17
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2025-07/0021-use-sign-convention-for-current-direction.html"
  versionInfo: "v1.0.0 (2025-07-17)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Use sign convention for current direction

## Context and Problem Statement

In modeling electrical systems—such as those governed by the IEC 61970/61968 CIM, IEC 61850, or proprietary distribution
management systems—there are multiple conventions for representing the direction of electrical quantities like current
and power.

A lack of a uniform sign convention leads to:

* Misalignment between systems, especially in power flow interpretation, leading to errors in data integration and
  exchange.
* Inconsistent modeling assumptions across engineering teams or software tools, complicating debugging and validation.
* Ambiguities in interpreting whether a component is consuming or supplying energy in reports, APIs, and logs.

As grid flexibility, bidirectional flows, and prosumer behavior become more important, clarity in flow direction becomes
mission-critical for reliability and transparency.

## Decision Drivers

The following drivers are key factors that influence and justify the architectural decision proces.

* Ensure consistent interpretation of energy-related concepts preventing misinterpretations of directionality,
  especially in multi-vendor and multi-domain environments.
* Enable automation, analytics, and decision-making at scale
* Ensure energy system reliability and stability
* Enable accurate forecasting and planning

## Considered Options

Two commonly used conventions are:

* Passive Sign Convention (PSC): Power is positive when flowing into a component (load absorbs power).
* Active Sign Convention (ASC): Power is positive when flowing out of a component (generator supplies power).

## Decision Outcome

The system will adopt the Passive Sign Convention:
* Power and current flows are positive into a device or subsystem.
* Generators have negative net power under normal operation (supplying power).
* Loads have positive net power under normal operation (absorbing power).
* Power export (e.g., to grid) is negative; import is positive.

## More Information
* [Used load flow convention in CIM](https://alliander.atlassian.net/wiki/x/GICbyQ)
* [Passive sign convention](https://en.wikipedia.org/wiki/Passive_sign_convention#The_convention)