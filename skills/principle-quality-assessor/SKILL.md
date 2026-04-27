---
name: principle-quality-assessor
description: "Quality assessment criteria and improvement recommendations for architecture principles (Enterprise and Architecture level)"
---

# Quality Assessment of Principles (Enterprise & Architecture)

  

## Purpose

This instruction enables an agent to **assess the quality of a Principle**—independent of whether it is an **Enterprise Principle** or an **Architecture Principle at any level**—and to **formulate concrete improvement recommendations**.

  

The instruction:

- Preserves the original **decision logic** (is this a principle or not)

- Extends it into a **general quality assessment**

- Prevents **policies, standards, constraints, and design rules** from being misclassified as principles

  

---

  

## Core Definition (TOGAF-aligned)

> A principle is an enduring, normative statement that guides decision-making 

> at a defined level of abstraction; it does not prescribe execution or a single solution.

  

---

  

## Required Decision Gate (must be passed first)

  

Before quality is assessed, the statement **MUST qualify as a principle**.

  

Reject the statement as a principle if **any** of the following apply:

- It prescribes execution or implementation

- It is directly testable against a single solution

- It enforces one specific technology, standard, or pattern

- It leaves no room for architectural choice

  

> If rejected, classify instead as: policy, standard, constraint, requirement, or design rule.

  

---

  

## Quality Assessment Structure

  

Once the statement qualifies as a principle, assess it against the dimensions below.

  

Each dimension must result in:

- **Assessment**: Adequate / Weak / Deficient 

- **Recommendation**: Concrete improvement guidance

  

---

  

## 1. Minimal Content Completeness

  

### 1.1 Name

**Assessment criteria**

- Represents the essence of the principle

- Easy to remember

- Free of technology references

- Avoids vague or weak verbs and qualifiers

  

**Avoid**

- Ambiguous terms: *support*, *consider*, *open*, *avoid*

- Management buzzwords without substance

- Unnecessary adjectives or adverbs (fluff)

  

**Recommendation guidance**

- Reduce to the core norm or value

- Prefer short, assertive phrasing

  

---

  

### 1.2 Statement

**Assessment criteria**

- Succinct and unambiguous

- Expresses a single fundamental rule

- Free of conditional or procedural language

  

**Quality test**

> Can two architects interpret this statement in the same way 

> without additional explanation?

  

**Recommendation guidance**

- Remove examples and implementation hints

- Eliminate “how” language; retain only “what must hold”

  

---

  

### 1.3 Rationale

**Assessment criteria**

- Explains *why* the principle matters in business terms

- Makes the value explicit (risk, cost, agility, quality, compliance, etc.)

- Describes interaction with other principles

  

**For Architecture Principles specifically**

- Explains how the principle supports decision-making in trade-offs

- Indicates when this principle may outweigh others

  

**Recommendation guidance**

- Replace technical justification with business outcomes

- Explicitly describe balancing with competing principles

  

---

  

### 1.4 Implications

**Assessment criteria**

- Describes consequences for business and IT

- Identifies required capabilities, effort, cost, or change

- Makes impact tangible without prescribing solutions

  

**Key test**

> Can the reader clearly answer: “How does this affect me?”

  

**Recommendation guidance**

- Make impacts explicit, not judgmental

- Separate *implications* from *requirements or rules*

  

---

  

## 2. Quality Criteria for a Principle Set

  

Assess the principle in the context of the **entire set**, not in isolation.

  

---

  

### 2.1 Understandable

- Intention is clear to non-specialist stakeholders

- Violations are recognizable

  

**Improve by**

- Simplifying language

- Removing implicit assumptions

  

---

  

### 2.2 Robust

- Supports consistent decision-making in complex situations

- Enables derivation of enforceable policies and standards

  

**Improve by**

- Tightening vague formulations

- Clarifying decision boundaries

  

---

  

### 2.3 Complete

- Addresses a meaningful aspect of information, technology, or architecture

- Is not redundant with other principles

  

**Improve by**

- Merging overlapping principles

- Removing principles with marginal scope or value

  

---

  

### 2.4 Consistent

- Does not contradict other principles

- Allows balanced interpretation across the set

  

**Improve by**

- Adjusting wording to avoid absolutes

- Explicitly documenting precedence in the rationale

  

---

  

### 2.5 Stable

- Designed to endure multiple architecture cycles

- Changeable only through formal governance

  

**Improve by**

- Removing references to current organizational or technical states

- Separating temporary intent into policies or roadmaps

  

---

  

## 3. Level Classification (after quality assessment)

  

Determine the level **only after** quality is confirmed.

  

- **Enterprise Principle**

  - Guides organization-wide values, direction, or strategic choices

  - Informs and constrains architecture principles

  

- **Architecture Principle**

  - Guides architectural decisions and governance

  - Derived from enterprise principles

  

> The quality criteria remain identical; only scope differs.

  

---

  

## 4. ArchiMate Modeling Guidance

  

- Model all principles as:

  - `Principle` (Motivation Extension)

  

- Distinguish levels via:

  - Naming conventions (e.g. EP-xx, AP-xx)

  - Tags (e.g. `principleLevel`)

  - Separate viewpoints

  

- Do NOT model the following as principles:

  - Policies

  - Standards

  - Constraints

  - Design rules

  

---

  

## Final Rejection Rule (non-negotiable)

> If a statement prescribes execution, is directly enforceable, 

> or mandates a single solution, it is **NOT a principle**, 

> regardless of intent or labeling.

  

---

  

## End of Instruction