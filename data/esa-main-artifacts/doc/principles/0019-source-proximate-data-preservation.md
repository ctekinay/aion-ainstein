---
parent: Principles
nav_order: PCP.19
dct:
  identifier: urn:uuid:0d1e2f3a-4b5c-4d6e-7f8a-9b0c1d2e3f4a
  title: Source-Proximate Data Preservation
  isVersionOf: proposed
  issued: 2025-11-12
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/principles/2025-11/0019-source-proximate-data-preservation.html"
  versionInfo: "v1.0.0 (2025-11-12)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Source-Proximate Data Preservation

## Statement

Original data required by business use-cases should be preserved as close to its source as feasible-preferably in an IT-capable layer near the origin-ensuring its highest attainable quality, integrity, and availability at the origin, to support both local and central decision-making. Where direct preservation at the source is not practical, the architecture must provide a proximate, reliable alternative without overburdening the originating device.

## Rationale

Preserving original data as close to its source as feasible is essential for operational resilience, auditability, and consistent decision-making based on authentic data. By ensuring that both local and central processes rely on the same high-quality, original data, the organization avoids the creation of conflicting "truths" and supports the principle of "do it right the first time." The location of usage (e.g., decentralized/local or centralized) is a key implication driver and has impact on the technological design of the solution. This approach empowers local autonomy while enabling robust central analytics, reducing the risk of systemic failures due to central outages. Although storing data locally introduces the risk of isolated data loss, it is generally less catastrophic than losing all centrally stored data at once. Therefore, appropriate mitigations should be in place to protect local datasets, ensuring continuity and trust in business-critical processes.

## Implications

- System designs must prioritize preserving original data in IT-capable layers near the source, such as substation servers or local gateways, rather than relying solely on central repositories
- Local data storage solutions must be robust, with appropriate backup and recovery mechanisms to mitigate the risk of isolated data loss
- Data quality, integrity, and uncertainty must be explicitly managed and documented at the point of origin, enabling both local and central decisions to be based on the same trusted dataset
- Local autonomy is supported, allowing operational decisions to be made at the edge even if central systems are unavailable
- Central analytics and enterprise processes must be designed to consume and integrate data from distributed, source-proximate repositories, ensuring consistency across the organization
- Architectural patterns that depend exclusively on central aggregation without preserving original data at the edge are discouraged, except where justified by technical or business constraints
- Trade-offs between local and central storage must be carefully evaluated, with clear justification for any deviation from this principle
