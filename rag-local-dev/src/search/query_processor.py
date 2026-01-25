"""
Query preprocessing: normalization, language detection, type classification.
"""

import re
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


def load_semantic_trigger_terms(config: dict) -> List[str]:
    """
    Load all semantic trigger terms from config.
    These are domain-specific terms that should use semantic search,
    not terminology lookup.
    """
    terms = []
    semantic_config = config.get("query", {}).get("semantic_trigger_terms", {})

    for category, term_list in semantic_config.items():
        if isinstance(term_list, list):
            terms.extend([t.lower() for t in term_list])

    return terms


def detect_query_language(query: str) -> str:
    """
    Detect query language, return 'en', 'nl', or 'both' if uncertain.

    Uses langdetect library with fallback to 'both' on errors.
    """
    try:
        from langdetect import detect

        lang = detect(query)
        if lang == "nl":
            return "nl"
        elif lang in ["en", "de"]:  # German sometimes detected for technical English
            return "en"
        else:
            return "both"
    except Exception as e:
        logger.debug(f"Language detection failed: {e}")
        return "both"


def detect_query_type(query: str, semantic_trigger_terms: List[str]) -> str:
    """
    Classify query type for routing and alpha selection.

    Args:
        query: The search query
        semantic_trigger_terms: List of terms that should trigger semantic search

    Returns:
        Query type: 'exact_match', 'semantic', 'terminology', or 'mixed'
    """
    query_lower = query.lower()

    # Exact ID patterns (ADR-001, PRINCIPLE-012, IEC-61968, GOV-PRINCIPLE-0001)
    id_patterns = [
        r"^(ADR|PRINCIPLE|GOV-PRINCIPLE)-?\d+",
        r"^IEC[-\s]?\d+",
        r"^NEN[-\s]?\d+",
    ]
    for pattern in id_patterns:
        if re.match(pattern, query, re.IGNORECASE):
            return "exact_match"

    # Domain-specific terms need semantic search (ArchiMate, energy/grid terms)
    for term in semantic_trigger_terms:
        if term in query_lower:
            return "semantic"

    # Short queries (1-2 words) without question words -> terminology lookup
    words = query.split()
    question_words_en = ["what", "how", "why", "which", "explain", "describe", "when", "where"]
    question_words_nl = ["wat", "hoe", "waarom", "welke", "wanneer", "waar"]
    question_words = question_words_en + question_words_nl

    if len(words) <= 2 and not any(q in query_lower for q in question_words):
        return "terminology"

    # Question words indicate semantic search
    if any(q in query_lower for q in question_words):
        return "semantic"

    return "mixed"


def expand_abbreviations(text: str, abbreviations: Dict[str, str]) -> str:
    """
    Expand known abbreviations for better embedding.

    Example: "DSO" -> "DSO (Distribution System Operator)"
    """
    for abbr, expansion in abbreviations.items():
        pattern = r"\b" + re.escape(abbr) + r"\b"
        text = re.sub(pattern, f"{abbr} ({expansion})", text, flags=re.IGNORECASE, count=1)
    return text


def preprocess_query(query: str, config: dict) -> dict:
    """
    Full query preprocessing pipeline.

    Returns dict with:
        - original: Original query
        - cleaned: Whitespace-normalized query
        - expanded: Query with abbreviations expanded
        - language: Detected language ('en', 'nl', 'both')
        - query_type: Classification ('semantic', 'exact_match', 'terminology', 'mixed')
        - alpha: Recommended alpha value for hybrid search
    """
    # Basic normalization
    cleaned = re.sub(r"\s+", " ", query.strip())

    # Language detection
    language = detect_query_language(cleaned)

    # Load semantic trigger terms from config
    semantic_terms = load_semantic_trigger_terms(config)

    # Query type classification
    query_type = detect_query_type(cleaned, semantic_terms)

    # Abbreviation expansion
    abbreviations = config.get("query", {}).get("abbreviations", {})
    if config.get("query", {}).get("expand_abbreviations", True) and abbreviations:
        expanded = expand_abbreviations(cleaned, abbreviations)
    else:
        expanded = cleaned

    # Select alpha based on query type
    alpha_presets = config.get("search", {}).get("alpha_presets", {})
    default_alpha = config.get("search", {}).get("default_alpha", 0.7)
    alpha = alpha_presets.get(query_type, default_alpha)

    return {
        "original": query,
        "cleaned": cleaned,
        "expanded": expanded,
        "language": language,
        "query_type": query_type,
        "alpha": alpha,
    }
