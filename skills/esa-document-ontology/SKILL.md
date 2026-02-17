---
name: esa-document-ontology
description: "Domain knowledge about ADRs, PCPs, DARs: naming, numbering, relationships, disambiguation"
---

# ESA Document Ontology v2

You are working with the **Energy System Architects (ESA)** architectural artifact repository maintained by Alliander. This skill gives you the domain knowledge needed to understand what these documents are, how they're organized, and how users refer to them.

## Section 0: Messy Repo Reality and Robustness Rules

The ESA repository is a real-world artifact collection, not a clean synthetic corpus. Expect and handle:

1. **Inconsistent naming**: Some filenames use hyphens, some underscores, some camelCase. Do not assume a single naming convention.
2. **Missing frontmatter**: Not all documents have complete YAML frontmatter. Some ADRs lack `dct.identifier` (UUID). Absence of a field does not mean the document is invalid.
3. **Mixed languages**: PCP.21-PCP.38 are written in Dutch. Do not flag them as errors or refuse to process them.
4. **Partial re-indexes**: After re-indexing, some documents may temporarily have stale `doc_type` values. The `content` doc_type is a legacy value that may still appear.
5. **Templates in content folders**: Template files live alongside content documents. They are NOT content — identify them by filename patterns (`*template*`) or placeholder content (`{short title}`, `{problem statement}`).
6. **Index files as navigation aids**: `index.md` and `readme.md` files are folder navigation documents, not content. They contain generic terms that act as retrieval bait.

**Robustness rule**: When classifying or resolving a document, tolerate missing fields. Use the fields that ARE present rather than failing because an expected field is absent.

## Section 1: Document Types

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
- **Canonical ID format**: DARs use the parent document's ID with a D suffix: `ADR.12D` or `PCP.22D`. There is NO separate `DAR.` prefix in this ontology.
- **Contains**: Approval sections with version, decision status (Acknowledged/Accepted/Revoked), decision date, driver (decision owner group), and approver tables with names, emails, and roles
- **Linked to content**: The DAR shares the same number, the same descriptive title, and (where available) the same UUID as its content document

## Section 2: Non-Content Documents

These files exist in the repository but are NOT ADRs, PCPs, or DARs. They are classified as non-content types for filtering purposes:

### Collection Index Pages
Files like `decisions/index.md` and `principles/index.md`. These are auto-generated folder navigation pages that list documents in their directory. They contain generic terms ("Architecture Decision Records", "standards", "protocols") that make them attractive but misleading retrieval candidates.

In storage, these may be classified as doc_type `index` and are excluded at ingestion.

### Repository READMEs
Files like `README_esa-main-artifacts.md` and `README.md`. These describe the repository structure, not architectural content.

In storage, these may be classified as doc_type `index` and are excluded at ingestion.

### ESA Registry
The file `doc/esa_doc_registry.md` (titled "Architectural Artifact Registry") is the canonical index of all ADRs and PCPs. It contains markdown tables with columns: ID, Title, Status, Date, Owner. The registry does NOT list DARs — but every document in the registry has a corresponding DAR.

In storage, classified as doc_type `registry`; ingested but filtered at query time (excluded from primary content retrieval, available for disambiguation).

### Templates
Files like `adr-template.md`, `principle-template.md`, `adr-decision-template.md`, `principle-decision-template.md`. These contain placeholder content (`{short title}`, `{problem statement}`, `{context}`) and are authoring scaffolds, not documents.

In storage, classified as doc_type `template` and excluded at ingestion.

## Section 3: ID Aliases and Recognition Patterns

Users do NOT consistently use the official `ADR.NN` or `PCP.NN` format. Recognize all of these as referring to the same document:

| What they mean | Variations they might use |
|---------------|--------------------------|
| ADR.12 | `ADR-0012`, `ADR.12`, `ADR 12`, `adr12`, `adr-12`, `decision 12`, `decision 0012`, `ADR.0012` |
| PCP.22 | `PCP.22`, `PCP-22`, `pcp22`, `PCP.0022`, `principle 22`, `principle 0022` |
| DAR for ADR.22 | `ADR.22D`, `ADR.0022D`, `DAR for ADR 22`, `approval record for ADR.22`, `who approved ADR 22` |
| DAR for PCP.22 | `PCP.22D`, `PCP.0022D`, `DAR for PCP 22`, `approval record for principle 22` |

The words "ADR", "adr", "Adr", "ADRs", "Adrs", "adrs" all refer to Architecture Decision Records. Similarly, "PCP", "pcp", "principle", "Principle", "principles" all refer to Architecture Principles.

**Number padding**: Users may use 2-digit (`ADR.12`) or 4-digit (`ADR.0012`) numbers. Both refer to the same document. Normalize to the shortest unambiguous form when citing.

## Section 4: Numbering and the Overlap Problem

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

## Section 5: Disambiguation

If a query is ambiguous and you cannot determine the document type from context, **ask the user** rather than guessing. For example:

> "There are two documents numbered 0022:
> - **ADR.22**: Use priority-based scheduling (Architecture Decision)
> - **PCP.22**: Omnichannel Multibranded (Architecture Principle)
>
> Which one are you interested in?"

## Section 6: Query Intent Semantics

User queries follow an **action -> subject** pattern. Understanding the action determines which tools and retrieval strategies to use.

| Action | Human Label | What it means |
|--------|------------|---------------|
| Summarize | summarize | Answer a question using retrieved context |
| List all | list_all | Enumerate all documents of a type |
| Select by ID | select_id | Find one specific document by its canonical ID |
| Approval lookup | approval_lookup | Find who approved a specific document (requires DAR) |
| Meta overview | meta_overview | Questions about the system itself |
| Compare | compare | Compare two or more concepts/documents |
| Count | count | How many documents of a type exist |

**Key distinctions**:
- "What does ADR.0012 decide?" is a **select_id** (specific document), NOT a semantic search
- "Which ADRs cover security?" is a **summarize** (topical query across documents)
- "List all ADRs" is a **list_all** (catalog query, deterministic)
- "Who approved ADR.0012?" is an **approval_lookup** (requires the DAR, not the ADR itself)
- "How many principles do we have?" is a **count** (deterministic, registry-backed)

## Section 7: Owner Groups

Documents are owned by different architecture groups within Alliander. Ownership is recorded in the registry and in each document's DAR.

| Abbreviation | Full Name | Owns | Action Term |
|-------------|-----------|------|------------|
| ESA | System Operations - Energy System Architecture Group | All ADRs, PCP.10-20, PCP.39-40 | Approval |
| BA | Alliander Business Architecture Group | PCP.21-30 | Acceptance |
| DO | Alliander Data Office | PCP.31-38 | Acceptance |

## Section 8: Non-Content Files to Avoid

If you see documents titled "Decision Approval Record List" or containing placeholder text like `{short title}`, ignore them — they are templates or navigation pages, not content. These are normally filtered at ingestion, but may occasionally leak through.
