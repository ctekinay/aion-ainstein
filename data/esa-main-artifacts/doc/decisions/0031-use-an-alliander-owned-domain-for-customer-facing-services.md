---
parent: Decisions
nav_order: ADR.31
dct:
  identifier: urn:uuid:f8a9b0c1-d2e3-4f4a-5b6c-7d8e9f0a1b2c
  title: Use an Alliander-Owned Domain for Customer-Facing Services
  isVersionOf: proposed
  issued: 2025-12-30
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2025-12/0031-use-an-alliander-owned-domain-for-customer-facing-services.html"
  versionInfo: "v1.0.0 (2025-12-30)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Use an Alliander-Owned Domain for Customer-Facing Services

## Context and Problem Statement

External customers or market participants consume multiple Alliander business services through digital interfaces,
primarily APIs. For these consumers, it must be clear that Alliander is the authoritative and accountable provider of
these services, regardless of whether they are implemented internally or delivered via a SaaS provider.

When customer-facing APIs expose SaaS provider domain names, the visible ownership of the service becomes ambiguous.
This weakens trust, obscures accountability, and ties the external service identity to a specific vendor, rather than to
Alliander as the responsible organization.

This causes ambiguity for consumers regarding:

* Who owns or controls the API?
* Which organization is accountable for reliability, security, and governance of the interface?
* Whether the endpoint is an official Alliander service or a third-party dependency?

This situation conflicts with the expectation that business services offered by Alliander present a consistent and
recognizable digital identity, independent of internal sourcing or hosting models, and undermines governance, lifecycle
control, and customer confidence in Alliander's digital services.

## Decision Drivers

The following drivers are key factors that influence and justify the architectural decision process.

* Ensure clear service ownership and accountability to make it unambiguous for customers and market participants that
  Alliander is the authoritative provider of the digital services they consume.
* Preserve customer trust and recognizable digital identity to prevent confusion about responsibility, support, and
  legitimacy when services are delivered via third-party platforms.
* Maintain vendor-independent service continuity to ensure customer integrations remain stable and unaffected when
  underlying SaaS providers or hosting models change.
* Enable consistent governance and lifecycle management to apply uniform standards for API naming, versioning, security,
  and deprecation across all customer-facing services.
* Strengthen security and compliance posture, to retain control over DNS, certificates, and endpoint identity in
  alignment with Alliander's security and regulatory obligations.

## Considered Options

### Option 1 — Use an Alliander-owned domain

Expose all customer-facing APIs under an Alliander domain (e.g., api.alliander.nl), while internally routing traffic to
the SaaS provider using reverse proxying, API gateway mapping, or managed DNS configuration.

### Option 2 — Using the SaaS provider's domain

Keep the situation where customers interact directly with the vendor's domain name.

### Option 3 — Use the SaaS provider's domain but include Alliander as a path prefix

Expose APIs as https://vendorcloud.com/alliander/..., clarifying ownership only through URL structure.

## Decision Outcome

Alliander must ensure that customers interacting with its digital services can clearly recognise Alliander as the
authoritative source of the API. This requires that the externally visible API endpoints reflect Alliander's identity,
remain stable over time, and are not tied to the domain or branding of SaaS vendors.

The outcome is to use an Alliander-owned domain for exposing customer-facing digital business services.

### Consequences

Positive

* Clear ownership: customers recognize APIs as Alliander services.
* Vendor independence: SaaS providers become interchangeable.
* Improved certificate, DNS, and endpoint governance.
* Consistent API landscape for internal and external developers.
* Easier API lifecycle management and discoverability.

Negative

* Technical integration effort is required to configure routing and custom domain support.
* Dependency on SaaS provider capabilities for custom domain mapping.
* Additional operational responsibility for Alliander (certificate renewal, routing config).

## Pros and Cons of the Options

### Option 1 — Alliander-owned domain

Positive:

* Aligns external API identity with Alliander's brand and trust responsibility.
* Ensures long-term vendor independence: Alliander controls DNS, certificates, and the API namespace.
* Allows seamless vendor switching without breaking customer integrations.
* Centralized governance of API standards, naming, and lifecycle.
* Improved security posture with company-managed certificates and TLS termination.
* Consistent developer experience across all Alliander APIs.

Negative:

* Requires additional configuration effort (reverse proxy, API gateway mapping).
* Increase the complexity of operational tasks.
* Some SaaS platforms may require additional configuration or support to enable custom domains.

### Keep SaaS provider's domain

Positive:

* Zero implementation effort.
* Uses the SaaS platform's native domain configuration.

Negative:

* Customers may not recognize the service endpoint as owned by Alliander, reducing trust.
* High vendor lock-in: changing SaaS provider forces customers to reconfigure endpoints.
* Loss of control over naming, routing, and certificate lifecycle.
* Inconsistent API landscape across Alliander's digital channels.
* Potential non-compliance with internal security and governance rules.
* Increase the risk of vendor outages due to SaaS provider downtime.

### Option 3 — Use vendor domain with Alliander path prefix

Positive:

* Slightly better branding than no reference at all.
* Minimal configuration overhead.

Negative:

* Still exposes the vendor's domain as the primary identity.
* Does not resolve vendor lock-in.
* Still confuses customers about actual ownership.
* Inconsistent with enterprise API strategy.

## More Information

