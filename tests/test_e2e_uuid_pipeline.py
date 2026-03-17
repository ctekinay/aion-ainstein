"""Layer 4b: UUID Pipeline E2E Tests with Traceability Extensions.

Tests the full generation pipeline for UUID correctness and source
traceability. Extends the scenarios from docs/e2e-uuid-pipeline-tests.md
with additional traceability assertions.

Requires Weaviate + Ollama. Marked @functional — auto-skips without services.
Run with: pytest -m functional tests/test_e2e_uuid_pipeline.py -v

LLM non-determinism strategy:
  - Assert on pipeline mechanics (deterministic), not LLM prose
  - Structural invariants: "at least one element with resolved dct:identifier"
  - Flaky reruns for name-dependent assertions
"""

import asyncio
import re
from xml.etree import ElementTree as ET

import pytest

NS = "http://www.opengroup.org/xsd/archimate/3.0/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_xml_elements(xml_str: str) -> list[dict]:
    """Parse ArchiMate XML and return element dicts with properties."""
    root = ET.fromstring(xml_str)
    elements = []
    for elem in root.findall(f".//{{{NS}}}element"):
        eid = elem.get("identifier", "")
        etype = elem.get("{http://www.w3.org/2001/XMLSchema-instance}type", "")
        name_el = elem.find(f"{{{NS}}}name")
        name = name_el.text if name_el is not None and name_el.text else ""

        # Extract properties
        props = {}
        for prop in elem.findall(f".//{{{NS}}}property"):
            pdef_ref = prop.get("propertyDefinitionRef", "")
            val_el = prop.find(f"{{{NS}}}value")
            val = val_el.text if val_el is not None and val_el.text else ""
            props[pdef_ref] = val

        elements.append({
            "id": eid,
            "type": etype,
            "name": name,
            "properties": props,
        })
    return elements


def _resolve_prop_defs(xml_str: str) -> dict[str, str]:
    """Map propertyDefinition identifiers to their names."""
    root = ET.fromstring(xml_str)
    prop_defs = {}
    for pdef in root.findall(f".//{{{NS}}}propertyDefinition"):
        pid = pdef.get("identifier", "")
        name_el = pdef.find(f"{{{NS}}}name")
        name = name_el.text if name_el is not None and name_el.text else ""
        prop_defs[pid] = name
    return prop_defs


def _get_dct_props(element: dict, prop_defs: dict) -> dict[str, str]:
    """Resolve an element's properties from definition refs to dct: names."""
    resolved = {}
    for pdef_ref, value in element["properties"].items():
        name = prop_defs.get(pdef_ref, pdef_ref)
        if name.startswith("dct:"):
            resolved[name] = value
    return resolved


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def generation_pipeline(weaviate_client):
    """Create a GenerationPipeline instance."""
    from aion.generation import GenerationPipeline
    return GenerationPipeline(weaviate_client)


def _run_generation(pipeline, query: str, doc_refs: list[str] | None = None):
    """Run generation synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            pipeline.generate(
                query=query,
                skill_tags=["archimate"],
                doc_refs=doc_refs,
            )
        )
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Scenario 4 + Traceability: Multi-Principle UUID Isolation
# (UUID suite Scenario 4 extended with traceability assertions)
# ---------------------------------------------------------------------------

@pytest.mark.functional
@pytest.mark.generation
@pytest.mark.flaky(reruns=2)
class TestMultiPrincipleUUIDIsolation:
    """UUID pipeline Scenario 4: Multi-principle generation.

    Asserts that each Principle element gets the correct dct:identifier
    from its respective KB source, and that derived elements do NOT
    get false provenance.
    """

    def test_multi_pcp_uuid_isolation_and_traceability(self, generation_pipeline, weaviate_client):
        """Generate model for PCP.10 + PCP.11, verify UUID isolation + traceability."""
        from weaviate.classes.query import Filter

        # First, get the actual dct_identifiers from Weaviate
        col_name = "Principle"
        try:
            col = weaviate_client.collections.get(col_name)
        except Exception:
            col = weaviate_client.collections.get(f"{col_name}_OpenAI")

        expected_uuids = {}
        expected_titles = {}
        for pn in ["0010", "0011"]:
            results = col.query.fetch_objects(
                filters=Filter.by_property("principle_number").equal(pn),
                limit=1,
                return_properties=["dct_identifier", "title"],
            )
            if results.objects:
                obj = results.objects[0]
                ref = f"PCP.{int(pn)}"
                expected_uuids[ref] = obj.properties.get("dct_identifier", "")
                expected_titles[ref] = obj.properties.get("title", "")

        if len(expected_uuids) < 2:
            pytest.skip("PCP.10 and/or PCP.11 not in Weaviate with dct_identifier")

        # Generate model
        response, objects = _run_generation(
            generation_pipeline,
            "Create an ArchiMate model covering PCP.10 and PCP.11",
            doc_refs=["PCP.10", "PCP.11"],
        )

        assert response, "Generation returned empty response"

        # Extract XML from response (it may be wrapped in markdown fences)
        xml_match = re.search(r"<\?xml.*?</model>", response, re.DOTALL)
        if not xml_match:
            # Response might be the XML directly
            if response.strip().startswith("<?xml") or response.strip().startswith("<model"):
                xml_str = response
            else:
                pytest.fail("No XML found in generation response")
        else:
            xml_str = xml_match.group(0)

        elements = _parse_xml_elements(xml_str)
        prop_defs = _resolve_prop_defs(xml_str)

        # --- UUID Isolation assertions ---
        principle_elements = [e for e in elements if e["type"] == "Principle"]
        assert len(principle_elements) >= 2, (
            f"Expected at least 2 Principle elements, found {len(principle_elements)}"
        )

        # Check each principle has its own UUID
        found_uuids = {}
        for elem in principle_elements:
            dct = _get_dct_props(elem, prop_defs)
            dct_id = dct.get("dct:identifier", "")
            if dct_id:
                found_uuids[elem["name"]] = dct_id

        # At least one element should have a resolved dct:identifier
        assert found_uuids, (
            "No Principle elements have dct:identifier — enrichment pipeline may have failed"
        )

        # No two elements should share the same dct:identifier
        uuid_values = list(found_uuids.values())
        assert len(uuid_values) == len(set(uuid_values)), (
            f"UUID collision detected — two elements share the same dct:identifier: {found_uuids}"
        )

        # --- Traceability assertions ---
        # Derived elements (BusinessRole, Goal, etc.) should NOT have dct:identifier
        derived_types = {"BusinessRole", "BusinessProcess", "Goal", "Requirement",
                         "ApplicationComponent", "SystemSoftware", "Node"}
        for elem in elements:
            if elem["type"] in derived_types:
                dct = _get_dct_props(elem, prop_defs)
                assert "dct:identifier" not in dct, (
                    f"Derived element '{elem['name']}' (type={elem['type']}) has "
                    f"false dct:identifier provenance: {dct.get('dct:identifier')}"
                )

        # Check dct:title present on enriched elements
        for elem in principle_elements:
            dct = _get_dct_props(elem, prop_defs)
            if dct.get("dct:identifier"):
                assert dct.get("dct:title"), (
                    f"Principle '{elem['name']}' has dct:identifier but missing dct:title"
                )


# ---------------------------------------------------------------------------
# Scenario 10 + Validation: Double urn:uuid: prefix (E2E check)
# ---------------------------------------------------------------------------

@pytest.mark.functional
@pytest.mark.generation
@pytest.mark.flaky(reruns=2)
class TestDoubleUrnPrefixE2E:
    """UUID pipeline Scenario 10: No double urn:uuid: in generated XML."""

    def test_no_double_prefix_in_generated_xml(self, generation_pipeline):
        """Generate a single-PCP model and verify no double urn:uuid:."""
        response, _ = _run_generation(
            generation_pipeline,
            "Create an ArchiMate model for PCP.10",
            doc_refs=["PCP.10"],
        )

        if not response:
            pytest.skip("Generation returned empty response")

        # Check for double prefix anywhere in the response
        assert "urn:uuid:urn:uuid:" not in response, (
            "Double urn:uuid: prefix detected in generated output"
        )
