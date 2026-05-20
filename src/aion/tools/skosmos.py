"""SKOSMOS vocabulary tool wrappers.

Calls the SKOSMOS REST API for structured vocabulary lookups.
Fixes critical quality issues in vocabulary queries (wrong results,
duplicates, incoherent comparisons) by using SKOSMOS's exact label
matching instead of Weaviate's approximate vector similarity.
"""

import logging

import requests

from aion.config import settings

logger = logging.getLogger(__name__)



def _base_url() -> str:
    """SKOSMOS REST API base URL from config."""
    return f"{settings.skosmos_url}/rest/v1"


# ---------------------------------------------------------------------------
# JSON-LD helpers
# ---------------------------------------------------------------------------

def _extract_label(val, lang="en") -> str:
    """Extract string from JSON-LD label, preferring the requested language."""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("value", val.get("@value", str(val)))
    if isinstance(val, list) and val:
        for item in val:
            if isinstance(item, dict) and item.get("lang", item.get("@language")) == lang:
                return item.get("value", item.get("@value", ""))
        return _extract_label(val[0], lang)
    return ""


def _extract_labels(val, lang="en") -> list[str]:
    """Extract list of strings from JSON-LD labels, preferring the requested language."""
    if isinstance(val, str):
        return [val]
    if isinstance(val, dict):
        return [_extract_label(val, lang)]
    if isinstance(val, list):
        tagged = [v for v in val if isinstance(v, dict) and v.get("lang", v.get("@language")) == lang]
        if tagged:
            return [_extract_label(v, lang) for v in tagged]
        return [_extract_label(v, lang) for v in val]
    return []


def _extract_links(val, lang="en") -> list[dict]:
    """Extract list of {uri, label} from JSON-LD broader/narrower/related."""
    if not val:
        return []
    if isinstance(val, dict):
        val = [val]
    links = []
    for item in val:
        if isinstance(item, str):
            links.append({"uri": item, "label": ""})
        elif isinstance(item, dict):
            links.append({
                "uri": item.get("uri", item.get("@id", "")),
                "label": _extract_label(item.get("prefLabel", item.get("label", "")), lang),
            })
    return links


# ---------------------------------------------------------------------------
# Tool 1: skosmos_search
# ---------------------------------------------------------------------------

def skosmos_search(
    query: str,
    lang: str = "en",
    vocab: str | None = None,
    max_results: int = 10,
) -> dict:
    """Search SKOSMOS for concepts matching a query string.

    Uses exact and pattern-based label matching with unique=true to
    prevent duplicate results.

    Returns:
        dict with "results" (list of concept dicts) and "total_results" (int).
    """
    try:
        # Guard against LLM passing string "None" instead of omitting the param
        if vocab and str(vocab).strip().lower() != "none":
            url = f"{_base_url()}/{vocab}/search"
        else:
            url = f"{_base_url()}/search"

        params = {
            "query": f"*{query}*",
            "lang": lang,
            "maxhits": max_results,
            "unique": "true",
            "fields": "broader related",
        }

        resp = requests.get(url, params=params, timeout=settings.timeout_skosmos)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "uri": item.get("uri", ""),
                "prefLabel": item.get("prefLabel", ""),
                "altLabel": item.get("altLabel", ""),
                "vocab": item.get("vocab", ""),
                "definition": item.get("skos:definition", ""),
                "broader": item.get("broader", []),
                "related": item.get("related", []),
            })

        return {"results": results, "total_results": len(results)}

    except requests.ConnectionError:
        return {
            "results": [], "total_results": 0,
            "error": f"SKOSMOS service unavailable at {settings.skosmos_url}",
        }
    except requests.RequestException as e:
        return {
            "results": [], "total_results": 0,
            "error": f"SKOSMOS search failed: {e}",
        }


# ---------------------------------------------------------------------------
# Tool 2: skosmos_concept_details
# ---------------------------------------------------------------------------

def skosmos_concept_details(
    uri: str,
    vocab: str,
    lang: str = "en",
) -> dict:
    """Get full details for a specific SKOS concept by URI.

    Fetches and flattens JSON-LD response into a simple dict with
    prefLabel, definition, broader/narrower/related links, etc.
    """
    try:
        if not vocab:
            return {"error": "vocab parameter is required — use the 'vocab' field from skosmos_search results"}
        url = f"{_base_url()}/{vocab}/data"
        params = {"uri": uri, "format": "application/json"}

        resp = requests.get(url, params=params, timeout=settings.timeout_skosmos)
        resp.raise_for_status()
        data = resp.json()

        # Flatten JSON-LD: find the concept node in the graph
        graph = data.get("graph", [data])
        concept = None
        for node in (graph if isinstance(graph, list) else [graph]):
            if node.get("uri", node.get("@id", "")) == uri:
                concept = node
                break

        if not concept:
            return {"error": f"Concept {uri} not found in response"}

        return {
            "uri": uri,
            "prefLabel": _extract_label(concept.get("prefLabel", ""), lang),
            "altLabels": _extract_labels(concept.get("altLabel", []), lang),
            "definition": _extract_label(concept.get("skos:definition", ""), lang),
            "broader": _extract_links(concept.get("broader", []), lang),
            "narrower": _extract_links(concept.get("narrower", []), lang),
            "related": _extract_links(concept.get("related", []), lang),
            "scopeNote": _extract_label(concept.get("scopeNote", ""), lang),
            "notation": concept.get("notation", ""),
        }

    except requests.ConnectionError:
        return {"error": f"SKOSMOS service unavailable at {settings.skosmos_url}"}
    except requests.RequestException as e:
        return {"error": f"SKOSMOS concept fetch failed: {e}"}


# ---------------------------------------------------------------------------
# Tool 3: skosmos_define (ISS-001 — composed search + concept_details)
# ---------------------------------------------------------------------------

def skosmos_define(
    term: str,
    lang: str = "en",
    vocab: str | None = None,
    max_results: int = 5,
) -> dict:
    """Atomic search + definition lookup for the single-hit case (ISS-001).

    Composes ``skosmos_search`` + ``skosmos_concept_details`` for definition
    queries ("what is X?", "define X"). Pre-1a.7 the vocabulary agent had
    to chain those two manually — and the disambiguation gate on the
    ``skosmos_concept_details`` agent-tool wrapper (at
    ``vocabulary_agent.py:~140``) blocks drill-down whenever search hits
    span multiple vocabularies, forcing the LLM into a re-search spiral
    (the ISS-001 thrash). This composed pure helper resolves the
    single-vocab case in one call without going through that wrapper,
    so the gate doesn't fire when the model wouldn't have needed it.

    Returns:
        Single-vocab (one result, OR all results from the same vocabulary):
            {"definition": str, "vocabulary": str, "uri": str,
             "prefLabel": str, "hit_count": int}
        Multi-vocab (search hits span vocabularies — present options to user):
            {"disambiguation": [hits...], "vocabularies": [str...]}
        No matches:
            {"error": "no matches", "term": term}

    Pure function: no ctx, no cache, no event emission. The agent-tool
    wrapper in ``vocabulary_agent.py`` handles those concerns. See
    that wrapper for the two-layer pattern.
    """
    search = skosmos_search(query=term, lang=lang, vocab=vocab, max_results=max_results)
    if "error" in search:
        return {"error": search["error"], "term": term}

    hits = search.get("results", [])
    if not hits:
        return {"error": "no matches", "term": term}

    vocabularies = {h.get("vocab") for h in hits if h.get("vocab")}
    if len(hits) == 1 or len(vocabularies) == 1:
        # Single-vocab path: take the top hit, fetch its concept_details
        # directly. This bypasses the vocabulary_agent wrapper's
        # disambiguation gate — which is correct here because there's
        # nothing ambiguous to disambiguate.
        top = hits[0]
        details = skosmos_concept_details(
            uri=top["uri"], vocab=top["vocab"], lang=lang,
        )
        if "error" in details:
            return {"error": details["error"], "term": term}
        return {
            "definition": details.get("definition", ""),
            "vocabulary": top["vocab"],
            "uri": top["uri"],
            "prefLabel": details.get("prefLabel", top.get("prefLabel", "")),
            "hit_count": len(hits),
        }

    # Multi-vocab: return the disambiguation list so the LLM can
    # present options to the user (existing disambiguation flow in
    # vocabulary_agent applies).
    return {
        "disambiguation": hits,
        "vocabularies": sorted(vocabularies),
    }


# ---------------------------------------------------------------------------
# Tool 4: skosmos_list_vocabularies
# ---------------------------------------------------------------------------

def skosmos_list_vocabularies(lang: str = "en") -> dict:
    """List all vocabularies available in SKOSMOS.

    Returns vocabulary IDs, titles, descriptions, and concept counts.
    """
    try:
        url = f"{_base_url()}/vocabularies"
        params = {"lang": lang}

        resp = requests.get(url, params=params, timeout=settings.timeout_skosmos)
        resp.raise_for_status()
        data = resp.json()

        vocabularies = []
        for item in data.get("vocabularies", []):
            vocabularies.append({
                "id": item.get("id", ""),
                "title": _extract_label(item.get("title", "")),
                "description": _extract_label(item.get("description", "")),
                "concept_count": item.get("conceptCount", 0),
                "languages": item.get("languages", []),
            })

        return {"vocabularies": vocabularies}

    except requests.ConnectionError:
        return {
            "vocabularies": [],
            "error": f"SKOSMOS service unavailable at {settings.skosmos_url}",
        }
    except requests.RequestException as e:
        return {"vocabularies": [], "error": f"SKOSMOS vocabulary list failed: {e}"}
