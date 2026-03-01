# ADR Candidates

Decisions to be proposed as formal ADRs through ESA governance.

## Governance

Candidates in this file are working drafts in the AInstein repository.
When a candidate is promoted to a formal proposal, two files must be
produced following the templates in `data/esa-main-artifacts/doc/decisions/`:

1. **ADR document** — from `adr-template.md`. MADR format with
   standardized YAML frontmatter (dct:identifier, dct:title, owl:versionIRI).
   Filename: `NNNN-descriptive-title.md` (number assigned on acceptance).

2. **Decision Approval Record (DAR)** — from `adr-decision-template.md`.
   Captures the governance trail using the DACI model (Driver, Approver,
   Contributor, Informed). Filename: `NNNND-descriptive-title.md`.

An ADR without a DAR is incomplete. Initial status is always `proposed` —
only an Energy System Architect assigns `accepted` via pull request
(4-eyes principle). The AInstein repository never contains accepted
ADRs — it only tracks candidates until they are proposed upstream.

The same rules apply to Principles (PCP) — template and DAR in
`doc/principles/` using `pcp-template.md` and `pcp-decision-template.md`.

---

## Candidate 1: Skill-Based Declarative Agent Architecture

**Context:** AI assistants within the ESA tooling landscape require
extensible capabilities without hardcoded agent classes or custom
orchestration code per capability.

**Decision:** AI capabilities are defined as declarative skills
consisting of a SKILL.md file and a registry entry. Adding a new
capability requires a skill definition and registry configuration —
no additional code or agent classes.

**Consequences:** All AI capabilities follow a uniform pattern.
Skills are composable, testable, and version-controlled independently.
New generation formats (e.g., PlantUML, BPMN) require only a skill
definition and registry entry.

**Status:** Implemented in AInstein. Pending formal ESA proposal.

---

## Candidate 2: Intent-Based Execution Routing

**Context:** Different query types require different execution models.
Retrieval benefits from a RAG pipeline with tool orchestration.
Generation of structured artifacts requires a direct LLM pipeline.
Routing all query types through a single pipeline creates architectural
tension and non-deterministic behavior.

**Decision:** A Persona component classifies user intent. A router
selects the execution path based on intent and skill tags. Skills
declare their execution model (tree or generation) in the registry.

**Consequences:** Clean separation between retrieval and generation
paths. New execution models can be introduced without modifying
existing paths. Routing is deterministic and reproducible.

**Status:** Implemented in AInstein. Pending formal ESA proposal.

---

## Candidate 3: ArchiMate 3.2 Open Exchange XML as Interchange Format

**Context:** Generated architecture models must be importable into
standard modeling tools (Archi, BiZZdesign, MEGA) without manual
conversion.

**Decision:** All generated architecture models use the ArchiMate 3.2
Open Exchange XML format as the standard interchange format.

**Consequences:** Tool-agnostic output. Any ArchiMate 3.2-compliant
tool can import generated models directly. Validation is schema-based
and deterministic.

**Status:** Implemented in AInstein. Pending formal ESA proposal.

---

## Candidate 4: LLM Generation with Deterministic Validation

**Context:** LLMs produce structured output (XML, models) that may
contain syntactic or semantic errors. Relying on the LLM to
self-correct is non-deterministic and token-expensive.

**Decision:** LLMs generate content. Deterministic tooling validates,
sanitizes, and repairs the output. The pipeline follows a fixed
sequence: generate, sanitize, repair views, validate, retry
only if necessary. Mechanical fixes take precedence over LLM retries
for syntactic issues.

**Consequences:** Generation quality scales with model capability.
Validation quality remains consistent regardless of model tier.
Mechanical fixes reduce token usage and latency.

**Status:** Implemented in AInstein. Pending formal ESA proposal.
