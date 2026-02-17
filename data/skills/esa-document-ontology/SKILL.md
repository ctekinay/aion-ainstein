# ESA Document Ontology

## Knowledge Base Structure

The AInstein knowledge base contains four document collections from Alliander's Energy System Architecture (ESA) domain.

### 1. Architectural Decision Records (ADRs)

Formal records of significant architecture decisions following the MADR template.

**Source:** Markdown files in `esa-main-artifacts/doc/decisions/`
**Naming:** `NNNN-title.md` (e.g., `0012-use-cim-as-canonical-data-model.md`)
**Identifier format:** ADR.XX (e.g., ADR.12)

**Key fields:**
- `title` — ADR title (prefixed with ADR.XX)
- `status` — One of: proposed, accepted, deprecated, superseded
- `context` — Context and Problem Statement
- `decision` — Decision Outcome
- `consequences` — Positive and negative consequences

**Ownership:** Energy System Architecture (ESA) team, System Operations department.

### 2. Architecture & Governance Principles (Principles)

Guiding principles for architecture and data governance decisions.

**Source:** Markdown files in `esa-main-artifacts/doc/principles/` and `do-artifacts/`
**Naming:** `NNNN-title.md` (e.g., `0010-eventual-consistency-by-design.md`)
**Identifier format:** PCP.XX (e.g., PCP.10)

**Key fields:**
- `title` — Principle title (prefixed with PCP.XX)
- `content` — Statement, Rationale, and Implications
- `doc_type` — content, index, template, or decision_approval_record

**Ranges:**
- PCP.10-20: ESA Architecture Principles
- PCP.21-30: Business Architecture Principles
- PCP.31-40: Data Office Governance Principles

**Ownership:** ESA team or Data Office (DO), depending on range.

### 3. Policy Documents

Data governance and compliance policies in DOCX/PDF format.

**Source:** `do-artifacts/policy_docs/`
**Formats:** .docx and .pdf

**Key fields:**
- `title` — Document title
- `content` — Extracted text (large documents chunked at ~6000 chars)
- `file_type` — docx or pdf

**Topics covered:** Data classification, information governance, data quality, metadata management, privacy, security, data lifecycle.

**Ownership:** Data Office (DO) team, Data Management department.

### 4. Vocabulary Concepts (SKOS/OWL)

Semantic vocabulary terms from IEC energy standards and domain ontologies, encoded in RDF/Turtle using SKOS and OWL standards.

**Source:** 70+ `.ttl` files in `esa-skosmos/`
**Standards:** W3C SKOS (Simple Knowledge Organization System), OWL

**Key fields:**
- `pref_label` — Preferred term (English or Dutch)
- `definition` — Concept definition
- `broader` / `narrower` / `related` — Concept hierarchy relationships
- `vocabulary_name` — Source vocabulary name
- `uri` — Unique concept URI

**Major vocabularies:**
- IEC 61968 / 61970 / 62325 / 62746 — Energy system CIM standards
- ENTSOE HEMRM — European energy market model
- ArchiMate — Enterprise architecture modeling
- ESA — Alliander's own energy system vocabulary
- Legal/regulatory vocabularies (Dutch energy law)

## Relationships Between Document Types

- **ADRs reference Principles:** Decisions are grounded in architectural principles
- **ADRs reference Vocabulary:** Decisions cite IEC/CIM standard concepts
- **Principles reference Vocabulary:** Principles use domain terminology
- **Policies enforce Principles:** Governance policies operationalize principles
- **Vocabulary provides shared semantics:** All document types use vocabulary terms

## Answer Guidelines

When answering questions:
- Reference ADRs by their identifier (e.g., "ADR.12 - Use CIM as Canonical Data Model")
- Reference Principles by their identifier (e.g., "PCP.10 - Eventual Consistency by Design")
- For vocabulary terms, include the source standard (e.g., "from IEC 61970")
- Distinguish between ESA architecture principles (PCP.10-20) and DO governance principles (PCP.31-40)
- Note the status of ADRs: accepted decisions are binding, proposed ones are under review
- Policy documents are primarily in Dutch; translate key points when answering in English
