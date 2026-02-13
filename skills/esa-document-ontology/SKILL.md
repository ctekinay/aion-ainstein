---
name: esa-document-ontology
description: "Domain knowledge about the ESA architectural artifact ecosystem: what ADRs, PCPs, and DARs are, how they're named, numbered, related, and how users refer to them. Enables accurate identification and disambiguation of document references in queries."
---

# ESA Document Ontology

You are working with the **Energy System Architects (ESA)** architectural artifact repository maintained by Alliander. This skill gives you the domain knowledge needed to understand what these documents are, how they're organized, and how users refer to them.

## Document Types

There are three types of content documents:

### Architecture Decision Records (ADRs)

An **ADR** captures an important architecture decision along with its context, considered options, and consequences. ADRs address functional and non-functional requirements at the Energy System Architecture level.

- **Location**: `doc/decisions/`
- **Official ID format**: `ADR.NN` (e.g., ADR.00, ADR.12, ADR.25)
- **Filename format**: `NNNN-descriptive-title.md` (e.g., `0012-use-CIM-as-default-domain-language.md`)
- **Sections**: Context and Problem Statement, Decision Drivers, Considered Options, Decision Outcome, Consequences
- **Statuses**: proposed, accepted, deprecated, superseded, rejected

### Architecture Principles (PCPs)

A **PCP** (Principle) is a fundamental statement that guides architecture decisions and provides a framework for evaluating design choices. The abbreviation "PCP" is used internally.

- **Location**: `doc/principles/`
- **Official ID format**: `PCP.NN` (e.g., PCP.10, PCP.22, PCP.40)
- **Filename format**: `NNNN-descriptive-title.md` (e.g., `0022-OmnichannelMultibrand.md`)
- **Sections**: Statement, Rationale, Implications, Scope, Related Principles
- **Statuses**: proposed, ready for acceptance, accepted

Note: Some principles (PCP.21-PCP.38) are written in Dutch, reflecting their ownership by the Business Architecture Group and Data Office.

### Decision Approval Records (DARs)

A **DAR** tracks the governance and approval history for an ADR or PCP. Every ADR has exactly one corresponding DAR, and every PCP has exactly one corresponding DAR.

- **Location**: Same folder as the document it belongs to (`doc/decisions/` for ADR DARs, `doc/principles/` for PCP DARs)
- **Filename format**: `NNNND-descriptive-title.md` — same as the content document but with a **D** suffix on the number (e.g., `0012D-use-CIM-as-default-domain-language.md`)
- **Contains**: Approval sections with version, decision status (Acknowledged/Accepted/Revoked), decision date, driver (decision owner group), and approver tables with names, emails, and roles
- **Linked to content**: The DAR shares the same number, the same descriptive title, and (where available) the same UUID as its content document

## Numbering and the Overlap Problem

Numbering is **purely sequential** within each type. ADRs and PCPs are numbered independently.

**Critical**: For numbers 0010-0031, a document exists in BOTH `decisions/` and `principles/` with the same number. For example:

- **0022** in `decisions/` = **ADR.22**: "Use priority-based scheduling" (an architecture decision)
- **0022** in `principles/` = **PCP.22**: "Omnichannel Multibranded" (an architecture principle)

These are completely different documents. When a user references just a number without specifying ADR or PCP, and the number falls in the overlapping range (0010-0031), you must disambiguate:

1. **If the user said "ADR" or "decision"**: it's the document in `decisions/`
2. **If the user said "PCP" or "principle"**: it's the document in `principles/`
3. **If they only gave a number**: ask which one they mean, showing both options with their titles

### Current Document Inventory

**ADRs** (18 documents): ADR.00-ADR.02, ADR.10-ADR.12, ADR.20-ADR.31
**PCPs** (31 documents): PCP.10-PCP.40
**DARs**: One per ADR (18) + one per PCP (31) = 49 DARs

Numbers that overlap between ADR and PCP: 0010, 0011, 0012, 0020-0031 (15 numbers total).

## How Users Refer to Documents

Users do NOT consistently use the official `ADR.NN` or `PCP.NN` format. You should recognize all of these as referring to the same document:

| What they mean | Variations they might use |
|---------------|--------------------------|
| ADR.12 | `ADR-0012`, `ADR.12`, `ADR 12`, `adr12`, `adr-12`, `decision 12`, `decision 0012` |
| PCP.22 | `PCP.22`, `PCP-22`, `pcp22`, `principle 22`, `principle 0022` |
| DAR for ADR.22 | `DAR for ADR 22`, `approval record for ADR.22`, `who approved ADR 22` |

The words "ADR", "adr", "Adr", "ADRs", "Adrs", "adrs" all refer to Architecture Decision Records. Similarly, "PCP", "pcp", "principle", "Principle", "principles" all refer to Architecture Principles.

When a user asks about a specific document by ID, this is a **lookup**, not a semantic search. Use the `adr_number` or `principle_number` metadata fields to find the exact document, not text similarity. (A `canonical_id` field like `"ADR.22"` may be added in future; use it for filtering when available.)

## Disambiguation Rules

When you need to determine which specific document a user means:

1. **Folder path** is definitive: `decisions/` = ADR, `principles/` = PCP
2. **Registry prefix** is definitive: `ADR.22` vs `PCP.22`
3. **Frontmatter `parent` field**: `Decisions` = ADR, `Principles` = PCP
4. **Frontmatter `nav_order`**: ADR DARs use `ADR.NND`, PCP content uses `PCP.NN`, PCP DARs use `PCP.NND`
5. **UUID** (`dct.identifier` in frontmatter): Shared between a content document and its DAR (available for PCPs; ADRs currently lack UUIDs in their content files)

If a query is ambiguous and you cannot determine the type from context, **ask the user** rather than guessing. For example:

> "There are two documents numbered 0022:
> - **ADR.22**: Use priority-based scheduling (Architecture Decision)
> - **PCP.22**: Omnichannel Multibranded (Architecture Principle)
>
> Which one are you interested in?"

## Owner Groups

Documents are owned by different architecture groups within Alliander. Ownership is recorded in the registry and in each document's DAR.

| Abbreviation | Full Name | Owns | Action Term |
|-------------|-----------|------|------------|
| ESA | System Operations - Energy System Architecture Group | All ADRs, PCP.10-20, PCP.39-40 | Approval |
| BA | Alliander Business Architecture Group | PCP.21-30 | Acceptance |
| DO | Alliander Data Office | PCP.31-38 | Acceptance |

The DACI framework governs decisions:
- **Driver**: Initiates and coordinates the decision-making process
- **Approver**: Has authority to make the final decision
- **Contributors**: Subject matter experts providing input
- **Informed**: Stakeholders kept in the loop

## The Registry

The file `doc/esa_doc_registry.md` (titled "Architectural Artifact Registry") is the canonical index of all ADRs and PCPs. It contains markdown tables with columns: ID, Title, Status, Date, Owner.

The registry does NOT list DARs — but every document in the registry has a corresponding DAR that can be inferred: replace `NNNN-title.md` with `NNNND-title.md` in the same folder.

## Other Files (Not Content Documents)

These files exist in the repository but are NOT ADRs, PCPs, or DARs:

- **Templates**: `adr-template.md`, `adr-decision-template.md` (in `decisions/`), `principle-template.md`, `principle-decision-template.md` (in `principles/`) — these are authoring templates, not documents
- **Index files**: `decisions/index.md`, `principles/index.md` — auto-generated folder descriptions
- **README**: `README_esa-main-artifacts.md` — repository documentation
- **Images**: `decisions/images/` — diagrams referenced by ADRs

## Frontmatter Differences

Be aware that ADR and PCP frontmatter schemas differ:

**ADR content files** have:
```yaml
parent: Decisions
nav_order: 22          # plain number
status: "proposed"
date: 2025-07-21
driver: Name1, Name2
```

**PCP content files** have:
```yaml
parent: Principles
nav_order: PCP.22      # prefixed
dct:
  identifier: urn:uuid:3c9f2b7e-...   # UUID
  title: "Document title"
  isVersionOf: proposed
  issued: 2026-01-21
owl:
  versionIRI: "https://esa-artifacts.alliander.com/..."
  versionInfo: "v1.0.0 (2026-01-21)"
```

**ADR DAR files** have:
```yaml
nav_order: ADR.22D     # prefixed with D
dct:
  identifier: urn:uuid:...   # UUID (but the ADR itself may not have one)
  title: Document title
```

**PCP DAR files** have:
```yaml
nav_order: PCP.22D     # prefixed with D
dct:
  identifier: urn:uuid:...   # same UUID as the PCP content file
  title: Document title
```

## Legacy Note: the `content` doc_type

Some ADR documents in Weaviate have `doc_type: "content"` instead of `doc_type: "adr"`. This is a legacy artifact from earlier ingestion runs. When filtering by document type, include both `"adr"` and `"content"` to avoid silently missing ADRs. This will be cleaned up in a future migration.
