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
# Tool 3: skosmos_list_vocabularies
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
