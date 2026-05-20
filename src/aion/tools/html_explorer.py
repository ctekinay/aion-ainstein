"""Generate interactive HTML architecture explorer from repo-analysis YAML.

Deterministic Python templating — no LLM call. Parses the architecture_notes
YAML, classifies components into tiers, and injects the data into a self-contained
HTML template with inline CSS and JS.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).parent / "explorer_template.html"

# Infrastructure keywords — matched as substrings against component name and path.
_INFRA_KEYWORDS = frozenset({
    "weaviate", "postgres", "redis", "kafka", "elasticsearch",
    "rabbitmq", "nginx", "minio",
})


def _strip_namespace(identifier: str) -> str:
    """Strip namespace prefix (e.g. 'mod:aion' → 'aion')."""
    if ":" in identifier:
        return identifier.split(":", 1)[1]
    return identifier


def _classify_tier(component: dict) -> str:
    """Classify a component into a tier using SKILL.md heuristics (priority order).

    1. Infrastructure — docker-compose source, infrastructure type, or infra keyword
    2. Agents — name/path contains 'agent'
    3. Data pipeline — name/path contains ingest/chunk/load/etl/pipeline/parse
    4. Support — name/path contains diagnostic/eval/test/mcp/monitor/metric
    5. Core services — everything else
    """
    name = (component.get("name") or "").lower()
    path = (component.get("path") or "").lower()
    source = (component.get("source") or "").lower()
    ctype = (component.get("type") or "").lower()

    # 1. Infrastructure (highest priority)
    if ("docker-compose" in source
            or ctype == "infrastructure"
            or any(kw in name for kw in _INFRA_KEYWORDS)
            or any(kw in path for kw in _INFRA_KEYWORDS)):
        return "infra"

    # 2. Agents
    if "agent" in name or "agent" in path:
        return "agent"

    # 3. Data pipeline
    if any(k in name or k in path
           for k in ("ingest", "chunk", "load", "etl", "pipeline", "parse")):
        return "data"

    # 4. Support
    if any(k in name or k in path
           for k in ("diagnostic", "eval", "test", "mcp", "monitor", "metric")):
        return "support"

    # 5. Default
    return "core"


def generate_explorer_html(yaml_content: str) -> str | None:
    """Generate a self-contained HTML architecture explorer from YAML.

    Args:
        yaml_content: Raw architecture_notes YAML string.

    Returns:
        Complete HTML string, or None on parse failure.
    """
    try:
        data = yaml.safe_load(yaml_content)
    except Exception:
        logger.warning("[html_explorer] Failed to parse YAML input")
        return None

    if not isinstance(data, dict):
        logger.warning("[html_explorer] YAML root is not a dict")
        return None

    components = data.get("components") or []
    edges = data.get("edges") or []
    meta = data.get("meta") or {}
    summary = data.get("summary") or {}
    deployment = data.get("deployment") or {}

    repo_name = meta.get("repo_name") or summary.get("repo_name") or "architecture"

    # Normalize component names — strip namespace prefixes
    for comp in components:
        if "name" not in comp and "id" in comp:
            comp["name"] = _strip_namespace(comp["id"])
        elif "name" in comp:
            comp["name"] = _strip_namespace(comp["name"])

    # Normalize edge endpoints
    for edge in edges:
        if "from" in edge:
            edge["from"] = _strip_namespace(edge["from"])
        if "to" in edge:
            edge["to"] = _strip_namespace(edge["to"])

    # Classify components into tiers
    tier_buckets: dict[str, list[str]] = {
        "infra": [],
        "agent": [],
        "data": [],
        "support": [],
        "core": [],
    }
    for comp in components:
        tier = _classify_tier(comp)
        name = comp.get("name", "")
        if name:
            tier_buckets[tier].append(name)

    # Build TIERS array — only include tiers that have components
    tier_defs = [
        ("Infrastructure", "infra"),
        ("Agents", "agent"),
        ("Core services", "core"),
        ("Data pipeline", "data"),
        ("Support", "support"),
    ]
    tiers = []
    for label, color in tier_defs:
        ids = tier_buckets.get(color, [])
        if ids:
            tiers.append({"label": label, "ids": ids, "color": color})

    # Build DATA object
    explorer_data = {
        "meta": meta,
        "summary": summary,
        "components": components,
        "edges": edges,
        "deployment": deployment,
    }

    # Read template and inject data
    try:
        template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error("[html_explorer] Template file not found: %s", _TEMPLATE_PATH)
        return None

    html = (template
            .replace("{DATA_JSON}", json.dumps(explorer_data, indent=2, default=str))
            .replace("{TIERS_JSON}", json.dumps(tiers, indent=2))
            .replace("{REPO_NAME}", repo_name))

    return html
