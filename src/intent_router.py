"""Intent-first query router for AION-AINSTEIN.

Replaces keyword-triggered routing with explicit intent classification.
Returns a stable IntentDecision schema that downstream routing can act on
deterministically.

Two implementations:
  1. heuristic_classify() — fast, regex-based, no LLM call
  2. llm_classify()       — uses the configured LLM for nuanced intent

Feature flag: AINSTEIN_INTENT_ROUTER_MODE controls which runs (heuristic|llm).
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List

logger = logging.getLogger(__name__)


# =============================================================================
# Intent Schema
# =============================================================================

class Intent(str, Enum):
    """Primary intent of the user query."""
    LIST = "list"
    COMPARE_COUNTS = "compare_counts"
    COMPARE_CONCEPTS = "compare_concepts"
    LOOKUP_APPROVAL = "lookup_approval"
    LOOKUP_DOC = "lookup_doc"
    SEMANTIC_ANSWER = "semantic_answer"
    META = "meta"
    COUNT = "count"
    UNKNOWN = "unknown"


class EntityScope(str, Enum):
    """Which document collection(s) the query targets."""
    ADR = "adr"
    PCP = "pcp"
    DAR_ADR = "dar_adr"
    DAR_PCP = "dar_pcp"
    DAR_ALL = "dar_all"
    POLICY = "policy"
    VOCAB = "vocab"
    MULTI = "multi"           # cross-domain
    UNKNOWN = "unknown"


class OutputShape(str, Enum):
    """Expected shape of the response."""
    SHORT_ANSWER = "short_answer"
    LIST = "list"
    TABLE = "table"
    EXPLANATION = "explanation"
    CLARIFICATION = "clarification"


@dataclass
class IntentDecision:
    """Stable schema returned by the intent router.

    Downstream routing uses this to decide which path to take
    instead of ad-hoc keyword matching.
    """
    intent: Intent
    entity_scope: EntityScope
    output_shape: OutputShape
    confidence: float                            # 0.0 – 1.0
    reasoning: str = ""                          # human-readable explanation
    detected_entities: List[str] = field(default_factory=list)  # e.g. ["ADR.0025"]
    clarification_options: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["intent"] = self.intent.value
        d["entity_scope"] = self.entity_scope.value
        d["output_shape"] = self.output_shape.value
        return d


# =============================================================================
# Default confidence threshold — below this we ask a clarifying question
# =============================================================================
DEFAULT_CONFIDENCE_THRESHOLD = 0.55


# =============================================================================
# Heuristic Classifier (fast, no LLM)
# =============================================================================

# ---- regex building blocks ----

_DOC_REF_RE = re.compile(
    r"\b(?:adr|pcp|dar)[.\s-]?\d{1,4}\b",
    re.IGNORECASE,
)

_ADR_RE = re.compile(r"\badrs?\b", re.IGNORECASE)
_PCP_RE = re.compile(r"\b(?:pcps?|principles?)\b", re.IGNORECASE)
_DAR_RE = re.compile(r"\bdars?\b|decision\s+approval\s+record", re.IGNORECASE)
_POLICY_RE = re.compile(r"\bpolic(?:y|ies)\b", re.IGNORECASE)
_VOCAB_RE = re.compile(
    r"\b(?:concept|term|definition|vocabulary|ontology|skos|iec|cim|"
    r"standard|meaning|semantic|taxonomy|owl|rdf|archimate)\b",
    re.IGNORECASE,
)

_LIST_VERBS_RE = re.compile(
    r"\b(?:list|show|enumerate|give\s+me|display)\b"
    r"|\b(?:what|which)\s+\w+s?\s+(?:are|exist|do\s+we\s+have)\b"
    r"|\b(?:what|which)\s+are\s+(?:all\s+)?(?:the\s+)?\w+"
    r"|\bshow\s+(?:me\s+)?all\b",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(
    r"\bhow\s+many\b|\btotal\s+(?:number|count)\b|\bcount\b",
    re.IGNORECASE,
)

_COMPARE_RE = re.compile(
    r"\b(?:difference|compare|differ|vs|versus)\b"
    r"|\bdifferent\s+(?:from|than|between)\b"
    r"|\b(?:more|fewer|less)\s+\w+\s+than\b",
    re.IGNORECASE,
)
_COMPARE_COUNTS_RE = re.compile(
    r"\b(?:more|fewer|less)\b.*\bthan\b"
    r"|\bhow\s+many\b.*\bvs\b"
    r"|\bcompare\s+(?:the\s+)?(?:number|count)"
    r"|\bdo\s+we\s+have\s+more\b",
    re.IGNORECASE,
)

_META_RE = re.compile(
    r"\b(?:who\s+are\s+you|what\s+(?:are|is)\s+you|your\s+(?:name|architecture|pipeline))\b"
    r"|\b(?:how\s+do\s+you\s+work|explain\s+your|your\s+skills?)\b"
    r"|\bare\s+you\s+(?:elysia|ainstein|an?\s+(?:ai|llm|bot))\b"
    r"|\b(?:skills?|tools?)\s+(?:did|do)\s+you\s+use\b"
    r"|\byour\s+own\s+(?:architecture|pipeline|design)\b",
    re.IGNORECASE,
)

_APPROVAL_RE = re.compile(
    r"\b(?:who\s+approved|approvers?|signed\s+off|daci|approval)\b",
    re.IGNORECASE,
)

_DEFINITIONAL_RE = re.compile(
    r"\bwhat\s+(?:is|are)\s+(?:a|an|the)?\s*(?:dar|adr|pcp)\b"
    r"|\bdefine\s+(?:dar|adr|pcp)\b"
    r"|\bmeaning\s+of\s+(?:dar|adr|pcp)\b",
    re.IGNORECASE,
)

_SPECIFIC_DOC_RE = re.compile(
    r"\b(?:tell\s+me\s+about|explain|details?\s+(?:of|about|on)|status\s+of|"
    r"what\s+(?:does|did|is)\s+(?:adr|pcp|dar))\b",
    re.IGNORECASE,
)


def _detect_entity_scope(question: str) -> EntityScope:
    """Infer which collection(s) the question targets."""
    q = question.lower()
    has_adr = bool(_ADR_RE.search(q))
    has_pcp = bool(_PCP_RE.search(q))
    has_dar = bool(_DAR_RE.search(q))
    has_policy = bool(_POLICY_RE.search(q))
    has_vocab = bool(_VOCAB_RE.search(q))

    # DAR scoping
    if has_dar:
        if has_adr and not has_pcp:
            return EntityScope.DAR_ADR
        if has_pcp and not has_adr:
            return EntityScope.DAR_PCP
        if has_adr and has_pcp:
            return EntityScope.DAR_ALL
        return EntityScope.DAR_ALL

    # multi-collection
    entity_count = sum([has_adr, has_pcp, has_policy, has_vocab])
    if entity_count > 1:
        return EntityScope.MULTI

    if has_adr:
        return EntityScope.ADR
    if has_pcp:
        return EntityScope.PCP
    if has_policy:
        return EntityScope.POLICY
    if has_vocab:
        return EntityScope.VOCAB

    return EntityScope.UNKNOWN


def _detect_doc_references(question: str) -> list[str]:
    """Extract explicit document references like ADR.0025, PCP.10."""
    return _DOC_REF_RE.findall(question)


def heuristic_classify(question: str) -> IntentDecision:
    """Fast, regex-based intent classification.

    Priority order mirrors the old routing cascade but produces a
    stable schema instead of scattered if/elif branches.
    """
    q_lower = question.lower().strip()
    entity_scope = _detect_entity_scope(question)
    doc_refs = _detect_doc_references(question)

    # ---- META (highest priority) ----
    if _META_RE.search(question):
        return IntentDecision(
            intent=Intent.META,
            entity_scope=EntityScope.UNKNOWN,
            output_shape=OutputShape.EXPLANATION,
            confidence=0.95,
            reasoning="Meta question about AInstein itself",
        )

    # ---- SPECIFIC DOCUMENT LOOKUP (has doc reference like ADR.0025) ----
    if doc_refs:
        # approval sub-intent
        if _APPROVAL_RE.search(question):
            return IntentDecision(
                intent=Intent.LOOKUP_APPROVAL,
                entity_scope=entity_scope,
                output_shape=OutputShape.TABLE,
                confidence=0.92,
                reasoning=f"Approval query with doc ref: {doc_refs}",
                detected_entities=doc_refs,
            )
        return IntentDecision(
            intent=Intent.LOOKUP_DOC,
            entity_scope=entity_scope,
            output_shape=OutputShape.EXPLANATION,
            confidence=0.90,
            reasoning=f"Specific document lookup: {doc_refs}",
            detected_entities=doc_refs,
        )

    # ---- APPROVAL (no specific doc ref) ----
    if _APPROVAL_RE.search(question):
        return IntentDecision(
            intent=Intent.LOOKUP_APPROVAL,
            entity_scope=entity_scope if entity_scope != EntityScope.UNKNOWN else EntityScope.DAR_ALL,
            output_shape=OutputShape.LIST,
            confidence=0.82,
            reasoning="Approval intent without specific doc reference",
        )

    # ---- COMPARE COUNTS ("do we have more DARs for ADRs than PCPs?") ----
    if _COMPARE_COUNTS_RE.search(question):
        return IntentDecision(
            intent=Intent.COMPARE_COUNTS,
            entity_scope=entity_scope if entity_scope != EntityScope.UNKNOWN else EntityScope.DAR_ALL,
            output_shape=OutputShape.TABLE,
            confidence=0.85,
            reasoning="Count comparison detected",
        )

    # ---- COMPARE CONCEPTS ("What's the difference between ADR and PCP?") ----
    if _COMPARE_RE.search(question):
        # Check if two+ distinct entity types are mentioned (including DAR combos)
        q = question.lower()
        has_adr = bool(_ADR_RE.search(q))
        has_pcp = bool(_PCP_RE.search(q))
        has_dar = bool(_DAR_RE.search(q))
        has_policy = bool(_POLICY_RE.search(q))
        has_vocab = bool(_VOCAB_RE.search(q))
        distinct_types = sum([has_adr, has_pcp, has_dar, has_policy, has_vocab])

        if distinct_types >= 2 or entity_scope in (EntityScope.MULTI, EntityScope.DAR_ALL):
            return IntentDecision(
                intent=Intent.COMPARE_CONCEPTS,
                entity_scope=entity_scope,
                output_shape=OutputShape.EXPLANATION,
                confidence=0.88,
                reasoning="Conceptual comparison between entity types",
            )
        # Compare with single entity — still conceptual
        if _DEFINITIONAL_RE.search(question):
            return IntentDecision(
                intent=Intent.COMPARE_CONCEPTS,
                entity_scope=entity_scope,
                output_shape=OutputShape.EXPLANATION,
                confidence=0.80,
                reasoning="Comparative/definitional question",
            )

    # ---- DEFINITIONAL ("What is a DAR?") ----
    if _DEFINITIONAL_RE.search(question):
        return IntentDecision(
            intent=Intent.COMPARE_CONCEPTS,  # definitions are a form of concept explanation
            entity_scope=entity_scope,
            output_shape=OutputShape.SHORT_ANSWER,
            confidence=0.88,
            reasoning="Definitional question about document type",
        )

    # ---- COUNT ("How many ADRs?") ----
    if _COUNT_RE.search(question):
        return IntentDecision(
            intent=Intent.COUNT,
            entity_scope=entity_scope,
            output_shape=OutputShape.SHORT_ANSWER,
            confidence=0.90,
            reasoning="Count/total query",
        )

    # ---- LIST ("List all ADRs", "Show me principles") ----
    if _LIST_VERBS_RE.search(question):
        return IntentDecision(
            intent=Intent.LIST,
            entity_scope=entity_scope,
            output_shape=OutputShape.LIST,
            confidence=0.85 if entity_scope != EntityScope.UNKNOWN else 0.50,
            reasoning="List intent with verb trigger",
        )

    # ---- SEMANTIC ANSWER (default for domain queries) ----
    # Check for any ESA cues to decide if this is an in-scope semantic question
    has_esa_cues = bool(
        _ADR_RE.search(q_lower)
        or _PCP_RE.search(q_lower)
        or _DAR_RE.search(q_lower)
        or _POLICY_RE.search(q_lower)
        or _VOCAB_RE.search(q_lower)
        or re.search(
            r"\b(?:esa|alliander|energy|architecture|governance|"
            r"consistency|idempoten|interoperab|security|tls|oauth|"
            r"data\s+(?:quality|reliability|access|integration)|"
            r"message\s+exchange|distributed\s+system|capability)\b",
            q_lower,
        )
    )

    if has_esa_cues:
        return IntentDecision(
            intent=Intent.SEMANTIC_ANSWER,
            entity_scope=entity_scope,
            output_shape=OutputShape.EXPLANATION,
            confidence=0.65,
            reasoning="ESA-related semantic question (no specific intent pattern)",
        )

    # ---- UNKNOWN (no ESA cues, no clear intent) ----
    return IntentDecision(
        intent=Intent.UNKNOWN,
        entity_scope=EntityScope.UNKNOWN,
        output_shape=OutputShape.CLARIFICATION,
        confidence=0.20,
        reasoning="No ESA cues or intent patterns detected",
        clarification_options=[
            "Search the ESA knowledge base",
            "List documents (ADRs, principles, policies)",
            "Ask about AInstein's capabilities",
        ],
    )


# =============================================================================
# LLM-Based Classifier (preferred in non-enterprise mode)
# =============================================================================

_LLM_CLASSIFY_PROMPT = """\
You are an intent classifier for an Energy System Architecture (ESA) knowledge base assistant called AInstein at Alliander.

The knowledge base contains: Architecture Decision Records (ADRs), Principles (PCPs), Decision Approval Records (DARs), Policy documents, and IEC/CIM vocabulary terms covering energy systems, ArchiMate, CIM standards, and related technical domains.

Given a user question, classify it into exactly ONE of these intents:
- lookup_doc: user wants details about a specific document by ID (e.g. "Tell me about ADR.0025", "What does ADR.0028 decide?", "What is the status of ADR.0027?")
- lookup_approval: user wants approval/approver info (e.g. "Who approved ADR.0025?", "Who approved PCP.0020?", "What are the approvers?")
- list: user wants to see a list/catalog of documents (e.g. "List all ADRs", "What principles exist?", "What are all the data governance principles?")
- compare_counts: user wants a numeric comparison between document types
- compare_concepts: user wants to understand differences between concepts/document types
- semantic_answer: user wants a substantive answer from the knowledge base. This includes ANY question about energy terms, architecture, governance, standards, CIM, IEC, ArchiMate, data quality, security, policies, or capabilities — even if the question doesn't explicitly mention "ADR" or "PCP". Examples: "What is a Business Actor in ArchiMate?", "What does eventual consistency by design mean?", "How should message exchange be handled?", "What capability document addresses data integration?", "What is defined in IEC 61970?"
- count: user wants to know how many documents exist
- meta: user is asking about AInstein/the assistant itself, its architecture, pipeline, skills, or capabilities — NOT about the ESA knowledge base content. Examples: "Explain your own architecture", "Which skills did you use?", "How do you work?", "Who are you?"
- unknown: genuinely unrelated to ESA or the assistant (e.g. "What's the weather?")

IMPORTANT: Default to "semantic_answer" with confidence >= 0.7 for any question that could plausibly be answered from an energy/architecture knowledge base. Only use "unknown" for questions clearly outside this domain.

Also classify the entity scope (which collection):
- adr: about Architecture Decision Records
- pcp: about Principles
- dar_adr, dar_pcp, dar_all: about Decision Approval Records
- policy: about policy/governance documents
- vocab: about vocabulary, terminology, definitions, CIM, IEC standards, ArchiMate
- multi: crosses multiple collections
- unknown: not determinable

And the output shape:
- short_answer, list, table, explanation, clarification

Respond with ONLY valid JSON (no markdown):
{
  "intent": "...",
  "entity_scope": "...",
  "output_shape": "...",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}

User question: """


async def llm_classify(question: str) -> IntentDecision:
    """LLM-based intent classification.

    Falls back to heuristic_classify on LLM failure.
    """
    from .config import settings

    prompt = _LLM_CLASSIFY_PROMPT + question

    try:
        if settings.llm_provider == "ollama":
            result = await _classify_with_ollama(prompt)
        else:
            result = await _classify_with_openai(prompt)

        if result:
            return result
    except Exception as e:
        logger.warning(f"LLM intent classification failed: {e}, falling back to heuristic")

    return heuristic_classify(question)


async def _classify_with_ollama(prompt: str) -> Optional[IntentDecision]:
    """Classify intent using Ollama."""
    import httpx
    from .config import settings

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 200},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("response", "").strip()
        return _parse_llm_response(raw)


async def _classify_with_openai(prompt: str) -> Optional[IntentDecision]:
    """Classify intent using OpenAI."""
    import openai
    from .config import settings

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0,
    )
    raw = resp.choices[0].message.content.strip()
    return _parse_llm_response(raw)


def _parse_llm_response(raw: str) -> Optional[IntentDecision]:
    """Parse LLM JSON response into IntentDecision."""
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"LLM intent response not valid JSON: {raw[:200]}")
        return None

    try:
        return IntentDecision(
            intent=Intent(data.get("intent", "unknown")),
            entity_scope=EntityScope(data.get("entity_scope", "unknown")),
            output_shape=OutputShape(data.get("output_shape", "explanation")),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=data.get("reasoning", ""),
        )
    except (ValueError, KeyError) as e:
        logger.warning(f"LLM intent response has invalid enum values: {e}")
        return None


# =============================================================================
# Public API — unified entry point
# =============================================================================

async def classify_intent(question: str, mode: str = "heuristic") -> IntentDecision:
    """Classify user intent.

    Args:
        question: The user's question
        mode: "heuristic" (fast, default) or "llm" (uses configured LLM)

    Returns:
        IntentDecision with stable schema
    """
    # Hybrid approach: for high-confidence structural intents (META, LOOKUP_DOC,
    # LOOKUP_APPROVAL), the heuristic is more reliable than the LLM because these
    # are pattern-based. Run heuristic first as a guardrail.
    _HEURISTIC_OVERRIDE_INTENTS = {
        Intent.META, Intent.LOOKUP_DOC, Intent.LOOKUP_APPROVAL,
    }
    _HEURISTIC_OVERRIDE_THRESHOLD = 0.85

    heuristic_decision = heuristic_classify(question)

    if mode == "llm":
        # If heuristic gives high confidence for structural intents, trust it
        if (heuristic_decision.intent in _HEURISTIC_OVERRIDE_INTENTS
                and heuristic_decision.confidence >= _HEURISTIC_OVERRIDE_THRESHOLD):
            logger.info(
                f"Heuristic override: {heuristic_decision.intent.value} "
                f"(confidence={heuristic_decision.confidence:.2f}), skipping LLM"
            )
            decision = heuristic_decision
        else:
            llm_decision = await llm_classify(question)
            # If LLM returns low confidence but heuristic has a real answer, prefer heuristic
            if (llm_decision.confidence < DEFAULT_CONFIDENCE_THRESHOLD
                    and heuristic_decision.intent != Intent.UNKNOWN
                    and heuristic_decision.confidence >= DEFAULT_CONFIDENCE_THRESHOLD):
                logger.info(
                    f"LLM low-confidence fallback to heuristic: "
                    f"LLM={llm_decision.intent.value}({llm_decision.confidence:.2f}) → "
                    f"heuristic={heuristic_decision.intent.value}({heuristic_decision.confidence:.2f})"
                )
                decision = heuristic_decision
            else:
                decision = llm_decision
    else:
        decision = heuristic_decision

    logger.info(
        f"Intent classified: intent={decision.intent.value}, "
        f"scope={decision.entity_scope.value}, "
        f"confidence={decision.confidence:.2f}, "
        f"reasoning={decision.reasoning}"
    )
    return decision


def needs_clarification(decision: IntentDecision, threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> bool:
    """Check if we should ask a clarifying question instead of routing."""
    return decision.confidence < threshold or decision.intent == Intent.UNKNOWN


_CLARIFICATION_PROMPT = """\
You are AInstein, the Energy System Architecture (ESA) assistant at Alliander.

The user asked a question, but you're not confident what they want. Generate a short,
contextual clarifying question (2-4 sentences max) that:
1. Acknowledges what the user said
2. Offers 2-3 specific options relevant to their wording
3. Uses markdown bullet points for options

The knowledge base contains: ADRs (Architecture Decision Records), Principles (PCPs),
DARs (Decision Approval Records), Policies, and IEC/CIM vocabulary terms.

Classification context:
- Best-guess intent: {intent}
- Detected scope: {entity_scope}
- Confidence: {confidence:.0%}
- Reasoning: {reasoning}
- Detected entities: {entities}

User question: {question}

Write ONLY the clarifying response (no JSON, no preamble):"""


async def build_clarification_response(
    decision: IntentDecision,
    question: str = "",
) -> str:
    """Generate a contextual clarifying question via the LLM.

    Falls back to a static menu if the LLM call fails.
    """
    from .config import settings

    prompt = _CLARIFICATION_PROMPT.format(
        intent=decision.intent.value,
        entity_scope=decision.entity_scope.value,
        confidence=decision.confidence,
        reasoning=decision.reasoning,
        entities=", ".join(decision.detected_entities) if decision.detected_entities else "none",
        question=question,
    )

    try:
        if settings.llm_provider == "ollama":
            response = await _generate_clarification_ollama(prompt)
        else:
            response = await _generate_clarification_openai(prompt)

        if response and len(response.strip()) > 20:
            return response.strip()
    except Exception as e:
        logger.warning(f"LLM clarification generation failed: {e}, using fallback")

    return _build_fallback_clarification(decision)


async def _generate_clarification_ollama(prompt: str) -> Optional[str]:
    """Generate clarification using Ollama."""
    import httpx
    from .config import settings

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 200},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "").strip()


async def _generate_clarification_openai(prompt: str) -> Optional[str]:
    """Generate clarification using OpenAI."""
    import openai
    from .config import settings

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def _build_fallback_clarification(decision: IntentDecision) -> str:
    """Static fallback when LLM is unavailable."""
    if decision.clarification_options:
        options = "\n".join(f"- {opt}" for opt in decision.clarification_options)
        return (
            "I'm not sure what you're looking for. Could you clarify?\n\n"
            f"{options}\n\n"
            "Please rephrase your question or pick one of the options above."
        )

    return (
        "I want to make sure I give you the right answer. "
        "Are you looking for:\n\n"
        "- A **list** of documents?\n"
        "- A **definition** or **comparison** of concepts?\n"
        "- **Details** about a specific document?\n"
        "- A **count** of documents?\n\n"
        "Please let me know which you'd prefer."
    )


# =============================================================================
# Compare Intent Handlers
# =============================================================================

# Canonical doc-type descriptions for compare_concepts
_DOC_TYPE_DESCRIPTIONS = {
    "adr": (
        "**ADR (Architecture Decision Record)** — A record of a significant "
        "architectural decision, including the context, the decision itself, "
        "its rationale, and its consequences. ADRs capture *what was decided and why*."
    ),
    "pcp": (
        "**PCP (Principle)** — A guiding rule or constraint that shapes how "
        "the architecture is designed and governed. Principles define *how things "
        "should be done* and provide guardrails for decision-making."
    ),
    "dar": (
        "**DAR (Decision Approval Record)** — An administrative record that "
        "tracks who approved an ADR or PCP, when, and under what conditions. "
        "DARs contain DACI governance information (Driver, Approver, Contributor, Informed)."
    ),
    "policy": (
        "**Policy** — A formal governance document covering data quality, "
        "privacy, security, or compliance requirements. Policies set mandatory "
        "rules that ADRs and Principles must respect."
    ),
    "vocab": (
        "**Vocabulary Concept** — A term from the IEC/CIM/SKOS ontologies "
        "used in the energy sector (e.g., PowerTransformer, ACLineSegment). "
        "These provide the shared language for ESA documentation."
    ),
}


def handle_compare_concepts(question: str) -> str:
    """Handle compare_concepts intent with deterministic definitions.

    Returns a structured explanation comparing the mentioned entity types.
    Does NOT call list_all_adrs or any list tool.
    """
    q_lower = question.lower()

    # Detect which entity types are mentioned
    mentioned = []
    if re.search(r"\badrs?\b", q_lower):
        mentioned.append("adr")
    if re.search(r"\b(?:pcps?|principles?)\b", q_lower):
        mentioned.append("pcp")
    if re.search(r"\bdars?\b|decision\s+approval", q_lower):
        mentioned.append("dar")
    if re.search(r"\bpolic(?:y|ies)\b", q_lower):
        mentioned.append("policy")
    if re.search(r"\bvocab|concept|term\b", q_lower):
        mentioned.append("vocab")

    # If only one or none mentioned, provide the most relevant comparison
    if len(mentioned) < 2:
        if "dar" in mentioned:
            mentioned = ["adr", "dar"]
        elif "adr" in mentioned:
            mentioned = ["adr", "pcp"]
        elif "pcp" in mentioned:
            mentioned = ["adr", "pcp"]
        else:
            mentioned = ["adr", "pcp", "dar"]

    # Build response
    parts = []
    for key in mentioned:
        desc = _DOC_TYPE_DESCRIPTIONS.get(key, "")
        if desc:
            parts.append(desc)

    if len(parts) >= 2:
        header = "Here are the key differences:\n\n"
        body = "\n\n".join(parts)
        summary = (
            "\n\n**In short:** ADRs record *decisions*, Principles define *guiding rules*, "
            "and DARs track *approvals*. They serve complementary roles in ESA governance."
        )
        return header + body + summary

    return "\n\n".join(parts) if parts else "I don't have a comparison for the requested types."


async def handle_compare_counts(
    question: str,
    tool_registry: dict,
) -> str:
    """Handle compare_counts intent with actual numeric data.

    Computes counts from the knowledge base and returns a numeric
    comparison — NOT a list dump.
    """
    count_tool = tool_registry.get("count_documents")
    if not count_tool:
        return "Count information is not available at this time."

    # Get all counts
    all_counts = await count_tool("all")
    if not isinstance(all_counts, dict) or "error" in all_counts:
        return "I couldn't retrieve the document counts. Please try again."

    # Build comparison response
    lines = ["Here are the document counts:\n"]
    for doc_type, count in sorted(all_counts.items()):
        lines.append(f"- **{doc_type}**: {count}")

    # Add specific comparison if the question targets two types
    q_lower = question.lower()
    if "adr" in q_lower and "pcp" in q_lower:
        adr_count = all_counts.get("ADRs", all_counts.get("adr", 0))
        pcp_count = all_counts.get("Principles", all_counts.get("principle", 0))
        diff = abs(adr_count - pcp_count)
        if adr_count > pcp_count:
            lines.append(f"\nADRs outnumber Principles by {diff}.")
        elif pcp_count > adr_count:
            lines.append(f"\nPrinciples outnumber ADRs by {diff}.")
        else:
            lines.append("\nADRs and Principles have equal counts.")

    if "dar" in q_lower:
        # DAR-specific comparison
        dar_adr = all_counts.get("ADR DARs", all_counts.get("dar_adr", 0))
        dar_pcp = all_counts.get("PCP DARs", all_counts.get("dar_pcp", 0))
        if dar_adr or dar_pcp:
            diff = abs(dar_adr - dar_pcp)
            if dar_adr > dar_pcp:
                lines.append(f"\nADR DARs ({dar_adr}) outnumber PCP DARs ({dar_pcp}) by {diff}.")
            elif dar_pcp > dar_adr:
                lines.append(f"\nPCP DARs ({dar_pcp}) outnumber ADR DARs ({dar_adr}) by {diff}.")
            else:
                lines.append(f"\nADR DARs ({dar_adr}) and PCP DARs ({dar_pcp}) have equal counts.")

    return "\n".join(lines)
