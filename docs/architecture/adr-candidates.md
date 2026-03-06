# ADR Candidates

Registry of architectural decision candidates to be proposed as formal ADRs
through ESA governance.

## Scope

This document tracks two categories of ADR candidates:

1. **Ecosystem-wide, tool-agnostic decisions** — Architectural choices that
   apply across the ESA tooling landscape regardless of specific tool
   implementations. These concern standards, interoperability patterns, and
   cross-cutting concerns that any ESA-aligned system should follow.

2. **Tool-specific decisions** — Architectural choices specific to AInstein
   (or another tool/technology) that represent significant design decisions
   within that tool's scope. These are documented for governance and knowledge
   sharing but may not apply to other ESA systems.

Each candidate links to a fully drafted ADR and DAR under
`docs/architecture/generated-candidates/`.

## Governance

When a candidate is promoted to a formal proposal, the generated drafts serve
as the starting point. Two files must be produced following the templates in
`data/esa-main-artifacts/doc/decisions/`:

1. **ADR document** — from `adr-template.md`. MADR format with standardized
   YAML frontmatter (dct:identifier, dct:title, owl:versionIRI).
   Filename: `NNNN-descriptive-title.md` (number assigned on acceptance).

2. **Decision Approval Record (DAR)** — from `adr-decision-template.md`.
   Captures the governance trail using the DACI model (Driver, Approver,
   Contributor, Informed). Filename: `NNNND-descriptive-title.md`.

An ADR without a DAR is incomplete. Initial status is always `proposed` —
only an Energy System Architect assigns `accepted` via pull request
(4-eyes principle). The AInstein repository never contains accepted
ADRs — it only tracks candidates until they are proposed upstream.

---

## Ecosystem-Wide Candidates

| # | Title | Status | Draft |
|---|-------|--------|-------|
| C3 | [ArchiMate Open Exchange XML as Interchange Format](#c3-archimate-open-exchange-xml-as-interchange-format) | Implemented in AInstein | [ADR](generated-candidates/C3-archimate-open-exchange-xml-as-interchange-format.md) · [DAR](generated-candidates/C3D-archimate-open-exchange-xml-as-interchange-format.md) |
| C5 | [Knowledge Base Traceability in Generated Artifacts](#c5-knowledge-base-traceability-in-generated-artifacts) | Implemented in AInstein | [ADR](generated-candidates/C5-knowledge-base-traceability-in-generated-artifacts.md) · [DAR](generated-candidates/C5D-knowledge-base-traceability-in-generated-artifacts.md) |

## Tool-Specific Candidates (AInstein)

| # | Title | Status | Draft |
|---|-------|--------|-------|
| C1 | [Skill-Based Declarative Agent Architecture](#c1-skill-based-declarative-agent-architecture) | Implemented in AInstein | [ADR](generated-candidates/C1-skill-based-declarative-agent-architecture.md) · [DAR](generated-candidates/C1D-skill-based-declarative-agent-architecture.md) |
| C2 | [Intent-Based Execution Routing](#c2-intent-based-execution-routing) | Implemented in AInstein | [ADR](generated-candidates/C2-intent-based-declarative-execution-routing.md) · [DAR](generated-candidates/C2D-intent-based-declarative-execution-routing.md) |
| C4 | [LLM Generation with Deterministic Validation](#c4-llm-generation-with-deterministic-validation) | Implemented in AInstein | [ADR](generated-candidates/C4-llm-generation-with-deterministic-validation.md) · [DAR](generated-candidates/C4D-llm-generation-with-deterministic-validation.md) |

---

## Candidate Summaries

### C1: Skill-Based Declarative Agent Architecture

**Category:** Tool-specific (AInstein)

AI capabilities are defined as declarative skills consisting of a SKILL.md
file and a registry entry. Adding a new capability requires a skill definition
and registry configuration — no additional code or agent classes. All AI
capabilities follow a uniform pattern: composable, testable, and
version-controlled independently.

### C2: Intent-Based Execution Routing

**Category:** Tool-specific (AInstein)

A Persona component classifies user intent via LLM. A router selects the
execution path based on intent and skill tags. Skills declare their execution
model (RAG tree or direct LLM pipeline) in the registry. This cleanly
separates retrieval from generation paths and makes routing deterministic.

### C3: ArchiMate Open Exchange XML as Interchange Format

**Category:** Ecosystem-wide

Generated architecture models use the ArchiMate Open Exchange XML format as
the standard interchange format, ensuring tool-agnostic output importable by
any compliant modeling tool (Archi, BiZZdesign, MEGA). Validation is
schema-based and deterministic.

### C4: LLM Generation with Deterministic Validation

**Category:** Tool-specific (AInstein)

LLMs generate content; deterministic tooling validates, sanitizes, and repairs
the output. The pipeline follows a fixed sequence: generate → sanitize →
repair views → validate → retry only if necessary. Mechanical fixes take
precedence over LLM retries for syntactic issues.

### C5: Knowledge Base Traceability in Generated Artifacts

**Category:** Ecosystem-wide

Generated artifacts embed real knowledge base identifiers (UUIDs) as Dublin
Core `dct:identifier` properties, creating a machine-readable provenance link
between generated model elements and their authoritative source documents.
Any tool in the ESA ecosystem generating artifacts from a shared knowledge
base should follow the same traceability pattern.
