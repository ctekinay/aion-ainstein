# ESA Document Ontology Analysis

## Comprehensive analysis of document identification, naming, relationships, and system knowledge gaps

**Date**: 2026-02-13
**Scope**: `data/esa-main-artifacts/doc/`, `config/`, and all code in `src/` that processes these documents

---

## PART 1: THE ACTUAL DOCUMENT ONTOLOGY (Ground Truth)

### 1.1 Document Types

There are exactly **4 content document types** and **4 infrastructure file types**:

| Type | Abbreviation | Location | Filename Pattern | Example |
|------|-------------|----------|-----------------|---------|
| Architecture Decision Record | ADR | `doc/decisions/` | `NNNN-descriptive-title.md` | `0022-use-priority-based-scheduling.md` |
| Decision Approval Record for ADR | DAR (ADR) | `doc/decisions/` | `NNNND-descriptive-title.md` | `0022D-use-priority-based-scheduling.md` |
| Architecture Principle | PCP | `doc/principles/` | `NNNN-descriptive-title.md` | `0022-OmnichannelMultibrand.md` |
| Decision Approval Record for PCP | DAR (PCP) | `doc/principles/` | `NNNND-descriptive-title.md` | `0022D-OmnichannelMultibrand.md` |
| ADR Template | - | `doc/decisions/` | `adr-template.md` | - |
| ADR DAR Template | - | `doc/decisions/` | `adr-decision-template.md` | - |
| PCP Template | - | `doc/principles/` | `principle-template.md` | - |
| PCP DAR Template | - | `doc/principles/` | `principle-decision-template.md` | - |

Plus 3 reference/meta files:
- `doc/esa_doc_registry.md` — The canonical registry of all ADRs and PCPs
- `doc/decisions/index.md` — Auto-generated index for decisions folder
- `doc/principles/index.md` — Auto-generated index for principles folder
- `doc/README_esa-main-artifacts.md` — Repository README

### 1.2 The Numbering System

Numbering is **purely sequential within each type**. The fact that certain number ranges happen to belong to certain owner groups is incidental — it's a consequence of which group submitted documents in what order.

**ADRs** (in `doc/decisions/`):
| Range | Count | Owner |
|-------|-------|-------|
| ADR.00–ADR.02 | 3 | ESA (Generic) |
| ADR.10–ADR.12 | 3 | ESA (Standardisation) |
| ADR.20–ADR.31 | 12 | ESA (Energy System) |
| **Total** | **18** | |

**PCPs** (in `doc/principles/`):
| Range | Count | Owner |
|-------|-------|-------|
| PCP.10–PCP.20 | 11 | ESA |
| PCP.21–PCP.30 | 10 | Business Architecture (BA) |
| PCP.31–PCP.38 | 8 | Data Office (DO) |
| PCP.39–PCP.40 | 2 | ESA (Additional) |
| **Total** | **31** | |

### 1.3 The Overlapping Number Problem

**Critical**: ADRs and PCPs share the same `NNNN` filename format. For numbers 0010–0031, there is a document in BOTH `decisions/` and `principles/`:

| Number | ADR (in decisions/) | PCP (in principles/) |
|--------|-------------------|---------------------|
| 0010 | Prioritize origins of standardizations | Eventual Consistency by Design |
| 0011 | Use standard for business functions | Data is Designed for Need to Know |
| 0012 | Use CIM as default domain language | Business-Driven Data Readiness |
| 0020 | Verify demand response products | Sovereign-by-Design |
| 0021 | Use sign convention for current direction | Operational Excellence |
| 0022 | Use priority-based scheduling | Omnichannel Multibranded |
| 0023 | FSP responsible for operational constraints | Zelfregie en zelfservice |
| 0024 | Standard for energy flow direction | Klant centraal |
| 0025 | Unify demand response interfaces | Klantervaring merken |
| 0026 | Ensure idempotent message exchange | Ontwerp waardestromen |
| 0027 | Use TLS to secure communication | Max waarde assets |
| 0028 | Participant-initiated invalidation | Business services |
| 0029 | Use OAuth 2.0 | Datagedreven besluiten |
| 0030 | Identification based on market participant | Human-machine knowledge |
| 0031 | Use Alliander-owned domain | Data vastlegging |

**15 numbers overlap.** The ONLY ways to disambiguate:
1. **Folder path**: `decisions/` = ADR, `principles/` = PCP
2. **Registry ID prefix**: `ADR.22` vs `PCP.22`
3. **Frontmatter**: `parent: Decisions` vs `parent: Principles`, `nav_order: ADR.22D` vs `nav_order: PCP.22D`
4. **UUID** in frontmatter (unique per document, shared between content file and its DAR)

### 1.4 The ADR↔DAR Relationship

Every ADR has exactly one corresponding DAR in the same folder:
- `0022-use-priority-based-scheduling.md` (ADR.22, the decision content)
- `0022D-use-priority-based-scheduling.md` (DAR for ADR.22, approval/governance history)

They share:
- The same `NNNN` number
- The same `descriptive-title` suffix
- The same UUID in frontmatter (`dct.identifier`)
- The same folder (`doc/decisions/`)

Same pattern for PCPs:
- `0022-OmnichannelMultibrand.md` (PCP.22)
- `0022D-OmnichannelMultibrand.md` (DAR for PCP.22)

### 1.5 The Official ID Format

From the registry (`esa_doc_registry.md`):
- ADRs: `ADR.NN` (e.g., ADR.22, ADR.00, ADR.10) — note: no leading zeros in the number after the dot
- PCPs: `PCP.NN` (e.g., PCP.22, PCP.10)

From DAR frontmatter `nav_order` field:
- ADR DARs: `ADR.NND` (e.g., ADR.22D)
- PCP DARs: `PCP.NND` (e.g., PCP.22D)

### 1.6 How Users Actually Refer to Documents

Users do NOT consistently use the `ADR.NN` format. Observed and expected variations:

| What they mean | What they might type |
|---------------|---------------------|
| ADR.12 | `ADR-0012`, `ADR.12`, `ADR 12`, `adr12`, `adr-12`, `ADR-12`, `decision 12`, `decision 0012`, `0012` |
| PCP.22 | `PCP.22`, `PCP-22`, `pcp22`, `principle 22`, `principle 0022` |
| DAR for ADR.22 | `DAR for ADR 22`, `approval record for ADR.22`, `who approved ADR 22`, `ADR.22D` |
| Any document | `Tell me about ADR.0025`, `What does ADR-0012 decide?` |

**Key insight**: The system must understand that `ADR`, `adr`, `Adr`, `ADRs`, `Adrs`, `adrs` all refer to Architecture Decision Records. Similarly for `PCP`, `principle`, `Principle`, etc. This is **not a regex problem** — it's a domain vocabulary problem.

### 1.7 Frontmatter Structure Differences

**ADR frontmatter** (decisions/0022-*.md):
```yaml
parent: Decisions
nav_order: 22
status: "proposed"
date: 2025-07-21
driver: Robert-Jan Peters, Laurent van Groningen
```
- No UUID
- No `dct:` block
- Uses `parent: Decisions`

**PCP frontmatter** (principles/0022-*.md):
```yaml
parent: Principles
nav_order: PCP.22
dct:
  identifier: urn:uuid:3c9f2b7e-8a4d-4e6b-9f2a-1d7c6e9b5a42
  title: "Omnichannel Multibranded"
  isVersionOf: proposed
  issued: 2026-01-21
owl:
  versionIRI: "https://esa-artifacts.alliander.com/..."
  versionInfo: "v1.0.0 (2026-01-21)"
```
- Has UUID (`dct.identifier`)
- Has semantic web metadata (`owl:`)
- Uses `parent: Principles`
- `nav_order` includes the `PCP.` prefix

**ADR DAR frontmatter** (decisions/0022D-*.md):
```yaml
nav_order: ADR.22D
dct:
  identifier: urn:uuid:c9d0e1f2-a3b4-4c5d-6e7f-8a9b0c1d2e3f
  title: Use priority based scheduling
```
- Has UUID (should match ADR's but ADR itself has none!)

**PCP DAR frontmatter** (principles/0022D-*.md):
```yaml
nav_order: PCP.22D
dct:
  identifier: urn:uuid:3c9f2b7e-8a4d-4e6b-9f2a-1d7c6e9b5a42
  title: Omnichannel Multibranded
```
- UUID matches PCP content file

### 1.8 Frontmatter Inconsistency (Found)

**ADR content files have NO UUID** while their DARs do. PCP content files have UUIDs and their DARs share them. This means:
- For PCPs: UUID linkage works (PCP.22 and its DAR share `urn:uuid:3c9f2b7e-...`)
- For ADRs: UUID linkage is broken (ADR.22 has no UUID; its DAR has one but there's nothing to match it against)

The `nav_order` field is also inconsistent:
- ADR content: plain number (`22`)
- ADR DAR: prefixed (`ADR.22D`)
- PCP content: prefixed (`PCP.22`)
- PCP DAR: prefixed (`PCP.22D`)

### 1.9 The Owner / Driver Information

The owner of an ADR or PCP is **NOT reliably in the content file**. It's in:
1. The **registry** (`esa_doc_registry.md`): `Owner` column
2. The **DAR file**: `Driver (Decision owner)` row in metadata table
3. The **DAR file**: section title pattern like "Creation and **ESA** Approval of ADR.22" or "Creation and **BA** Acceptance of PCP.22"

Owner groups:
| Abbreviation | Full Name | Action Term |
|-------------|-----------|------------|
| ESA | System Operations - Energy System Architecture Group | Approval |
| BA | Alliander Business Architecture Group | Acceptance |
| DO | Alliander Data Office | Acceptance |

---

## PART 2: WHAT THE CURRENT SYSTEM KNOWS (AND GETS WRONG)

### 2.1 Code that processes document types

There are **10 modules** involved in understanding document identity:

| # | Module | Role | Issues |
|---|--------|------|--------|
| 1 | `src/doc_type_classifier.py` | Canonical taxonomy & classification | `all_types()` omits PRINCIPLE and PRINCIPLE_APPROVAL |
| 2 | `src/loaders/markdown_loader.py` | Loads files, extracts frontmatter & sections | **Duplicates** classification logic instead of using #1 |
| 3 | `src/loaders/index_metadata_loader.py` | Parses index.md for ownership | Never reads registry for per-document ownership |
| 4 | `src/approval_extractor.py` | Parses DARs, matches approval queries | Works but separate from loader pipeline |
| 5 | `src/intent_router.py` | Classifies user intent | Detects doc references but doesn't validate they exist |
| 6 | `src/meta_route.py` | Detects system-meta vs corpus questions | No domain ontology awareness |
| 7 | `src/weaviate/ingestion.py` | Ingests documents into Weaviate | Number extraction uses weak regex, no UUID handling |
| 8 | `src/skills/filters.py` | Builds Weaviate filters by doc_type | Relies on correct doc_type at ingestion |
| 9 | `config/taxonomy.default.yaml` | Pattern definitions | Most complete config, but not used everywhere |
| 10 | `config/corpus_expectations.yaml` | Corpus validation | Only has ADR count range, no principle expectations |

### 2.2 Specific Issues Found

#### Issue 1: Duplicate classification logic
`markdown_loader.py` has its own `_classify_adr_document()` and `_classify_principle_document()` methods (~120 lines) that duplicate what `doc_type_classifier.py` does. They use slightly different patterns (`decision_approval_record` vs `adr_approval`), creating a **two-truth problem**.

#### Issue 2: The number-only reference ambiguity
When a user says "tell me about 0022", the system cannot know if they mean ADR.22 or PCP.22. Currently:
- `approval_extractor.py:extract_document_number()` looks for `adr[.\s-]?(\d{1,4})` or `pcp[.\s-]?(\d{1,4})` — requires the prefix
- `intent_router.py:_detect_doc_references()` uses `r"\b(?:adr|pcp|dar)[.\s-]?\d{1,4}\b"` — also requires prefix
- If user just says "0022" or "document 22", **nothing detects it as a document reference**

#### Issue 3: No concept of "what is an ADR" for the system
The system has regex patterns for detecting document references, but **no grounded understanding** of:
- What "ADR" means (Architecture Decision Record)
- What "PCP" means (Architecture Principle, with "PCP" being an internal abbreviation)
- What "DAR" means (Decision Approval Record, the governance trail)
- That ADRs and PCPs are fundamentally different document types
- That DARs exist for both ADRs and PCPs
- That numbering overlaps between ADRs and PCPs

This knowledge exists only in:
- The README (not indexed, not used by system)
- The registry (indexed as a single blob, not parsed for structure)
- The index.md files (skipped at ingestion)
- The user's head

#### Issue 4: The registry is ingested but not structurally parsed
`esa_doc_registry.md` is ingested into Weaviate as a text blob. But its structured data (the markdown tables with ID, Title, Status, Date, Owner) is never extracted into queryable metadata. The system can't answer "what is the status of ADR.25?" from the registry because it's just text in a vector.

#### Issue 5: No UUID extraction or linking
- PCP frontmatter has `dct.identifier` (UUID) — never extracted or stored in Weaviate
- ADR frontmatter has no UUID (inconsistency in the source data)
- DAR frontmatter has UUID — never used to link DAR↔content file
- The system links ADR↔DAR purely by number matching, which works but ignores the richer UUID linkage

#### Issue 6: Ownership is not queryable
The Owner/Driver information lives in:
- Registry markdown tables (not parsed)
- DAR metadata tables (parsed only on explicit approval queries)
- Never stored as a Weaviate property

So "which ADRs were created by the Data Office?" requires full-text search instead of a filter.

#### Issue 7: corpus_expectations.yaml is half-empty
```yaml
adr:
  unique_count: { enabled: true, min: 15, max: 25 }
  must_include_ids: { enabled: true, values: ["0030", "0031"] }
principle:
  unique_count: { enabled: false }
  must_include_ids: { enabled: false }
```
Principles have no expectations. ADR count range (15-25) will quickly go stale as new ADRs are added.

#### Issue 8: Taxonomy config has good patterns, but code doesn't always use them
`taxonomy.default.yaml` defines `doc_reference_patterns`, `doc_request_phrases`, `terminology_patterns`, `markers` — but some code modules import these patterns and others hardcode their own. For example:
- `intent_router.py` hardcodes many regex patterns (lines 205-357)
- `approval_extractor.py` hardcodes patterns (lines 323-344)
- `meta_route.py` hardcodes patterns (lines 74-95)

#### Issue 9: The `content` legacy type creates confusion
The taxonomy has `content` as a "legacy-canonical" type, allowed in both ADR and Principle routes. Some code still uses `content` as a doc_type, others use `adr`. This dual-naming means Weaviate queries need to filter for both, and any miss causes silent retrieval failures.

#### Issue 10: Templates and index files are skipped but their knowledge is lost
Templates define the **expected structure** of ADRs and PCPs (what sections exist, what fields are required). This structural knowledge could be used for validation and section extraction, but since templates are skipped at ingestion, the system only has hardcoded regex patterns that approximate this structure.

---

## PART 3: THE RESTRUCTURING PLAN

### 3.1 Philosophy

The current system tries to handle domain knowledge through:
- Regex patterns scattered across 10+ files
- YAML configs that are partially used
- Hardcoded assumptions in code

This should be replaced with:
1. **A single Domain Knowledge Skill** — a structured, human-readable document that captures everything the system needs to know about the ESA document ecosystem
2. **A Document Registry Service** — a programmatic layer that provides authoritative lookups
3. **Consolidated classification** — one path for document type identification

### 3.2 Proposed Architecture

```
┌──────────────────────────────────────────────────────────┐
│  LAYER 1: Domain Knowledge Skill (NEW)                   │
│  "What is an ADR? How are documents named?"              │
│  → Used by LLM for grounded understanding                │
│  → Single source of truth for domain vocabulary          │
│  → File: src/skills/esa_document_ontology.md             │
└──────────────┬───────────────────────────────────────────┘
               │ informs
┌──────────────▼───────────────────────────────────────────┐
│  LAYER 2: Document Registry Service (NEW)                │
│  "Resolve ADR.22 → file, metadata, DAR link"             │
│  → Parses esa_doc_registry.md into structured data       │
│  → Builds ADR↔DAR linkage from filenames + UUIDs         │
│  → Provides lookup by ID, number, title, owner           │
│  → File: src/services/document_registry.py               │
└──────────────┬───────────────────────────────────────────┘
               │ used by
┌──────────────▼───────────────────────────────────────────┐
│  LAYER 3: Consolidated Classifier (REFACTORED)           │
│  "Is this file an ADR, PCP, DAR, template, or index?"    │
│  → Single module: src/doc_type_classifier.py             │
│  → markdown_loader.py CALLS it, doesn't duplicate it     │
│  → All config from taxonomy.default.yaml only            │
└──────────────┬───────────────────────────────────────────┘
               │ used by
┌──────────────▼───────────────────────────────────────────┐
│  LAYER 4: Query Understanding (REFACTORED)               │
│  "User said 'ADR.12' → resolve to specific document"     │
│  → Pre-retrieval: detect ID references, resolve via      │
│    Registry Service, add Weaviate where-filter           │
│  → All patterns from taxonomy.default.yaml only          │
│  → intent_router.py, approval_extractor.py unified       │
└──────────────────────────────────────────────────────────┘
```

### 3.3 Detailed Actions

#### Action 1: Create the ESA Document Ontology Skill

Create `src/skills/esa_document_ontology.md` — a structured knowledge document that captures:

**Section A: Document Types**
- What is an ADR (Architecture Decision Record)?
- What is a PCP (Architecture Principle)?
- What is a DAR (Decision Approval Record)?
- How do DARs relate to ADRs and PCPs? (1:1 relationship, same folder, same number + D suffix)

**Section B: Naming and Identification**
- Official IDs: ADR.NN, PCP.NN (from registry)
- Filename format: NNNN-descriptive-title.md (content), NNNND-descriptive-title.md (DAR)
- The XXXX placeholder convention for drafts
- How users refer to documents (all variations)
- The overlapping number problem (ADR.22 ≠ PCP.22)

**Section C: Repository Structure**
- Folder layout: decisions/ has ADRs + their DARs, principles/ has PCPs + their DARs
- Template files (not documents, authoring aids)
- Registry file (canonical index of all ADRs and PCPs)
- README (repository documentation)

**Section D: Governance**
- Owner groups: ESA, BA, DO
- DACI framework: Driver, Approver, Contributors, Informed
- Status lifecycle: proposed → accepted → deprecated/superseded/revoked
- How ownership is determined (from DAR, from registry)

**Section E: Frontmatter Schema**
- ADR frontmatter fields (parent, nav_order, status, date, driver)
- PCP frontmatter fields (parent, nav_order, dct.identifier, dct.title, owl.versionIRI)
- DAR frontmatter fields (nav_order, dct.identifier, dct.title)
- Known inconsistencies (ADRs lack UUIDs, nav_order format varies)

This skill would be loaded into the LLM context when processing any query about the ESA corpus, giving it grounded understanding rather than pattern-matching.

#### Action 2: Build the Document Registry Service

Create `src/services/document_registry.py`:

```python
class DocumentEntry:
    """A single document in the registry."""
    doc_type: str          # "adr" or "principle"
    canonical_id: str      # "ADR.22" or "PCP.22"
    number: str            # "0022"
    title: str             # "Use priority-based scheduling"
    status: str            # "accepted", "proposed", etc.
    date: str              # "2024-11-14"
    owner: str             # "System Operations - Energy System Architecture Group"
    content_path: Path     # decisions/0022-use-priority-based-scheduling.md
    dar_path: Path         # decisions/0022D-use-priority-based-scheduling.md
    uuid: str | None       # From frontmatter dct.identifier (if available)

class DocumentRegistry:
    """Authoritative lookup service for ESA documents."""

    def load_from_registry_file(self, path: Path) -> None:
        """Parse esa_doc_registry.md into structured entries."""

    def load_from_filesystem(self, doc_path: Path) -> None:
        """Scan decisions/ and principles/ to build entry list."""

    def resolve(self, query: str) -> DocumentEntry | None:
        """Resolve 'ADR.22', 'adr-0022', 'decision 22', etc."""

    def lookup_by_number(self, number: str, doc_type: str = None) -> list[DocumentEntry]:
        """Find by number, optionally filtered by type."""

    def lookup_by_title(self, title_fragment: str) -> list[DocumentEntry]:
        """Fuzzy match on title."""

    def get_dar_for(self, entry: DocumentEntry) -> DocumentEntry | None:
        """Get the DAR corresponding to an ADR or PCP."""

    def list_by_owner(self, owner_fragment: str) -> list[DocumentEntry]:
        """Find all docs by owner group."""

    def list_by_status(self, status: str) -> list[DocumentEntry]:
        """Find all docs with given status."""
```

This service would be:
- Initialized once at startup from both the registry file and the filesystem
- Used by the query pipeline to resolve document references before retrieval
- Used by ingestion to enrich documents with authoritative metadata

#### Action 3: Consolidate Classification

**Remove** duplicate classification in `markdown_loader.py`. Make it call `doc_type_classifier.py` exclusively.

**Fix** `doc_type_classifier.py`:
- Add PRINCIPLE and PRINCIPLE_APPROVAL to `all_types()`
- Deprecate and remove the `content` legacy type with a migration
- Ensure all patterns come from `taxonomy.default.yaml` (no hardcoding)

#### Action 4: Enrich Weaviate Properties

Add queryable metadata properties to Weaviate collections:

```
# Current
adr_number: str       # "0022"
doc_type: str         # "adr"
title: str            # "Use priority-based scheduling"
content: str          # Full text

# Add
canonical_id: str     # "ADR.22"
dar_path: str         # "decisions/0022D-use-priority-based-scheduling.md"
uuid: str             # "urn:uuid:..." (from frontmatter)
owner: str            # "System Operations - Energy System Architecture Group"
owner_abbr: str       # "ESA"
status: str           # "accepted"
date: str             # "2024-11-14"
```

This enables:
- `where: canonical_id = "ADR.22"` for exact lookups
- `where: owner_abbr = "ESA"` for ownership queries
- `where: status = "proposed"` for status filtering

#### Action 5: Pre-Retrieval Document Resolution

Add a `resolve_document_reference()` step in the query pipeline, before Weaviate search:

1. Detect if query contains a document reference (any of the variations in §1.6)
2. Use the Registry Service to resolve it to a specific `DocumentEntry`
3. If resolved: add a Weaviate `where` filter on `canonical_id` or `adr_number`
4. If ambiguous (just a number, could be ADR or PCP): ask for clarification OR search both with the filter

This eliminates the "ADR-0001 beats ADR-0012" problem entirely — it's a lookup, not a search.

#### Action 6: Unify Pattern Sources

All regex patterns should come from ONE place:
- `taxonomy.default.yaml` for document identity patterns
- `routing_policy.yaml` for routing behavior flags

Code modules should import patterns from config, not define their own. Specifically:
- `intent_router.py`: replace hardcoded patterns with config-loaded ones
- `approval_extractor.py`: use shared patterns from config
- `meta_route.py`: use shared negative patterns from config

#### Action 7: Fix Corpus Expectations

Update `corpus_expectations.yaml`:

```yaml
adr:
  unique_count:
    enabled: true
    min: 18     # actual current count
    max: 40     # reasonable growth ceiling
  must_include_ids:
    enabled: true
    values: ["0000", "0001", "0002", "0031"]  # first + latest

principle:
  unique_count:
    enabled: true
    min: 31     # actual current count
    max: 50     # reasonable growth ceiling
  must_include_ids:
    enabled: true
    values: ["0010", "0040"]  # first + latest

dar:
  unique_count:
    enabled: true
    min: 49     # 18 ADR DARs + 31 PCP DARs
    max: 90
```

#### Action 8: Address Source Data Inconsistencies (Suggestions to Repo Maintainers)

These are changes to the source data (`esa-main-artifacts`) that would make automation much more reliable:

1. **Add UUIDs to ADR frontmatter** — PCPs have them, ADRs don't. This breaks UUID-based linking.
2. **Standardize nav_order format** — ADRs use plain numbers (`22`), PCPs use prefixed (`PCP.22`). Pick one.
3. **Add canonical_id to frontmatter** — Instead of deriving `ADR.22` from folder + filename, put `id: ADR.22` in frontmatter.
4. **Add a `dar_ref` column to the registry** — The registry lists ADRs and PCPs but not their DARs. Adding a column with the DAR filename would make the relationship explicit.
5. **Consider a `manifest.yaml` per folder** — Instead of relying on filename parsing, each folder could have a manifest listing its documents with metadata. This is automation-friendly while keeping the human-readable markdown files as-is.

### 3.4 Implementation Priority

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| **P0** | Action 1: Domain Knowledge Skill | Low | High — gives LLM grounded understanding |
| **P0** | Action 5: Pre-retrieval document resolution | Medium | High — fixes the exact-match failure |
| **P1** | Action 2: Document Registry Service | Medium | High — authoritative lookups for everything |
| **P1** | Action 4: Enrich Weaviate properties | Medium | High — enables filtered queries |
| **P2** | Action 3: Consolidate classification | Low | Medium — reduces bugs from duplication |
| **P2** | Action 6: Unify pattern sources | Low | Medium — single source of truth for patterns |
| **P3** | Action 7: Fix corpus expectations | Low | Low — validation improvement |
| **P3** | Action 8: Source data suggestions | External | High — but requires repo maintainer action |

---

## PART 4: INCONSISTENCIES FOUND IN README

Reviewing `README_esa-main-artifacts.md`:

1. **Line 73: `index.md` reference** — README says `doc/index.md` is the Architectural Artifact Registry, but the actual file is `doc/esa_doc_registry.md`. The file was renamed but README still references the old location.

2. **Line 57: Repository structure** — Shows `doc/images/` as a direct child, but images actually live in `doc/decisions/images/`. No `doc/images/` directory exists at the top level (only the GIF referenced in the README).

3. **Contributing section** — Mentions `git push origin feature/new-adr` but there's no branch protection or CI validation described for the naming convention rules.

4. **Missing from README**:
   - No mention that ADR and PCP numbers can overlap (0010-0031 range)
   - No mention of the UUID linkage between content files and DARs
   - No mention of the `nav_order` format differences between ADRs and PCPs
   - No explanation of why some PCPs are in Dutch and others in English
   - No description of how the registry is updated (manual? CI?)

---

## APPENDIX A: Complete File Inventory

### decisions/ (18 ADRs + 18 DARs + 2 templates + 1 index + 1 images dir = 40 files)

| File | Type | ID |
|------|------|----|
| 0000-use-markdown-architectural-decision-records.md | ADR | ADR.00 |
| 0000D-use-markdown-architectural-decision-records.md | DAR | ADR.00D |
| 0001-use-conventions-in-writing.md | ADR | ADR.01 |
| 0001D-use-conventions-in-writing.md | DAR | ADR.01D |
| 0002-use-DACI-for-decision-making-process.md | ADR | ADR.02 |
| 0002D-use-DACI-for-decision-making-process.md | DAR | ADR.02D |
| 0010-prioritize-the-origins-of-standardizations.md | ADR | ADR.10 |
| 0010D-prioritize-the-origins-of-standardizations.md | DAR | ADR.10D |
| 0011-use-standard-for-business-functions.md | ADR | ADR.11 |
| 0011D-use-standard-for-business-functions.md | DAR | ADR.11D |
| 0012-use-CIM-as-default-domain-language.md | ADR | ADR.12 |
| 0012D-use-CIM-as-default-domain-language.md | DAR | ADR.12D |
| 0020-verify-demand-response-products.md | ADR | ADR.20 |
| 0020D-verify-demand-response-products.md | DAR | ADR.20D |
| 0021-use-sign-convention-for-current-direction.md | ADR | ADR.21 |
| 0021D-use-sign-convention-for-current-direction.md | DAR | ADR.21D |
| 0022-use-priority-based-scheduling.md | ADR | ADR.22 |
| 0022D-use-priority-based-scheduling.md | DAR | ADR.22D |
| 0023-flexibility-service-provider-is-responsible-for-acquire-operational-constraints.md | ADR | ADR.23 |
| 0023D-flexibility-service-provider-is-responsible-for-acquire-operational-constraints.md | DAR | ADR.23D |
| 0024-use-standard-for-specifying-the-energy-directing-market-domain.md | ADR | ADR.24 |
| 0024D-use-standard-for-specifying-the-energy-directing-market-domain.md | DAR | ADR.24D |
| 0025-unify-demand-response-interfaces-via-open-standards.md | ADR | ADR.25 |
| 0025D-unify-demand-response-interfaces-via-open-standards.md | DAR | ADR.25D |
| 0026-ensure-idempotent-exchange-of-messages.md | ADR | ADR.26 |
| 0026D-ensure-idempotent-exchange-of-messages.md | DAR | ADR.26D |
| 0027-use-TLS-to-secure-data-communication.md | ADR | ADR.27 |
| 0027D-use-TLS-to-secure-data-communication.md | DAR | ADR.27D |
| 0028-support-participant-initiated-invalidation-of-operating-constraints.md | ADR | ADR.28 |
| 0028D-support-participant-initiated-invalidation-of-operating-constraints.md | DAR | ADR.28D |
| 0029-use-OAuth-2.0--for-identification-authentication-and-authorization.md | ADR | ADR.29 |
| 0029D-use-OAuth-2.0--for-identification-authentication-and-authorization.md | DAR | ADR.29D |
| 0030-identification-based-on-market-participant.md | ADR | ADR.30 |
| 0030D-identification-based-on-market-participant.md | DAR | ADR.30D |
| 0031-use-an-alliander-owned-domain-for-customer-facing-services.md | ADR | ADR.31 |
| 0031D-use-an-alliander-owned-domain-for-customer-facing-services.md | DAR | ADR.31D |
| adr-template.md | Template | - |
| adr-decision-template.md | Template | - |
| index.md | Index | - |

### principles/ (31 PCPs + 31 DARs + 2 templates + 1 index = 65 files)

| File | Type | ID |
|------|------|----|
| 0010-eventual-consistency-by-design.md | PCP | PCP.10 |
| 0010D-eventual-consistency-by-design.md | DAR | PCP.10D |
| 0011-data-design-need-to-know.md | PCP | PCP.11 |
| 0011D-data-design-need-to-know.md | DAR | PCP.11D |
| ... (0012–0040 follow same pattern) | | |
| 0040-energy-efficient-ai.md | PCP | PCP.40 |
| 0040D-energy-efficient-ai.md | DAR | PCP.40D |
| principle-template.md | Template | - |
| principle-decision-template.md | Template | - |
| index.md | Index | - |

### Top-level doc/

| File | Type |
|------|------|
| esa_doc_registry.md | Registry |
| README_esa-main-artifacts.md | README |
