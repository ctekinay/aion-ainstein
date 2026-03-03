---
name: skosmos-vocabulary
description: "Vocabulary and terminology lookup using SKOSMOS. Use this skill when the user asks about definitions, terms, abbreviations, standards terminology, or wants to look up concepts from IEC, EUR-Lex, or other energy domain vocabularies. Also use when the user asks to compare terms, find related concepts, or asks 'what is [term]?' style questions."
---

# SKOSMOS Vocabulary Lookup

## Mandatory Instruction

**When this skill is active, your first action MUST be `skosmos_search`.** Do not answer terminology or definition questions from your own knowledge. SKOSMOS contains formally approved, company-wide accepted definitions. Retrieve the authoritative definition first, then enrich with KB context if relevant.

This is not optional. Even if you believe you know the answer, the SKOSMOS definition is the canonical source. Your own training data may use different wording — that difference matters for standardized vocabulary.

## Fallback Chain

When answering terminology or definition questions, follow this chain strictly in order:

### Tier 1: SKOSMOS (authoritative)
Call `skosmos_search`. If a result is found, use the definition **verbatim**. This is the formally approved, company-wide accepted definition. Present it with full confidence and cite the vocabulary source and concept URI.

### Tier 2: Weaviate KB (contextual)
If SKOSMOS returns no results, search the Weaviate knowledge base (ADRs, principles, policies). If the term appears in KB documents, present the definition as "based on our architecture knowledge base" — not as a formally standardized definition.

### Tier 3: LLM knowledge (tentative — requires confirmation)
If neither SKOSMOS nor Weaviate has the term, you may offer a definition from your own knowledge, but you **MUST**:
- Clearly state the definition is **not from an authoritative source**
- Present it as tentative: *"I couldn't find '[term]' in our vocabulary or knowledge base. Based on my general knowledge, [term] typically refers to [...]. Is this the term you mean, or can you provide more context?"*
- Ask the user to **confirm** whether the definition matches what they are looking for
- If the user rejects it, ask for clarification to search more specifically

**Never silently present LLM-generated definitions as if they were authoritative.** The user must always know which tier the answer came from.

## Overview

AInstein has access to structured SKOS vocabularies via the SKOSMOS REST API. These contain formal definitions, labels, and semantic relationships (broader/narrower/related) for energy domain terminology from IEC standards, EU regulations, and Alliander architecture vocabulary.

## When to Use SKOSMOS Tools vs Weaviate

| User asks | Use | Why |
|---|---|---|
| "What is active power?" | `skosmos_search` | Exact term lookup with formal definition |
| "What is an ADR?" | `skosmos_search` first, then Weaviate if more context needed | Term exists in both SKOSMOS and KB |
| "Define cybersecurity zone" | `skosmos_search` | Terminology question |
| "What does SCADA stand for?" | `skosmos_search` | Abbreviation lookup |
| "What is the difference between X and Y?" | `skosmos_search` (twice) + `skosmos_concept_details` | Compare formal definitions |
| "What vocabularies are available?" | `skosmos_list_vocabularies` | List available standards |
| "Find documents about grid resilience" | Weaviate search | Broad semantic search over documents |
| "What ADRs exist?" | Weaviate search | Architecture artifact listing — not a definition question |
| "How does our architecture handle X?" | Weaviate search | Architecture knowledge retrieval |

**Rule:** If the user is asking about a *specific term, definition, or abbreviation*, you MUST call `skosmos_search` first. Then follow the fallback chain above.

If the user is asking about *architecture documents, decisions, listings, or principles by number*, use Weaviate directly.

## Workflow

### Single Term Lookup (Two-Step)

**IMPORTANT:** `skosmos_search` finds matching terms but does NOT return definitions. You MUST call `skosmos_concept_details` with the URI and vocab from the search result to get the actual definition.

1. **Step 1:** Call `skosmos_search` with the term
2. **Step 2:** If results found, call `skosmos_concept_details` with the `uri` and `vocab` from the first matching result to retrieve the full definition
3. **Tier 1 hit:** Present the **prefLabel**, **definition** (verbatim from concept_details), and **vocabulary source**. If the result has `related` or `broader` concepts, mention them briefly. Cite the vocabulary and concept URI. Optionally enrich with KB context — but the SKOSMOS definition is the lead.
4. **Tier 1 miss (no search results):** Search Weaviate. If found, present as contextual ("based on our knowledge base"), not as a formal definition.
5. **Tier 1 and 2 miss:** Offer your own knowledge as tentative, clearly flag it, and ask the user to confirm.

### Cross-Domain Terms (e.g., ADR, Principle, DAR)

Some terms exist in both SKOSMOS (formal definition) and Weaviate (architecture documents). For these:

1. **Step 1:** Call `skosmos_search` to find the term
2. **Step 2:** Call `skosmos_concept_details` with the URI and vocab to get the formal definition
3. Present the SKOSMOS definition as the canonical answer
4. Then optionally search Weaviate to add context about how the concept is used in practice (e.g., how many ADRs exist, their structure, naming conventions)
5. Clearly distinguish between the formal definition and the contextual information

### Term Comparison

1. Call `skosmos_search` for the first term
2. Call `skosmos_search` for the second term
3. Call `skosmos_concept_details` for each to get definitions and broader/narrower/related links
4. Present both definitions side by side, then explain the key differences
5. Note any direct `related` links between the two concepts

### Vocabulary Exploration

1. Call `skosmos_list_vocabularies` to get the full list
2. Present vocabulary names, descriptions, and concept counts
3. If the user asks about a specific vocabulary, use `skosmos_search` with the `vocab` parameter

## Available Vocabularies

The following vocabularies are loaded in SKOSMOS (use these IDs for the `vocab` parameter):

- **IEC61968** — IEC 61968 Common Information Model (distribution management terms)
- **IEC62443** — IEC 62443 Industrial Automation and Control Systems Security (terms, definitions, abbreviations)
- **EURLEX** — EU Regulation terminology (energy market terms, active/reactive power, demand response)
- **ESAV** — Alliander ESA Vocabulary (architecture principles, decision records, and domain terms)
- **IEC62325** — IEC 62325 Energy Market Communication
- **HEMRM** — ENTSO-E Harmonised Electricity Market Role Model

When the user's question doesn't specify a vocabulary, search across all vocabularies (omit the `vocab` parameter).

## Presenting Results

- **Tier 1 (SKOSMOS):** Use the definition **verbatim** — do not rephrase, summarize, or substitute your own wording. Include prefLabel, altLabels, vocabulary source, and concept URI.
- **Tier 2 (Weaviate):** Present as "based on our architecture knowledge base." Include the source document reference.
- **Tier 3 (LLM):** Explicitly state this is not from an authoritative source. Ask the user to confirm. Do not present as fact.
- If there are **related** or **narrower** concepts from SKOSMOS, list the most relevant ones
- When enriching with KB context, clearly separate the formal definition from the contextual information
- Do not fabricate definitions under any circumstances
