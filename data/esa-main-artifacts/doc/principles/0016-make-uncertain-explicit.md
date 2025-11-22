---
parent: Principles
nav_order: "0016"
title: Make Uncertainty Explicit to Strengthen Decisions
status: proposed
date: 2025-10-27

driver: Decision quality, operational robustness, trust in system outputs
#approvers: "...
contributors: Christian Heuer, Laurent van Groningen, Robert-Jan Peters
#informed: System architects, data engineers, business analysts, product owners
---

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
