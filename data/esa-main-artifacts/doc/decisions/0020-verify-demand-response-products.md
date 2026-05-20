---
parent: Decisions
nav_order: ADR.20
dct:
  identifier: urn:uuid:a7b8c9d0-e1f2-4a3b-4c5d-6e7f8a9b0c1d
  title: Verify Demand/Response Products
  isVersionOf: accepted
  issued: 2025-04-09
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2025-04/0020-verify-demand-response-products.html"
  versionInfo: "v1.0.0 (2025-04-09)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Verify Demand/Response Products

## Context and Problem Statement

In operating demand response (D/R) products, a flexibility provider adjusts its energy in-feed or withdrawal patterns
based on the exchanged operating constraints. Examples of D/R products include automated load shifting, peak shaving,
frequency regulation, and real-time price-responsive demand. However, some current D/R products operate with stationary
properties on time, volume or a combination of both.

Verifying whether the provider adheres to these constraints is an integral part of process operation capacity
management, particularly within the context of energy systems, and demand-side flexibility management.

This verification process typically involves:

* Comparing actual vs. expected execution of the operating constraints
* Triggering alerts or penalties if deviations occur
* Monitoring real-time data

Who is responsible to execute the verification process of the different D/R products?

## Decision Drivers

The following drivers are essential in the "operate capacity management" process:

* Ensure system reliability and stability
* Maintain contractual and regulatory compliance
* Enable accurate forecasting and planning

## Considered Options

The following departments or processes are options to perform the verification process:

* Market Services (MD), it performs a customer validation and the allocation/reconciliation for fix-firm products.
* System Operation (S), it performs the verification of non-stationary D/R products.

## Decision Outcome

The verification of Demand/Response products is operated by the System Operation department, because:

* the stationary D/R products on time and volume impacts the available capacity
* the verification is a key operational activity within capacity management, especially in the GaaS system that rely on
  the D/R products of flexible resources.

## More Information
* IEC TR 62746-2 