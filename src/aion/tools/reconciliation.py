"""DCT metadata reconciliation for generated ArchiMate models.

Builds source metadata from Weaviate KB objects and enriches
ArchiMate YAML elements with Dublin Core (dct:*) properties.
Extracted from GenerationPipeline for reuse across pipelines.
"""

import logging
import re

logger = logging.getLogger(__name__)


# -- Document type aliases for source_ref normalization --
# Maps LLM-variant prefixes to canonical form.
# Extensible: add new doc types here (e.g., "POLICY": "POL").
DOC_TYPE_ALIASES: dict[str, str] = {
    "PCP": "PCP",
    "PRINCIPLE": "PCP",
    "ADR": "ADR",
}

# ArchiMate type → document prefix for type-gated fallback.
# Only these element types can have source_ref inferred from name.
SOURCE_DOC_TYPES: dict[str, str] = {
    "Principle": "PCP",
    "ArchitecturalDecision": "ADR",
}


def normalize_ref(raw: str) -> str | None:
    """Normalize source_ref variants to canonical form (PCP.10, ADR.29).

    Handles: "PCP.10", "PCP 10", "PCP-10", "PCP10", "Principle 10",
    "ADR.29", "ADR 29". Bare numbers ("0010") are ambiguous — skipped.
    """
    s = raw.strip().upper()
    for alias, canonical in DOC_TYPE_ALIASES.items():
        m = re.match(rf"{alias}[.\s-]*(\d+)", s)
        if m:
            return f"{canonical}.{int(m.group(1))}"
    return None


def build_source_metadata(sources: list[dict]) -> dict[str, dict]:
    """Build doc_ref -> metadata lookup from fetched sources.

    Keys are canonical doc refs (e.g. "PCP.10", "ADR.29").
    Values carry all available dct-relevant fields. Designed for
    extensibility: add fields here without changing enrich_yaml_with_dct().
    """
    meta: dict[str, dict] = {}
    for src in sources:
        pn = src.get("principle_number", "")
        an = src.get("adr_number", "")
        kb_uuid = src.get("kb_uuid", "")
        dct_id = src.get("dct_identifier", "")
        title = src.get("title", "")
        owner = src.get("owner_display", "")
        if not kb_uuid and not dct_id:
            continue
        if pn and an:
            logger.warning(
                "Source has both principle_number=%s and adr_number=%s "
                "(kb_uuid=%s) — using principle_number. "
                "Investigate KB data quality.",
                pn, an, kb_uuid,
            )
        ref = None
        if pn:
            ref = f"PCP.{int(pn)}"
        elif an:
            ref = f"ADR.{int(an)}"
        if ref:
            # Prefer frontmatter UUID (canonical) over Weaviate chunk UUID (random)
            if dct_id:
                resolved_uuid = dct_id if dct_id.startswith("urn:uuid:") else f"urn:uuid:{dct_id}"
            elif kb_uuid:
                resolved_uuid = f"urn:uuid:{kb_uuid}"
            else:
                resolved_uuid = ""

            entry: dict[str, str] = {
                "resolved_identifier": resolved_uuid,
                "title": title,
                "_raw_dct_identifier": dct_id,  # for UUID integrity check
            }
            if owner:
                entry["creator"] = owner
            issued = src.get("dct_issued", "")
            if issued:
                entry["issued"] = issued
            entry["language"] = "en"
            meta[ref] = entry
    return meta


def enrich_yaml_with_dct(yaml_text: str, source_metadata: dict) -> str:
    """Enrich YAML elements with dct properties, strip source_ref.

    For elements with source_ref matching a source_metadata key,
    adds dct:identifier, dct:title, and dct:creator (if available).
    Falls back to inferring source_ref from element name — only for
    elements whose type matches the source doc type (Principle/ADR).
    Strips source_ref afterward (not an ArchiMate field).
    Returns original yaml_text unchanged on any parse error.
    """
    import yaml as _yaml

    try:
        data = _yaml.safe_load(yaml_text)
    except Exception:
        return yaml_text
    if not data or "elements" not in data:
        return yaml_text

    total = 0
    enriched = 0
    explicit = 0
    fallback = 0

    for elem in data.get("elements", []):
        total += 1
        ref_raw = elem.pop("source_ref", None)
        ref = normalize_ref(ref_raw) if ref_raw else None
        via_fallback = False

        # Type-gated fallback: only infer for Principle/ADR elements
        if not ref:
            expected_prefix = SOURCE_DOC_TYPES.get(
                elem.get("type", "")
            )
            if expected_prefix:
                name = elem.get("name", "")
                m = re.match(r"(?:PCP|ADR)[.\s-]*(\d+)", name, re.I)
                if m:
                    ref = normalize_ref(m.group(0))
                    via_fallback = True

        if ref and ref in source_metadata:
            props = elem.get("properties", {})
            if not isinstance(props, dict):
                props = {}
            meta = source_metadata[ref]
            props["dct:identifier"] = meta["resolved_identifier"]
            props["dct:title"] = meta["title"]
            if "creator" in meta:
                props["dct:creator"] = meta["creator"]
            if "issued" in meta:
                props["dct:issued"] = meta["issued"]
            if "language" in meta:
                props["dct:language"] = meta["language"]

            # UUID integrity check — catch pipeline corruption
            raw_dct_id = meta.get("_raw_dct_identifier", "")
            if raw_dct_id and props["dct:identifier"] != raw_dct_id:
                logger.warning(
                    "[reconciliation] UUID mismatch for %s: enriched=%s, kb=%s",
                    ref, props["dct:identifier"], raw_dct_id,
                )

            elem["properties"] = props
            enriched += 1
            if via_fallback:
                fallback += 1
            else:
                explicit += 1

    logger.info(
        "dct enrichment: %d/%d elements enriched "
        "(%d via source_ref, %d via name fallback)",
        enriched, total, explicit, fallback,
    )

    return _yaml.dump(
        data, default_flow_style=False, allow_unicode=True, sort_keys=False
    )
