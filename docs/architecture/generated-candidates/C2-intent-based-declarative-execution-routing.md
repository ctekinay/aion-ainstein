---
parent: Decisions
nav_order: ADR.NN
dct:
  identifier: urn:uuid:b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e
  title: "Route AI agent execution by classified intent and skill-declared execution model"
  isVersionOf: proposed
  issued: 2026-03-06
owl:
  versionIRI: "https://esa-artifacts.alliander.com/metamodel/decisions/2026-03/NNNN-intent-based-execution-routing.html"
  versionInfo: "v1.0.0 (2026-03-06)"
---
<!-- markdownlint-disable-next-line MD025 -->

# Route AI agent execution by classified intent and skill-declared execution model

## Context and Problem Statement

An AI assistant that supports both knowledge retrieval (searching architecture
decisions, principles, policies) and content generation (producing ArchiMate models,
structured artifacts) must select the appropriate execution pipeline for each query.
Retrieval queries benefit from a RAG pipeline with tool orchestration and vector
search. Generation queries require a direct LLM pipeline with schema validation and
iterative refinement. Routing all query types through a single pipeline creates
architectural tension: the RAG pipeline terminates prematurely on generation tasks
(it considers retrieved context sufficient), while the generation pipeline lacks
the multi-tool search capabilities needed for retrieval.

How should the system determine which execution pipeline to use for each user query?

## Decision Drivers

* Ensure retrieval queries use a pipeline optimized for multi-source search,
  deduplication, and cited summarization.
* Ensure generation queries use a pipeline optimized for structured output,
  schema validation, and iterative refinement.
* Avoid routing failures where a query enters the wrong pipeline and produces
  degraded results (e.g., a generation request answered with a retrieval summary).
* Support adding new execution models (e.g., inspection, comparison) without
  modifying existing pipeline code.
* Keep the routing decision transparent and auditable — the system should report
  which intent was classified and which pipeline was selected.

## Considered Options

1. **Keyword-based routing** — Pattern-match queries against keyword lists to
   determine the execution pipeline. E.g., "generate" → generation pipeline,
   "list" → retrieval pipeline.

2. **Single unified pipeline** — Route all queries through one pipeline that
   attempts to handle both retrieval and generation within the same execution flow.

3. **LLM-based intent classification with skill-declared execution models** — An
   LLM Persona classifies user intent (retrieval, generation, identity, off-topic)
   in a single call. Skills declare their execution model in the registry. The
   router matches classified intent to the appropriate pipeline.

4. **User-explicit routing** — Require users to specify the desired operation type
   (e.g., "/search" vs "/generate") through command prefixes or UI controls.

## Decision Outcome

Chosen option: "LLM-based intent classification with skill-declared execution models",
because it handles ambiguous natural language queries that keyword matching cannot
classify reliably, supports transparent routing decisions, and allows new execution
models to be introduced by adding registry entries rather than modifying router code.

### Consequences

* Good, because the LLM handles ambiguous and conversational queries that keyword
  matching fails on (e.g., "can you model the principles about data quality?" requires
  understanding that "model" means ArchiMate generation, not retrieval).
* Good, because skills declare their execution model in the registry, so adding a new
  pipeline only requires a registry entry — no router code changes.
* Good, because the Persona emits intent classification as a visible event, making
  routing decisions transparent and debuggable.
* Good, because the Persona also rewrites queries for follow-up context (pronoun
  resolution, conversation history), improving downstream pipeline quality.
* Bad, because intent classification adds latency (one LLM call before pipeline
  execution — 5–12 seconds locally, <1 second with cloud models).
* Bad, because misclassification sends queries to the wrong pipeline with no
  automatic recovery — the user must rephrase.

### Confirmation

Compliance can be confirmed by verifying that:
1. No keyword-based routing logic exists outside the documented fallback path.
2. The Persona emits a `persona_intent` event for every query, visible in the UI.
3. Skills in `skills-registry.yaml` declare an `execution_model` field.
4. New execution pipelines added after adoption are selected via the registry, not
   through hardcoded conditions in the router.

## Pros and Cons of the Options

### Keyword-based routing

Pattern-match queries against keyword lists (e.g., "generate", "create", "list",
"compare") to select execution pipeline.

* Good, because zero latency — no LLM call needed.
* Good, because deterministic and predictable behavior.
* Bad, because natural language is ambiguous — "model" can mean "explain" or
  "generate an ArchiMate model" depending on context.
* Bad, because keyword lists grow unmanageably and still miss edge cases.
* Bad, because multi-language support (Dutch/English) doubles the keyword lists.
* Bad, because 10 keyword-triggered routes were built and deleted during AInstein's
  development (commit 265: -600 lines) due to unreliable classification.

### Single unified pipeline

One pipeline handles both retrieval and generation, deciding internally how to
respond.

* Good, because simpler architecture — one pipeline to maintain.
* Bad, because the RAG pipeline's termination condition (sufficient retrieved context)
  conflicts with generation tasks that need structured output after retrieval.
* Bad, because generation-specific steps (schema validation, XML sanitization, view
  repair) have no natural place in a retrieval-focused pipeline.
* Bad, because pipeline configuration becomes complex as it tries to serve
  contradictory requirements.

### LLM-based intent classification with skill-declared execution models

A Persona component classifies intent via LLM. Skills declare their execution model.
A router maps classified intent to the appropriate pipeline.

* Good, because handles ambiguous natural language reliably.
* Good, because transparent — classification is emitted as an event.
* Good, because extensible via registry entries.
* Good, because the Persona also provides query rewriting for conversation context.
* Neutral, because adds one LLM call of latency per query.
* Bad, because misclassification has no automatic recovery path.

### User-explicit routing

Users specify operation type through commands or UI controls.

* Good, because zero ambiguity — the user declares intent explicitly.
* Good, because no classification latency.
* Bad, because poor user experience — users must learn command syntax.
* Bad, because conversational follow-ups ("now generate a model for that") require
  the user to switch modes explicitly.
* Bad, because it shifts cognitive load from the system to the user.

## More Information

### Implementation in AInstein

AInstein implements this pattern through a three-component architecture:

- **Persona** (`src/aion/persona.py`): Classifies intent and rewrites queries in a
  single LLM call. Outputs a JSON object `{"intent": "...", "content": "..."}` with
  a line-based fallback parser.
- **Skills Registry** (`skills/skills-registry.yaml`): Each skill declares its
  execution model (e.g., `tree` for RAG, `generation` for direct LLM pipeline).
- **Router** (`src/aion/chat_ui.py`): Maps the Persona's classified intent to the
  skill's declared execution model and dispatches to the appropriate pipeline.

The Persona maintains conversation context through structured turn summaries,
enabling accurate follow-up classification (e.g., "show me the first three" after
"what principles exist?" correctly routes to retrieval with the right context).
