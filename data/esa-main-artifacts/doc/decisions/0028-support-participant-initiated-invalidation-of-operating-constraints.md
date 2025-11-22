---
# Configuration for the Jekyll template "Just the Docs"
parent: Decisions
nav_order: 28
title: Support flexibility service provider-initiated invalidation of operating constraints
status: proposed
date: 2025-07-24

driver: Robert-Jan Peters <robert-jan.peters@alliander.com>
---

# Support Flexibility Service Provider Initiated Technical Invalidation of Operating Constraints

## Context and Problem Statement

When market participants acting as Flexibility Service Providers (FSPs) receive operating constraints—such as dispatch
instructions, setpoints, or contractual limits—these may become technically infeasible or invalid due to local
conditions, including equipment limitations, network constraints, or safety interlocks.

This is especially relevant in distributed operational environments, where changing conditions can render previously
accepted constraints non-viable. Without a formal mechanism to indicate invalidation, systems often rely on indirect
signals such as delayed telemetry or low-level rejection codes, which can cause inconsistent interpretations and
untraceable operational outcomes.

The system should therefore be designed to support a formal and verifiable invalidation process, allowing FSPs and
system operators to explicitly communicate when a constraint is no longer technically possible. Once an invalidation
message is issued and acknowledged, later actions should consistently reflect the updated operational
state—ensuring traceability, synchronized understanding between parties, and stability in decision-making processes.

## Decision Drivers

The following drivers are key factors that influence and justify the architectural decision process.

* Improve system safety and reliability during abnormal FSP conditions, to prevent unsafe or unstable grid behavior when
  FSPs cannot follow received instructions.
* Enable formal, auditable feedback for coordination, to provide structured feedback when operating constraints are
  invalidated to support coordinated actions.
* Ensure auditability of rejection and failure scenarios, to maintain transparency and accountability when instructions
  are rejected or fail.
* Eliminate ambiguous or silent failures, to avoid situations where FSP assumes compliance despite unreported
  invalidation.

## Considered Options

**Option 1: Structured invalidation requests by FSPs**

- FSPs submit formal invalidation messages referencing specific constraints
- Messages can include optional reason codes and diagnostics
- Invalidations are idempotent

**Option 2: Only implicit or technical rejection codes**

- FSPs report errors or reject constraints passively
- Limited auditability and weak process alignment

**Option 3: No invalidation support**

- FSPs silently ignore unfeasible constraints
- Operator assumes compliance if no alerts are received

## Decision Outcome

The outcome is to implement a formal, message-based invalidation mechanism, so FSPs can explicitly reject or invalidate
received operating constraints.

> Note: Implementation details for the control application logic to implement in the digitalization are not covered
> in this scope.

## Consequences

**Pros:**

- Improved error handling and system safety
- Transparent records of constraint rejections
- Enables feedback for future constraint revisions

**Cons:**

- Greater messaging complexity and state management
- Requires governance (e.g., rate limiting, reason validation)

## Implementation impact

- Invalidation messages must:
    - Reference the original constraint’s **unique identifier**
    - Include an optional **reason code** or human-readable explanation
    - Be **idempotent** (performing the same invalidation request multiple times should have the same effect as
      performing it once, making it safe to retry without causing unintended side effects)
- The system must acknowledge and log invalidations, with optional operator intervention

## More Information

### ENTSO-R Role Model

The [ENTSO-R Role Model](https://www.entsoe.eu/data/cim/role-models/) standardizes terminology for electricity market
roles and domains. It establishes unified vocabulary to support IT development and enable seamless process integration
between system operators and market participants.
