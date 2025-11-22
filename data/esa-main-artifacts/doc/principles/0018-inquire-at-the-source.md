---
parent: Principles
nav_order: 0018
title: Inquire at the Source
status: proposed
date: 2025-11-12
driver: Operational resilience, auditability, consistent decision-making based on authentic data
contributors: Laurent van Groningen, Robert-Jan Peters, Cagri Tekinay
---

<!-- Reasoning [CT]: I understand and agree with RJP's feedbacks.The original principle was more focused on WHERE to store data ("as close to its source as feasible"), which is the technical implementation concern (new Principle 0019). The governance aspect (who is authoritative) was implied but not explicitly stated, so I created the Principle 1, i.e., 0018-inquire-at-the-source, as per RJP's suggestion.

To Principle 0018 (Governance):

"essential for operational resilience, auditability, and consistent decision-making based on authentic data"
"avoids the creation of conflicting 'truths'"
"supports the principle of 'do it right the first time'"
Added: "clear accountability for data quality and integrity" (governance focus)

To Principle 0019 (Technical):

"Preserving original data as close to its source as feasible is essential for operational resilience, auditability, and consistent decision-making based on authentic data"
"By ensuring that both local and central processes rely on the same high-quality, original data, the organization avoids the creation of conflicting 'truths' and supports the principle of 'do it right the first time.'"
"This approach empowers local autonomy while enabling robust central analytics, reducing the risk of systemic failures due to central outages"
"Although storing data locally introduces the risk of isolated data loss, it is generally less catastrophic than losing all centrally stored data at once"
"Therefore, appropriate mitigations should be in place to protect local datasets, ensuring continuity and trust in business-critical processes"
Added from feedback: "The location of usage (e.g., decentralized/local or centralized) is a key implication driver and has impact on the technological design of the solution"

Reasoning: The original rationale discussed BOTH why source authority matters AND why local storage matters. I kept the full technical storage discussion in 0019 (old 0018), and extracted the governance/authority aspects for the new Principle 0018. I added the feedback about "location of usage" to P2's rationale as per RJP's request.

-->

# Inquire at the Source

## Statement

The origin of information is authoritative in determining what is correct, actual, and authentic. Business functions and services that produce data are the definitive source of truth for that data, and all consuming processes must defer to the originating source for authoritative information.

## Rationale

Establishing clear data ownership and authority at the source is essential for operational resilience, auditability, and consistent decision-making based on authentic data. By recognizing the originating business function as the authoritative source, the organization avoids the creation of conflicting "truths" and supports the principle of "do it right the first time." This governance approach provides clear accountability for data quality and integrity, ensuring that reliable and high-quality information is available for services and decision-making.

## Implications

- Business functions and services that originate data are designated as the authoritative source for that data
- Data governance models must explicitly identify the source of authority for each data element or dataset
- Consuming processes must query or receive data from the authoritative source, not from derived copies or aggregations, unless explicitly justified
- Data ownership and stewardship responsibilities must be clearly assigned to the originating business function
- Any transformation, aggregation, or derivation of source data must maintain traceability back to the authoritative source
- Conflicts between different versions of data must be resolved by deferring to the authoritative source
- Architectural patterns that create multiple conflicting sources of truth are discouraged

<!-- From this point on optional elements only. Feel free to remove. 
## Scope
Applies to all business-critical data generated at the edge or origin, including but not limited to measurement, telemetry, and operational event data, across both local and central systems.

## Related principles
- Make Uncertainty Explicit to Strengthen Decisions
- Business Specifications Driven Data Ownership
- Business-Compliant Storage – Decision Context Preservation
-->
