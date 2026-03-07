---
parent: Decisions
nav_order: ADR.NN
dct:
  identifier: urn:uuid:a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
  title: "Use declarative skill definitions for AI agent capabilities"
  isVersionOf: proposed
  issued: 2026-03-06
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2026-03/NNNN-skill-based-declarative-agent-architecture.html"
  versionInfo: "v1.0.0 (2026-03-06)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Use declarative skill definitions for AI agent capabilities

## Context and Problem Statement

AI assistants within the ESA tooling landscape require extensible capabilities — the
ability to answer questions about architecture decisions, generate ArchiMate models,
query vocabulary services, and more. As the number of capabilities grows, a pattern is
needed that allows adding, modifying, and removing capabilities without writing new
agent classes, modifying orchestration code, or redeploying the system for each change.

How should AI agent capabilities be defined and managed so that they are extensible,
version-controlled, and independently testable without requiring code changes per
capability?

## Decision Drivers

* Enable non-developer domain experts (architects, knowledge managers) to define and
  modify AI capabilities through configuration rather than code.
* Ensure capabilities are composable — multiple skills can be active simultaneously
  and injected into the agent's context without interference.
* Support independent versioning and testing of individual capabilities without
  affecting the rest of the system.
* Minimize the code footprint required to add a new capability — ideally zero lines
  of new Python code for prompt-driven capabilities.
* Maintain a clear separation between what the agent *can* do (skill definitions) and
  how the agent *decides* what to do (orchestration logic).

## Considered Options

1. **Hardcoded agent classes per capability** — Each capability is implemented as a
   dedicated Python class with its own prompt logic, tool selection, and response
   formatting. New capabilities require new classes and code deployment.

2. **Plugin architecture with code modules** — Capabilities are defined as Python
   modules loaded dynamically at runtime. Each module registers tools, prompts, and
   handlers. New capabilities require writing Python code in a prescribed module format.

3. **Declarative skill definitions (SKILL.md + registry)** — Capabilities are defined
   as markdown files containing system prompts, rules, and reference material, with a
   YAML registry that declares metadata (name, execution model, active/inactive
   status). The orchestration layer injects active skill content into the LLM context.
   New capabilities require only a SKILL.md file and a registry entry.

4. **Configuration-driven prompt chains** — Capabilities are defined as JSON/YAML
   configurations specifying prompt templates, tool sequences, and response schemas.
   A generic executor interprets the configuration at runtime.

## Decision Outcome

Chosen option: "Declarative skill definitions (SKILL.md + registry)", because it
is the only option that allows domain experts to define capabilities without writing
code, supports version control through standard git workflows on markdown files, and
maintains a clean separation between capability definitions and orchestration logic.

### Consequences

* Good, because adding a new capability (e.g., BPMN generation, compliance checking)
  requires only a SKILL.md file and a registry entry — zero Python code for
  prompt-driven capabilities.
* Good, because skill definitions are plain markdown — reviewable, diffable, and
  understandable by non-developers.
* Good, because skills can be activated or deactivated through the registry without
  code changes or redeployment.
* Good, because reference material (element type lists, allowed relations, thresholds)
  is co-located with the skill definition and version-controlled together.
* Bad, because capabilities that require custom tool implementations (e.g., Weaviate
  search tools, external API integrations) still need Python code alongside the
  skill definition.
* Bad, because the declarative approach limits expressiveness — complex multi-step
  workflows with conditional branching are harder to express in markdown prompts
  than in code.

### Confirmation

Compliance can be confirmed by verifying that:
1. New capabilities added after adoption consist of a SKILL.md file and a registry
   entry, with no new Python agent classes.
2. The skills registry (`skills/skills-registry.yaml`) contains entries for all
   active capabilities.
3. Skill content is injected into the LLM context via the atlas injection mechanism,
   not through hardcoded prompt strings in Python code.

## Pros and Cons of the Options

### Hardcoded agent classes per capability

Each capability is a Python class with its own prompt construction, tool registration,
and response handling.

* Good, because full control over each capability's behavior.
* Good, because standard Python debugging and testing applies.
* Bad, because adding a capability requires a developer, code review, and deployment.
* Bad, because prompt content is embedded in code, making it opaque to domain experts.
* Bad, because capabilities cannot be toggled without code changes.
* Bad, because the number of classes grows linearly with capabilities, increasing
  maintenance burden.

### Plugin architecture with code modules

Capabilities are Python modules loaded dynamically, each registering tools and prompts
through a prescribed interface.

* Good, because new capabilities can be added without modifying core code.
* Good, because each module is independently testable.
* Neutral, because it requires a module loading framework and interface contract.
* Bad, because still requires Python development skills to add capabilities.
* Bad, because module interface versioning adds complexity.
* Bad, because prompt content remains embedded in code rather than in reviewable
  documents.

### Declarative skill definitions (SKILL.md + registry)

Capabilities defined as markdown files with a YAML registry. The orchestration layer
reads active skills and injects their content into the LLM context.

* Good, because zero-code capability addition for prompt-driven skills.
* Good, because domain experts can author and review skill definitions.
* Good, because version control and diff tooling work naturally on markdown.
* Good, because skills are composable — multiple can be active simultaneously.
* Neutral, because custom tool implementations still require Python code.
* Bad, because complex conditional workflows are harder to express declaratively.

### Configuration-driven prompt chains

Capabilities defined as JSON/YAML configurations specifying prompt templates, tool
sequences, and response schemas.

* Good, because no Python code required for new capabilities.
* Good, because configurations can be validated against a schema.
* Bad, because JSON/YAML prompt chains are harder to read and review than markdown.
* Bad, because the configuration schema becomes a framework in itself, requiring
  its own documentation and maintenance.
* Bad, because debugging prompt chain execution requires understanding the
  interpreter, adding a layer of indirection.

## More Information

### Implementation in AInstein

AInstein implements this pattern with the following structure:

- **Skill definitions:** `skills/<skill-name>/SKILL.md` — markdown files containing
  system prompts, behavioral rules, and formatting guidance.
- **Reference material:** `skills/<skill-name>/references/` — supporting documents
  (element type lists, thresholds, templates) co-located with the skill.
- **Registry:** `skills/skills-registry.yaml` — declares skill metadata including
  name, description, execution model, and active/inactive status.
- **Injection:** The skill loader parses active skills and injects their content into
  the LLM context via `tree_data.atlas.agent_description` before each query.

As of March 2026, AInstein has 8 active skills defined this way, covering identity,
response formatting, RAG quality assurance, ArchiMate generation, vocabulary querying,
and document ontology awareness.
