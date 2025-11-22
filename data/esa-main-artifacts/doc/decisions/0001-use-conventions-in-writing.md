---
parent: Decisions
nav_order: 1
status: accepted
date: 2025-06-01
approvers: "Energy System Architecture: Robert-Jan Peters, Laurent van Groningen"
consulted: René Tiesma (BBN architecture), Robbert van Waveren (ART-SO solution architecture)"
informed: "BBN architecture, ART-SO solution architecture"
---

# What conventions to use in writing ADRs?

## Context and Problem Statement

The ADR are defined in typical text files, then what ADR conventions should be used.
Which format and structure should these records follow?

## Decision Outcome

### Template Convention
For new Architectural Decision Records (ADRs), use this templates and ajust if required as a starting point:
this [adr-template.md](adr-template.md) has all sections, with explanations about them.

### Language Convention
The standard language for writing an ADR is US english.

### File Name Conventions
The ESA file name convention:
* The name has a present tense imperative verb phrase. This helps readability and matches our commit message format.
* The name uses lowercase and dashes (same as this repo). This is a balance of readability and system usability.
* The extension is markdown. This can be useful for easy formatting.

### Suggestions for writing good ADRs
Characteristics of a good ADR:
* Rationale: Explain the reasons for doing the particular AD. This can include the context (see below), pros and cons of various potential choices, feature comparions, cost/benefit discussions, and more.
* Specific: Each ADR should be about one AD, not multiple ADs.
* Timestamps: Identify when each item in the ADR is written. This is especially important for aspects that may change over time, such as costs, schedules, scaling, and the like.
* Immutable: Don't alter existing information in an ADR. Instead, amend the ADR by adding new information, or supersede the ADR by creating a new ADR.

Characteristics of a good "Context" section in an ADR:
* Explain your organization's situation and business priorities.
* Include rationale and considerations based on social and skills makeups of your teams.
* Include pros and cons that are relevant, and describe them in terms that align with your needs and goals.

Characteristics of good "Consequences" section in an ADR:
* Explain what follows from making the decision. This can include the effects, outcomes, outputs, follow ups, and more.
* Include information about any subsequent ADRs. It's relatively common for one ADR to trigger the need for more ADRs, such as when one ADR makes a big overarching choice, which in turn creates needs for more smaller decisions.
* Include any after-action review processes. It's typical for teams to review each ADR one month later, to compare the ADR information with what's happened in actual practice, in order to learn and grow.

A new ADR may take the place of a previous ADR:
* When an AD is made that replaces or invalidates a previous ADR, then a new ADR should be created


## More Information
* [Architectural Decision Records for MADR](https://github.com/adr/madr/docs/decision)
