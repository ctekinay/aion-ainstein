# ESA Document Ontology

## 1. Document Types

The AInstein knowledge base contains four document collections from Alliander's Energy System Architecture (ESA) domain.

### Architectural Decision Records (ADRs)

Formal records of significant architecture decisions following the MADR template.

**Identifier format:** ADR.NN (e.g., ADR.12 = "Use CIM as default domain language")
**Sections:** Context (problem statement), Decision (outcome), Consequences
**Status:** proposed, accepted, deprecated, or superseded

**ADR number ranges:**
- ADR.0-2: Meta decisions (markdown format, writing conventions, DACI process)
- ADR.10-12: Standardisation (IEC standards priority, business functions, CIM adoption)
- ADR.20-31: Energy system decisions (demand response, scheduling, security, OAuth, TLS)

**Decision Approval Records (DARs):** Files like `0029D` contain the approval record for ADR.29 — who approved it, when, and under what conditions.

**Ownership:** Energy System Architecture (ESA) team, System Operations department.

### Architecture & Governance Principles (PCPs)

Guiding principles with sections: Statement, Rationale, Implications.

**Identifier format:** PCP.NN (e.g., PCP.10 = "Eventual Consistency by Design")

**PCP number ranges:**
- PCP.10-20: ESA Architecture Principles (data design, consistency, sovereignty)
- PCP.21-30: Business Architecture Principles (omnichannel, customer centricity, value streams) — primarily Dutch
- PCP.31-40: Data Office Governance Principles (data quality, accessibility, AI) — mix of Dutch and English

**Decision Approval Records:** Files like `0022D` contain the approval record for PCP.22.

**Ownership:** ESA team (PCP.10-20), Business Architecture (PCP.21-30), Data Office (PCP.31-40).

### Policy Documents

Data governance and compliance policies in DOCX/PDF format, primarily in Dutch.

**Topics:** Data classification (BIV), information governance, data quality, metadata management, privacy, security, data lifecycle, data product management.
**Chunking:** Large documents are split at ~6000 chars, so multiple results may come from the same document.

**Ownership:** Data Office (DO) team, Data Management department.

### Vocabulary Concepts (SKOS/OWL)

Semantic vocabulary terms from 70+ RDF/Turtle ontology files.

**Major vocabularies:**
- IEC 61968/61970 (CIM — Common Information Model)
- IEC 62325 (energy market), IEC 62746 (demand response)
- ENTSOE HEMRM (European energy market model)
- ArchiMate (enterprise architecture), ESA vocabulary
- Dutch legal/regulatory vocabularies (energy law)

**Each concept has:** pref_label, definition, broader/narrower/related hierarchy, vocabulary_name, URI.

## 2. Relationships Between Document Types

- **ADRs reference Principles:** Decisions are grounded in architectural principles
- **ADRs reference Vocabulary:** Decisions cite IEC/CIM standard concepts
- **Principles reference Vocabulary:** Principles use domain terminology
- **Policies enforce Principles:** Governance policies operationalize principles
- **Vocabulary provides shared semantics:** All document types use vocabulary terms

## 3. ID Aliases

Users refer to documents in many ways. All of these are equivalent:

**ADRs:** "ADR 29", "adr-29", "ADR.29", "ADR.0029", "ADR-0029", "decision 29"
**Principles:** "PCP 10", "pcp-10", "PCP.10", "PCP.0010", "principle 10"

When searching, normalize to the 4-digit format (e.g., "0029" for ADR.29).

## 4. Numbering Overlap

Numbers 10-12 and 20-31 exist in BOTH ADRs and Principles. Examples:

| Number | ADR | Principle |
|--------|-----|-----------|
| 10 | Prioritize origins of standardizations | Eventual Consistency by Design |
| 12 | Use CIM as default domain language | Business Driven Data Readiness |
| 22 | Use priority-based scheduling | Omnichannel Multibrand |
| 29 | Use OAuth 2.0 for auth | Datagedreven besluiten |

If a user says "document 22" without specifying ADR or PCP, present BOTH results.

## 5. Team Ownership

| Team | Abbreviation | Owns |
|------|-------------|------|
| Energy System Architecture | ESA | All ADRs, PCP.10-20 |
| Business Architecture | — | PCP.21-30 |
| Data Office | DO | All Policies, PCP.31-40 |

## 6. Query Intent Patterns

- **Lookup:** "What does ADR.12 decide?" → Search for the specific ADR
- **Approval:** "Who approved ADR.29?" → Search for DAR "0029D"
- **Topic search:** "What decisions about security?" → Keyword search across ADRs
- **List:** "List all ADRs" → Use list_all_adrs, not search
- **Ambiguous number:** "What is document 22?" → Search both ADRs and Principles

## 7. Answer Guidelines

- Reference ADRs as "ADR.12 — Use CIM as default domain language"
- Reference Principles as "PCP.10 — Eventual Consistency by Design"
- For vocabulary terms, include the source standard (e.g., "from IEC 61970")
- Note ADR status: accepted = binding, proposed = under review
- Policy documents are primarily in Dutch; translate key points when answering in English
