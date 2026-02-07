# Energy System Architects (ESA) - Main Artifacts for Target Architecture

[![Alliander](https://img.shields.io/badge/maintained%20by-Alliander-orange.svg)](https://www.alliander.com)

A comprehensive repository for core Energy System Architecture artifacts including Architecture Decision Records (ADRs), Architecture Principles, and foundational documentation that collectively describe the ESA-main Target Architecture initiative driven by the Energy System Architects (ESA) group at Alliander.

## Table of Contents

- [About](#about)
- [What is ESA-main Target Architecture?](#what-is-esa-main-target-architecture)
- [Repository Purpose](#repository-purpose)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Architecture Decision Records (ADRs)](#architecture-decision-records-adrs)
- [Architecture Principles](#architecture-principles)
- [Decision Approval Records](#decision-approval-records)
- [Contributing](#contributing)
- [Related Initiatives and Repositories](#related-initiatives-and-repositories)
- [Contact](#contact)

## About

This repository is maintained by the **Energy System Architects (ESA)** group at Alliander and serves as the central location for core architectural artifacts that define and document the ESA-main Target Architecture initiative.

**Repository Naming Convention:**
- **esa**: Energy System Architects group (owning group)
- **main**: ESA-main target architecture (initiative name)
- **artifacts**: Core architectural documentation and decision records (content type)

## What is ESA-main Target Architecture?

![ESA Initiatives Overview](doc/images/Overview_ESA_Delivery_Readme.gif)

**ESA-main Target Architecture** is the foundational initiative focused on creating a future AI-embracing and resilient energy system architecture.

**What**: Future AI embracing and resilient energy system architecture.

**Why**: We strongly believe that an incremental architecture is not the right answer to managing 3 (energy-, AI- and geopolitical) transitions at once.

**How**: Understanding the AI-transition from AIon that delivers on the energy transition and embedding the results in the main AI based target architecture. In parallel test resilience patterns with external institutes with infrastructure in scope.

This initiative provides the overarching target architecture that guides both current transformation efforts and future state architecture development across the organization.

## Repository Purpose

This repository serves multiple critical functions:

1. **Decision Documentation**: Capturing important architecture decisions through ADRs that address functional and non-functional requirements at the Energy System Architecture level
2. **Principle Definition**: Establishing and maintaining architecture principles that guide design and implementation decisions
3. **Approval Tracking**: Maintaining decision approval records that document the governance process and approvals for each artifact
4. **Target Architecture Foundation**: Documenting the foundational elements of the ESA-main Target Architecture that enables managing the three concurrent transitions (energy, AI, and geopolitical)

The artifacts in this repository provide the reasoning and persuasive power to explain which changes are needed, why they matter, and how they should be implemented.

## Repository Structure

```
esa-main-artifacts/
├── doc/
│   ├── decisions/                    # Architecture Decision Records (ADRs)
│   │   ├── NNNN-*.md                 # ADR artifacts (NNNN-descriptive-title.md)
│   │   ├── NNNND-*.md                # ADR decision approval records (NNNND-descriptive-title.md)
│   │   ├── adr-template.md           # Template for new ADRs
│   │   ├── adr-decision-template.md  # Template for ADR approval records
│   │   └── ...
│   ├── principles/                   # Architecture Principles
│   │   ├── NNNN-*.md                 # Principle artifacts (NNNN-descriptive-title.md)
│   │   ├── NNNND-*.md                # Principle decision approval records (NNNND-descriptive-title.md)
│   │   ├── principle-template.md           # Template for new principles
│   │   ├── principle-decision-template.md  # Template for principle approval records
│   │   └── ...
│   ├── images/                       # Diagrams, screenshots, and visual assets
│   └── index.md                      # Architectural Artifact Registry
└── README.md                         # This file
```

## Getting Started

### Prerequisites

- Access to Alliander internal systems
- Understanding of enterprise architecture principles
- Familiarity with the ESA initiatives ecosystem (A4A, AIon, AInstein)
- Basic knowledge of Markdown formatting

### Installation

```bash
# Clone the repository
git clone https://github.com/Alliander/esa-main-artifacts.git

cd esa-main-artifacts
```

### Usage

Browse the repository structure to find relevant artifacts:

- **For Architecture Decision Records**: Check the `doc/decisions/` directory
- **For Architecture Principles**: See the `doc/principles/` directory
- **For ADR templates**: Use `doc/decisions/adr-template.md` and `doc/decisions/adr-decision-template.md`
- **For Principle templates**: Use `doc/principles/principle-template.md` and `doc/principles/principle-decision-template.md`
- **For visual assets**: Browse the `doc/images/` directory

## Architecture Decision Records (ADRs)

### What is an ADR?

An Architecture Decision Record (ADR) is a document that captures an important architecture decision made that addresses a functional or non-functional requirement along with its context and consequences at the level of Energy System Architecture.

This repository offers a solution to record any decision that is important for the working and operation of the energy system. While there are debates about what constitutes an architecturally-significant decision, we believe any important decision should be captured in a structured way.

### ADR Structure

Each ADR consists of two files:
- **Artifact file** (`NNNN-descriptive-title.md`): Contains the decision content, context, and rationale
- **Decision approval record** (`NNNND-descriptive-title.md`): Tracks the governance and approval history

### When Should an ADR be Created?

An ADR for the Energy System should be created:

- When the decision will impact the working/scope of the whole Energy System
- When the decision will be hard to reverse or will incur high costs
- When the decision establishes patterns or precedents for future work
- When the decision involves trade-offs between competing concerns

### How are ADRs Governed?

**Branching Strategy:**
When starting a new ADR, create a branch named based on the title. Use `XXXX` as a placeholder for the number in the filename (e.g., `XXXX-my-new-decision.md`). A permanent number will be assigned when the ADR is merged to the main branch.

**Review Process:**
Additions, changes and deletion of ADRs at Energy System Architecture level are done by the Energy System Architecture group with the 4-eyes principle and in a trackable way. All changes are created in new branches in GitHub and approval status is assigned by another Energy System Architect via a pull-request.

For more details, see [ADR 0002: Use DACI for decision making process](./doc/decisions/0002-use-DACI-for-decision-making-process.md)

## Architecture Principles

Architecture Principles are fundamental statements that guide architecture decisions and provide a framework for evaluating design choices. They help ensure consistency and alignment across the organization's architecture.

### Structure of Principles

Each principle document should include:
- **Principle Statement**: Clear, concise declaration
- **Rationale**: Why this principle matters
- **Implications**: What this means for design and implementation
- **Related ADRs**: Links to decisions that implement or are guided by this principle

### Principle Ownership

Principles can be owned by different groups within Alliander:
- **ESA** (System Operations - Energy System Architecture Group) - Technical architecture principles
- **BA** (Alliander Business Architecture Group) - Business architecture principles
- **DO** (Alliander Data Office) - Data governance principles

## Decision Approval Records

Each ADR and Principle has a corresponding **Decision Approval Record** file (`NNNND-*.md`) that tracks the governance history.

### Record Structure

Decision approval records contain numbered entries in **descending order** (newest first):

```markdown
## 2. [Latest record - e.g., External Collaboration or Update]
| Name                  | Value                                    |
|-----------------------|------------------------------------------|
| Version of ADR        | v1.0.1 (YYYY-MM-DD)                      |
| Decision              | [Acknowledged | Accepted | Revoked]      |
| Decision date         | YYYY-MM-DD                               |
| Driver (Decision owner)| [Owner group]                           |
| Remarks               |                                          |

**Approvers**
| Name | Email | Role | Comments |
|------|-------|------|----------|

---
## 1. Creation and [ESA/BA/DO] [Approval/Acceptance] of [ADR.N/PCP.N]
...
```

### Decision Status Types

- **Acknowledged**: Decision has been reviewed and acknowledged
- **Accepted**: Decision has been formally approved and is now active
- **Revoked**: Decision has been revoked and is no longer valid

### Driver (Decision Owner) Groups

| Group | Abbreviation | Action Term |
|-------|--------------|-------------|
| System Operations - Energy System Architecture Group | ESA | Approval |
| Alliander Business Architecture Group | BA | Acceptance |
| Alliander Data Office | DO | Acceptance |

### DACI Framework

Decision records follow the DACI framework:
- **Driver**: The person who initiates, coordinates, and executes the decision-making process
- **Approver**: The person(s) with authority to make the final decision
- **Contributors**: Subject matter experts who provide input (optional section)
- **Informed**: Stakeholders who need to be kept in the loop (optional section)

## Contributing

We welcome contributions from the ESA team and other Alliander colleagues. Please:

1. Create a feature branch (`git checkout -b feature/new-adr` or `git checkout -b feature/new-principle`)
2. For ADRs:
   - Use the ADR template (`doc/decisions/adr-template.md`)
   - Use `XXXX` as a placeholder in the filename (e.g., `XXXX-my-decision.md`)
   - Create a corresponding decision approval record using `doc/decisions/adr-decision-template.md` (e.g., `XXXXD-my-decision.md`)
3. For Principles:
   - Use the principle template (`doc/principles/principle-template.md`)
   - Use `XXXX` as a placeholder in the filename
   - Create a corresponding decision approval record using `doc/principles/principle-decision-template.md`
4. Update relevant documentation
5. Commit your changes (`git commit -am 'Add [artifact description]'`)
6. Push to the branch (`git push origin feature/new-adr`)
7. Create a Pull Request (a permanent number will be assigned upon merge)

### Contribution Guidelines

**General Guidelines:**
- Follow Markdown best practices and formatting standards
- Document significant changes in commit messages
- Ensure sensitive information is not included in public artifacts
- Update this README if adding new categories or major changes
- Maintain consistency with existing artifact styles

**For ADRs:**
- Use the ADR template from `doc/decisions/adr-template.md`
- Use `XXXX` as a placeholder in the filename until merged to main (e.g., `XXXX-my-decision.md`)
- Create a corresponding decision approval record using `doc/decisions/adr-decision-template.md`
- Keep ADRs focused on a single decision
- If an ADR needs to be updated after acceptance, add a new numbered record entry in the decision approval file
- Cross-reference related ADRs where appropriate

**For Architecture Principles:**
- Use the principle template from `doc/principles/principle-template.md`
- Use `XXXX` as a placeholder in the filename until merged to main (e.g., `XXXX-my-principle.md`)
- Create a corresponding decision approval record using `doc/principles/principle-decision-template.md`
- Ensure principles are clear, actionable, and testable
- Link to relevant ADRs that implement the principle
- Keep principles concise and focused

### Artifact Naming Conventions

**ADRs:**
```
NNNN-descriptive-title.md           # ADR artifact (final, after merge)
NNNND-descriptive-title.md          # ADR decision approval record
XXXX-descriptive-title.md           # ADR artifact (placeholder, before merge)
XXXXD-descriptive-title.md          # ADR decision approval record (placeholder)

Examples (final):
0002-use-DACI-for-decision-making-process.md
0002D-use-DACI-for-decision-making-process.md

Examples (during development):
XXXX-my-new-architecture-decision.md
XXXXD-my-new-architecture-decision.md
```

**Principles:**
```
NNNN-descriptive-title.md           # Principle artifact (final, after merge)
NNNND-descriptive-title.md          # Principle decision approval record
XXXX-descriptive-title.md           # Principle artifact (placeholder, before merge)
XXXXD-descriptive-title.md          # Principle decision approval record (placeholder)

Examples (final):
0010-eventual-consistency-by-design.md
0010D-eventual-consistency-by-design.md

Examples (during development):
XXXX-my-new-principle.md
XXXXD-my-new-principle.md
```

**Other Artifacts:**
```
[YYYY-MM-DD]_[artifact-type]_[description].[extension]

Examples:
2025-11-13_diagram_target-architecture-overview.png
2025-11-13_documentation_resilience-patterns.md
```

## Related Initiatives and Repositories

As shown by the ESA Initiatives figure under the "What is ESA-main Artifacts for Target Architecture?" section, ESA-main for Target Architecture initiative is supported by multiple initiatives:

- **Architecture for Architecture (A4A)**
- **AInstein**
- **AIon**

These tightly-coupled ESA architecture initiatives have their own repositories and these repositories work together to provide a complete view of the Energy System Architecture delivery streams:

- **[esa-main-artifacts](https://github.com/Alliander/esa-main-artifacts)** - Core architectural artifacts, ADRs, and principles (this repository)
- **[esa-a4a-artifacts](https://github.com/Alliander/esa-a4a-artifacts)** - A4A general artifacts and documentation
- **[esa-a4a-archi](https://github.com/Alliander/esa-a4a-archi)** - A4A ArchiMate co-architecture models
- **[esa-ainstein-artifacts](https://github.com/Alliander/esa-ainstein-artifacts)** - AInstein artifacts and knowledge base
- **[esa-ainstein-archi](https://github.com/Alliander/esa-ainstein-archi)** - AInstein ArchiMate co-architecture models
- **[esa-aion-artifacts](https://github.com/Alliander/esa-aion-artifacts)** - AIon artifacts and knowledge base
- **[esa-aion-archi](https://github.com/Alliander/esa-aion-archi)** - AIon ArchiMate co-architecture models

## Related Resources

### Architecture Frameworks & Standards

- **[TOGAF Standard, 10th Edition](https://www.opengroup.org/togaf)** - The Open Group Architecture Framework (latest version, released 2022, updated 2025)
- **[ArchiMate 3.2 Specification](https://pubs.opengroup.org/architecture/archimate3-doc/)** - Official ArchiMate 3.2 specification (current version)
- **[ISO/IEC/IEEE 42010:2022](https://www.iso.org/standard/74393.html)** - Systems and software engineering — Architecture description

### Decision Records

- **[Markdown Architectural Decision Records (MADR)](https://adr.github.io/madr/)** - The MADR template and documentation
- **[ADR GitHub Organization](https://adr.github.io/)** - Resources and tools for architectural decision records
- **[Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)** - Michael Nygard's original ADR concept

### Architecture Principles

- **[TOGAF Architecture Principles](https://pubs.opengroup.org/architecture/togaf9-doc/arch/chap20.html)** - Guide to developing architecture principles
- **[Enterprise Architecture Principles](https://www.bizzdesign.com/blog/enterprise-architecture-principles/)** - Best practices and examples

### Energy System Architecture

- **[IEC 61968 Series](https://webstore.iec.ch/publication/6195)** - Application integration at electric utilities - System interfaces for distribution management
- **[IEC 62351 Series](https://webstore.iec.ch/publication/6912)** - Power systems management and associated information exchange - Data and communications security

## Contact

**Energy System Architects (ESA) Team**
- Organization: [Alliander](https://www.alliander.com)
- Repository: [esa-main-artifacts](https://github.com/Alliander/esa-main-artifacts)

For questions or support, please [open an issue](https://github.com/Alliander/esa-main-artifacts/issues) or contact the ESA team.

---

*[Maintained by the ESA Team at Alliander](https://www.alliander.com/en/)*
