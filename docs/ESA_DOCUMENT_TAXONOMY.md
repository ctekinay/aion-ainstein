# ESA Document Taxonomy (Deterministic Contract)

This document is the authoritative contract for:
- document classification (`doc_type`)
- ID parsing and normalization
- retrieval filtering (content vs approval)
- routing (list vs specific doc vs semantic vs approval)
- output labeling rules (ADR vs DAR, PCP vs DAR)

This contract exists to prevent recurring failures:
- confusing ADR content with DAR content
- list routing swallowing semantic questions
- counts returning chunk counts instead of unique docs
- "ADR.25" vs "ADR.0025" ambiguity

## 1. Directory roots

1) ADRs
- `data/esa-main-artifacts/doc/decisions/`

2) Principles
- `data/esa-main-artifacts/doc/principles/`

3) Registry
- `data/esa-main-artifacts/doc/esa_doc_registry.md`

## 2. File naming rules

### 2.1 ADR content (Decision Record)

Pattern:
- `^(\\d{4})-[a-z0-9-]+\\.md$`

Example:
- `0025-unify-demand-response-interfaces-via-open-standards.md`

Stored fields:
- `adr_number = <NNNN>`
- `doc_type = adr` (legacy allowed: `content`)

### 2.2 ADR approval record (DAR)

Pattern:
- `^(\\d{4})D-[a-z0-9-]+\\.md$`

Example:
- `0025D-unify-demand-response-interfaces-via-open-standards.md`

Stored fields:
- `adr_number = <NNNN>`
- `doc_type = decision_approval_record`

Canonical display:
- ADR content: `ADR.<NNNN>`
- ADR DAR: `ADR.<NNNN>D`

### 2.3 Principle content

Pattern:
- `^(\\d{4})-[a-z0-9-]+\\.md$`

Example:
- `0010-eventual-consistency-by-design.md`

Stored fields:
- `principle_number = <NNNN>`
- `doc_type = principle` (legacy allowed: `content`)

Canonical display:
- Principle content: `PCP.<NNNN>`
- Principle DAR: `PCP.<NNNN>D`

Note:
- PCP is a display prefix. The file number remains `NNNN`.
- If the source files do not explicitly contain "PCP", the system still displays PCP.<NNNN> based on `principle_number`.

### 2.4 Principle approval record (DAR)

Pattern:
- `^(\\d{4})D-[a-z0-9-]+\\.md$`

Example:
- `0010D-eventual-consistency-by-design.md`

Stored fields:
- `principle_number = <NNNN>`
- `doc_type = decision_approval_record`

### 2.5 Templates, directory index, registry

Templates:
- `*-template.md` => `doc_type = template`
- Always skip embedding into vector store

Directory indexes:
- `index.md`, `_index.md`, `README.md`, `overview.md` => `doc_type = index`
- Always skip embedding into vector store

Registry:
- `esa_doc_registry.md` => `doc_type = registry`
- Recommended: do not include in retrieval by default
- Optional: embed only if there is a dedicated "registry" route or explicit user request

## 3. ID parsing and normalization rules

### 3.1 ADR reference patterns

Accept these as ADR references:
- `ADR.0031`
- `ADR 0031`
- `ADR-0031`
- `ADR.31`
- `ADR 31`
- `ADR-31`

Regex:
- `\\bADR[.\\s-]?(\\d{1,4})(D)?\\b` (case insensitive)

Normalization:
- left-pad number to 4 digits: `31 => 0031`
- if suffix `D` exists: this is a DAR reference

Examples:
- `ADR.31` => `ADR.0031` (content unless approval intent or explicit D)
- `ADR.31D` => `ADR.0031D` (DAR)

### 3.2 PCP reference patterns

Accept these as principle references:
- `PCP.0010`
- `PCP 0010`
- `PCP-0010`
- `PCP.10`
- `PCP 10`
- `PCP-10`

Regex:
- `\\bPCP[.\\s-]?(\\d{1,4})(D)?\\b` (case insensitive)

Normalization:
- left-pad number to 4 digits: `10 => 0010`
- if suffix `D` exists: this is a DAR reference

## 4. Query routing rules (deterministic)

Routing must be deterministic and test-covered.

### 4.1 Specific document reference (NOT list route)

If the query contains a specific ADR or PCP reference (Section 3), it is NOT a list query.

Routing:
- specific ADR content query: semantic retrieval with filter excluding DAR
- specific ADR DAR query: approval retrieval with DAR allow-list
- same for PCP

Examples:
- "List ADR.0031" => specific doc route, not list route
- "ADR.31" => specific doc route
- "Tell me about ADR.0025" => specific doc route, content only
- "Who approved ADR.0025?" => approval route, DAR allowed

### 4.2 List intent route (existence questions)

Treat as list only when there is an explicit existence intent AND no specific doc reference.

Strong list intent markers:
- "list all"
- "show all"
- "what exists"
- "which ADRs exist"
- "what ADRs exist"
- "what principles exist"

Examples:
- "What ADRs exist in the system?" => list route
- "List all principles" => list route

### 4.3 Topical semantic intent (NOT list)

If query contains topical markers, treat as semantic retrieval, not list.

Topical markers:
- "about"
- "status"
- "consequences"
- "decision drivers"
- "context"
- "what does it say"
- "explain"
- "details"
- "decisions about <topic>"

Examples:
- "Show ADR decisions about TLS" => semantic route
- "List ADR status and consequences" => semantic route
- "What does the ADR about caching say?" => semantic route

### 4.4 Approval intent (approval route)

Approval intent markers:
- "approval"
- "approved"
- "DAR"
- "decision approval record"
- "governance"
- "DACI"
- "who signed"
- "who decided"
- "who is accountable"

Routing:
- approval route
- allow `decision_approval_record`

Examples:
- "List Decision approval records for principles" => approval route
- "Who approved PCP.10?" => approval route

## 5. Retrieval filters (allow-list)

Default filters:
- ADR content queries: `doc_type in [adr, content]`
- Principle content queries: `doc_type in [principle, content]`

Approval queries:
- include `decision_approval_record`

Registry:
- exclude `registry` from default retrieval
- include only when the user explicitly asks for the registry or taxonomy

Index and templates:
- should not exist in vector store at all (skip at ingestion)

## 6. Output formatting contract

The assistant must always label content vs DAR explicitly.

Rules:
1) ADR content must be labeled `ADR.<NNNN>`
2) ADR DAR must be labeled `ADR.<NNNN>D` and include "Approval Record" text
3) PCP content must be labeled `PCP.<NNNN>`
4) PCP DAR must be labeled `PCP.<NNNN>D` and include "Approval Record" text
5) Never describe a DAR as if it is the ADR or PCP decision content

If both are returned:
- "ADR.0025 (Decision Record)"
- "ADR.0025D (Approval Record)"

## 7. Acceptance tests (must exist)

The following must be covered by tests.

Routing:
- "List ADR 31" => NOT list route
- "ADR.31" => specific doc reference
- "Show ADR decisions about TLS" => semantic route
- "List ADR status and consequences" => semantic route
- "What ADRs exist in the system?" => list route
- "List all principles" => list route
- "List Decision approval records for principles" => approval route

Filtering:
- "Tell me about ADR.0025" must not retrieve DAR unless approval intent is present
- "Who approved ADR.0025" must be able to retrieve DAR

Counting:
- "total number of principles" must return unique docs count (31 in current corpus), not chunk count (168)

## 8. Operational verification commands

After ingestion, verify both content and DAR exist for a given ID:

- ADR example: 0025
  - exactly one content object for `doc_type in [adr, content]` and `adr_number=0025`
  - exactly one DAR object for `doc_type=decision_approval_record` and `adr_number=0025`

- Principle example: 0010
  - exactly one content object for `doc_type in [principle, content]` and `principle_number=0010`
  - exactly one DAR object for `doc_type=decision_approval_record` and `principle_number=0010`
