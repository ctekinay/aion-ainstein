---
name: principle-generator
description: "Principle generation following TOGAF-aligned quality criteria and template structure"
---

# Generating Architecture Principles

## Purpose

Generate high-quality architecture or enterprise principles using the established
template. Every generated principle must pass the quality gate before being presented.

Use the knowledge base to retrieve related existing principles before generating —
avoid redundancy and ensure consistency with the existing principle set.

---

## Output Template

Generate the principle as a markdown document with this exact structure:

```markdown
## [Principle Name]

**Statement**
[One concise, unambiguous sentence. No conditionals. No implementation details. No "how" language.]

**Rationale**
[Why this principle matters in business terms. What risk, cost, agility, quality, or compliance concern it addresses. NOT a technical justification.]

**Implications**
- [Concrete consequence for business or IT — what changes, what capabilities are required]
- [Another consequence]
- [At least one more]

**Level**: Enterprise Principle / Architecture Principle
**Owner**: [owning group — e.g. ESA, EA, NB-EA, BA, DO]
```

---

## Quality Gate (apply before presenting output)

Before presenting, verify the generated principle meets ALL of the following.
If it fails any gate, revise or explain why it cannot be expressed as a principle.

### Gate 1 — Is it actually a principle?

Reject if ANY of the following apply:
- It prescribes execution or implementation steps
- It is directly testable against a single solution
- It enforces one specific technology, standard, or pattern
- It leaves no room for architectural choice

If rejected: classify as **policy**, **standard**, **constraint**, or **design rule** instead, and explain why.

### Gate 2 — Statement quality

- Single fundamental rule
- Unambiguous (two architects read it the same way without explanation)
- Free of conditional or procedural language
- No fluff, no management buzzwords, no weak verbs (*support*, *consider*, *avoid*)

### Gate 3 — Rationale quality

- Business outcome framing (not technical justification)
- Makes the value explicit (risk, cost, agility, compliance, etc.)
- For Architecture Principles: explains how it supports trade-off decisions

### Gate 4 — Implications quality

- Describes consequences for business AND IT
- Makes impact tangible without prescribing solutions
- Reader can clearly answer: "How does this affect me?"

### Gate 5 — Level determination

Explicitly determine and state the level:
- **Enterprise Principle** — guides organisation-wide values, direction, or strategic choices; informs and constrains architecture principles
- **Architecture Principle** — guides architectural decisions and governance; derived from enterprise principles

---

## Consistency Check

Before finalising, verify:
- The generated principle does not duplicate an existing principle in the KB
- It does not contradict existing principles (if tension exists, note it explicitly)
- The naming follows the existing set (concise, assertive, technology-free)
