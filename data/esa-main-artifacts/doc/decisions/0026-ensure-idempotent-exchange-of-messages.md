---
# Configuration for the Jekyll template "Just the Docs"
parent: Decisions
nav_order: 26
title: Ensure idempotent exchange of messages
status: proposed
date: 2025-07-24

driver: Robert-Jan Peters <robert-jan.peters@alliander.com>
---

# Ensure Idempotent Exchange of Messages

## Context and Problem Statement

When system operators and market participants in the role of party-connected-to-grid or flexibility service provider (
FSP),
exchange operating constraints, measurements, and validations—especially in power systems (e.g., power setpoints,
contractual-limits), where the process must be robust against communication failures.

This is important in distributed systems or systems with unreliable communication, where messages might be duplicated.
Repeated messages can occur due to retries, delayed acknowledgments, or the need for reconfirmation. Without safeguards,
these duplicates may cause unintended consequences. Treating messages as [**idempotent**](#clarification-of-idempotent)
helps prevent unintended side effects, like applying the same command multiple times and causing instability or errors.

The system should be designed so that if it receives the same message (like operating constraints) more than once, it
doesn't change anything after the first time. It should recognize that it's already processed that message and not apply
it again.

## Decision Drivers

The following drivers are key factors that influence and justify the architectural decision process.

* Ensure robustness under distribution conditions (retries, network delays); This prevents duplicate effects from
  retries or delays in IT network operation, ensuring consistent outcomes.
* Guarantee auditability and traceability in a regulated environment, and guarantees consistent, verifiable records for
  compliance and audits.
* To ensure transactional safety, energy systems must guarantee the integrity, consistency, and reliability of all data
  exchanges and operations, enabling trusted, verifiable, and fail-safe interactions across markets and control domains.
* Simplify error handling by enabling safe message deduplication. When IT systems can safely ignore or merge duplicated
  messages, error handling becomes simpler and more reliable.

## Considered Options

After analyzing the decision drivers and system requirements for ensuring reliable message exchange in power systems, we
evaluated two distinct approaches to handle message processing, particularly focusing on operating constraints,
measurements, and validations:

**Option 1: Require Idempotency for All Operating Constraint Exchanges**

- Each message includes a unique identifier (e.g., UUID or sequence number)
- Receiving systems track handled messages and ignore duplicates
- System stability and audit traceability are ensured

**Option 2: Allow Non-Idempotent Behavior (Current Practice)**

- Retries can inadvertently change system state
- Failure handling is more complex due to duplicate messages
- Reliability and compliance may be compromised

## Decision Outcome

The outcome is **Option 1** to enforce idempotent message processing for all system components handling operating
constraints.

## Consequences

**Positive:**

- Robustness in the face of retries and communication issues
- Clear and auditable system history
- Reduced operational risk from communication glitches

**Negative:**

- Slightly increased complexity for message tracking
- All messages require additional metadata (e.g., unique IDs)

## Implementation impact

- All system components must implement message tracking
- Message schemas will include mandatory unique identifier fields
- Storage requirements increase to maintain message history

## More Information

### ENTSO-R Role Model

The [ENTSO-R Role Model](https://www.entsoe.eu/data/cim/role-models/) standardizes terminology for electricity market
roles and domains. It establishes unified vocabulary to support IT development and enable seamless process integration
between system operators and market participants.

### IEC 61850 Idempotent

The IEC 61850 does not guarantee message idempotence at the protocol level. Idempotence has to be designed or enforced
in the control application logic or the middleware layer. Instead, it provides: sequence numbers and timestamps,
state-based models, and interaction patterns.

### Clarification of "Idempotent"

A process or operation is called **idempotent** if performing it multiple times has the same effect as performing it
once.

**Examples in this context:**

- If a system receives the same setpoint message multiple times (due to network retries), it applies the setpoint only
  once—later identical messages do not change the system state further.
- If an invalidation message is sent more than once, the system processes the first occurrence and ignores any exact
  duplicates.
- Deleting a constraint with the same identifier multiple times will only remove it once; later delete requests
  have no further effect.

**Examples of non-idempotent behavior:**

- If each repeated message caused the setpoint to be applied again, leading to incorrect values or system instability.
