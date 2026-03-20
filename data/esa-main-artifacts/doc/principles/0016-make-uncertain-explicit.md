---
parent: Principles
nav_order: PCP.16
dct:
  identifier: urn:uuid:7a8b9c0d-1e2f-4a3b-4c5d-6e7f8a9b0c1d
  title: Make Uncertainty Explicit to Strengthen Decisions
  isVersionOf: proposed
  issued: 2025-10-27
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/principles/2025-10/0016-make-uncertain-explicit.html"
  versionInfo: "v1.0.0 (2025-10-27)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Principle: Make Uncertainty Explicit to Strengthen Decisions

## Statement  
Architectural designs must ensure that uncertainty in data is made explicit wherever it influences operational or strategic decisions. This includes expressing confidence, accuracy, or probability where applicable, so that decisions are informed by both the data and its limitations.

## Rationale  
In large-scale systems, data values are often exchanged without indicating their associated uncertainty leading to misinterpretation and overconfidence. By explicitly including uncertainty, systems promote better-informed decisions, reduce false trust in outputs, and improve the robustness of business processes. This principle supports transparency and acknowledges that even seemingly binary data may carry hidden uncertainty due to administrative or systemic limitations.

## Implications  
- Business applications may be designed to interpret and act on uncertainty metadata (e.g., confidence intervals, accuracy scores, probability distributions)  
- Data models and telemetry services must support and propagate uncertainty indicators  
- Reduces false confidence and improves trust in system outputs by acknowledging limitations  
- Supports multiple forms of uncertainty representation, from simple quality tags ('estimated', 'verified') to statistical confidence intervals or full probablistic distributions. 
- Exceptions may apply due to regulatory constraints or user experience considerations, but must be explicitly justified  
- Requires governance frameworks to define thresholds, representation standards, and audience-appropriate uncertainty communication strategies

<!-- exclude
## Scope  
Applies enterprise-wide, especially in domains where operational decisions are made based on data with inherent or contextual uncertainty (e.g., telemetry, AI-driven analytics, sensor data, administrative states).

## Related principles  
- Business-Driven Data Availability  
- Data is Designed for Need to Know  
- Business-Compliant Storage – Decision Snapshot Preservation
-->
