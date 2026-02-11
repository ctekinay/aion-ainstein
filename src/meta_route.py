"""Meta route: short-circuit for questions about AInstein itself.

Detects questions about the system's own architecture, skills, formatting,
identity, and processing pipeline. Returns deterministic responses that explain
how AInstein works, without querying the ESA knowledge base.

Response detail is controlled by the ainstein_disclosure_level setting:
- Level 0 (default): functional description, no internals
- Level 1: RAG pipeline overview, no internal component names
- Level 2: full implementation detail (Elysia, Weaviate, DSPy, etc.)

This prevents the "spiral" UX where meta questions get routed to ADR search,
returning irrelevant results or hallucinated process descriptions.
"""

import logging
import re

logger = logging.getLogger(__name__)

# =============================================================================
# Meta Intent Detection
# =============================================================================

# Patterns that indicate the user is asking about AInstein itself,
# not about the ESA knowledge base. Ordered by specificity.
_META_PATTERNS = [
    # Skills / formatting process
    re.compile(r"\b(which|what)\s+skills?\b", re.IGNORECASE),
    re.compile(r"\bhow\s+did\s+you\s+format\b", re.IGNORECASE),
    re.compile(r"\bshow\s+(me\s+)?(the\s+)?(sequential\s+)?steps\b", re.IGNORECASE),
    re.compile(r"\bwhen\s+(did|does)\s+(the\s+)?skill\s+kick", re.IGNORECASE),
    re.compile(r"\bdo\s+you\s+load\s+(skills?|at\s+startup)\b", re.IGNORECASE),
    re.compile(r"\bskill\s+(activation|injection|loading)\b", re.IGNORECASE),

    # System architecture / self-description
    re.compile(r"\b(explain|describe|show)\s+(me\s+)?(your|the\s+system('s)?)\s+(own\s+)?(architecture|design|pipeline)\b", re.IGNORECASE),
    re.compile(r"\bhow\s+(are|were)\s+you\s+built\b", re.IGNORECASE),
    re.compile(r"\bhow\s+do\s+you\s+work\b", re.IGNORECASE),
    re.compile(r"\byour\s+(own\s+)?(architecture|design|system|pipeline)\b", re.IGNORECASE),
    re.compile(r"\bhow\s+(did\s+)?you\s+(came|come)\s+to\s+this\s+answer\b", re.IGNORECASE),
    re.compile(r"\bexplain\s+(the\s+)?process\s+how\s+you\b", re.IGNORECASE),

    # Identity / name questions
    re.compile(r"\bwho\s+are\s+you\b", re.IGNORECASE),
    re.compile(r"\bwhat('?s| is)\s+your\s+name\b", re.IGNORECASE),
    re.compile(r"\bare\s+you\s+(elysia|a\s+bot|an?\s+ai|a\s+language\s+model)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(is|are)\s+you\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+is\s+your\s+purpose\b", re.IGNORECASE),
    re.compile(r"\btell\s+me\s+about\s+yourself\b", re.IGNORECASE),

    # Prompt / embedding internals
    re.compile(r"\b(prompt|embedding|vector)\s+(preserv|mutate|mess|change|modif)", re.IGNORECASE),
    re.compile(r"\bdo\s+you\s+(mess|change|modify)\s+(up\s+)?(the\s+)?(original\s+)?prompt\b", re.IGNORECASE),
    re.compile(r"\bhow\s+can\s+I\s+check\s+this\b", re.IGNORECASE),

    # Debug / trace
    re.compile(r"\b(debug|trace|reasoning)\s*(mode|view|id|log)?\b", re.IGNORECASE),

    # Functional description of "you"
    re.compile(r"\bfunctional\s+description\s+(of\s+)?(your|the\s+system)\b", re.IGNORECASE),
]

# Negative patterns: if these match, it's probably an ESA question, not meta
_NOT_META_PATTERNS = [
    re.compile(r"\badr[.\s-]?\d{1,4}\b", re.IGNORECASE),
    re.compile(r"\bpcp[.\s-]?\d{1,4}\b", re.IGNORECASE),
    re.compile(r"\biec\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bcim\b", re.IGNORECASE),
    re.compile(r"\balliander('s)?\s+(energy|data|policy|principle)\b", re.IGNORECASE),
]


def is_meta_query(question: str) -> bool:
    """Detect if the user is asking about AInstein itself, not the ESA corpus.

    Args:
        question: The user's question

    Returns:
        True if this is a meta/system question that should be short-circuited
    """
    # Check negative patterns first — if the question references specific ESA
    # documents or standards, it's not a meta question even if it uses "your"
    for pattern in _NOT_META_PATTERNS:
        if pattern.search(question):
            return False

    # Check positive patterns
    for pattern in _META_PATTERNS:
        if pattern.search(question):
            logger.info(f"Meta intent detected: matched pattern '{pattern.pattern}'")
            return True

    return False


# =============================================================================
# Meta Response Templates (tiered by disclosure level)
# =============================================================================

# Level 0: functional description — no internals, no component names
_META_RESPONSE_L0 = """I am **AInstein**, the Energy System Architecture AI Assistant at Alliander.

I search the ESA knowledge base and summarize the relevant records for you. I can help with:

- **Architecture Decision Records** (ADRs) and their approval records
- **Data governance principles** (PCPs) and their approval records
- **IEC/CIM vocabulary** and energy sector terminology
- **Data governance policies** and capabilities

If I cannot find relevant information in the knowledge base, I will tell you so rather than guessing.

This explanation describes my capabilities, not the ESA knowledge base."""

# Level 1: power-user — mentions RAG pipeline, no internal component names
_META_RESPONSE_L1 = """I am **AInstein**, the Energy System Architecture AI Assistant at Alliander.

I use **retrieval-augmented generation**: I retrieve relevant passages from the ESA knowledge base, then generate an answer grounded in them.

**How I process your questions:**
1. **Intent classification** — I determine the query type (vocabulary lookup, document fetch, approval extraction, list/count, or semantic search).
2. **Deterministic routing** — For specific documents, approval queries, lists, and counts, I use deterministic extraction with no LLM involvement.
3. **Quality assurance** — Before answering, quality and formatting rules are applied to my working context. Your original question is preserved unchanged.
4. **Retrieval** — For semantic queries, I search the relevant collection(s) using hybrid search (keyword + vector similarity).
5. **Generation** — I synthesize an answer from retrieved documents, applying citation and abstention rules.

**Key design choices:**
- Quality rules are loaded **per query**, not at startup.
- Your prompt is **never modified** — rules are injected separately.
- Approval extraction uses **deterministic parsing** — no LLM interpretation of approver names.
- If retrieval confidence is low, I **abstain** rather than guessing.

**What I can answer:**
- Architecture Decision Records (ADRs) and their approval records
- Data governance principles (PCPs) and their approval records
- IEC/CIM vocabulary and energy sector terminology
- Data governance policies and capabilities

This explanation describes my pipeline, not the ESA knowledge base."""

# Level 2: debug — full implementation detail (Elysia, Weaviate, DSPy, etc.)
_META_RESPONSE_L2 = """I am **AInstein**, the Energy System Architecture AI Assistant at Alliander. Here is how I process your questions:

**Pipeline overview:**
1. **Intent classification** — I determine the query type (vocabulary lookup, specific document fetch, approval extraction, list/count, semantic search, or cross-domain).
2. **Deterministic routing** — For specific documents (e.g., "ADR.0025"), approval queries (e.g., "who approved PCP.0020"), lists, and counts, I use deterministic extraction with no LLM involvement. This ensures reliable, accurate results.
3. **Skill injection** — Before the decision tree executes, quality assurance and formatting rules are appended to my working context. Your original question is preserved unchanged.
4. **Retrieval** — For semantic queries, I search the relevant collection(s) using hybrid search (keyword + vector similarity) against Weaviate.
5. **Generation** — I synthesize an answer from retrieved documents, applying citation and abstention rules.
6. **Response formatting** — Structured output and transparency rules are applied at the response stage, not by modifying your question.

**Key design choices:**
- Skills are loaded **per query**, not at startup. Each query gets fresh skill injection based on its content.
- The user prompt is **never modified**. Skills are injected into the agent description, separate from your question.
- Approval extraction (e.g., "who approved ADR.0025?") uses **deterministic markdown table parsing** — no LLM interpretation of approver names.
- Vocabulary lookups use a **local SKOSMOS index** loaded from IEC/CIM standard TTL files.
- If retrieval confidence is low, the system **abstains** rather than guessing.

**What I can answer:**
- Architecture Decision Records (ADRs) and their approval records
- Data governance principles (PCPs) and their approval records
- IEC/CIM vocabulary and energy sector terminology
- Data governance policies and capabilities

This explanation is generated from my system documentation, not from the ESA knowledge base."""


def build_meta_response(question: str, structured_mode: bool = False) -> str:
    """Build a deterministic response for meta/system questions.

    Response detail is controlled by settings.ainstein_disclosure_level:
    - 0: functional description, no internals
    - 1: RAG pipeline overview, no internal component names
    - 2: full implementation detail

    Args:
        question: The user's question (used for future refinement)
        structured_mode: Whether to wrap in JSON contract format

    Returns:
        Response text (plain or JSON-wrapped)
    """
    from .config import settings

    level = settings.ainstein_disclosure_level
    if level >= 2:
        body = _META_RESPONSE_L2
    elif level >= 1:
        body = _META_RESPONSE_L1
    else:
        body = _META_RESPONSE_L0

    if structured_mode:
        import json
        return json.dumps({
            "schema_version": "1.0",
            "answer": body,
            "items_shown": 0,
            "items_total": 0,
            "count_qualifier": None,
            "transparency_statement": "This response describes the AInstein system architecture. No ESA documents were retrieved.",
            "sources": [],
        }, indent=2)

    return body
