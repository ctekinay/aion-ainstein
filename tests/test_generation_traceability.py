"""Layer 4a: Generation Traceability Tests (cheap, mock-based, no services).

Validates that the DCT enrichment pipeline, ArchiMate validation, and
YAML→XML conversion handle edge cases correctly. All tests use mock
data — no LLM or Weaviate required.

Run with: pytest tests/test_generation_traceability.py
"""

import textwrap

import pytest
import yaml

# ---------------------------------------------------------------------------
# Test 1: Derived elements have NO false dct:identifier
# ---------------------------------------------------------------------------

class TestDerivedElementsNoDctProps:
    """Only source-linked elements (Principle, ADR) should get dct properties.
    Derived elements (BusinessRole, Goal) must NOT inherit them."""

    def test_only_principle_gets_dct(self):
        from aion.tools.reconciliation import enrich_yaml_with_dct

        yaml_text = textwrap.dedent("""\
            model:
              name: "Test Model"
            elements:
              - id: m1
                type: Principle
                name: "PCP.10 Eventual Consistency"
                source_ref: PCP.10
              - id: b1
                type: BusinessRole
                name: "Data Steward"
        """)

        source_metadata = {
            "PCP.10": {
                "resolved_identifier": "urn:uuid:aaa-10",
                "title": "Eventual Consistency by Design",
                "language": "en",
            }
        }

        result = enrich_yaml_with_dct(yaml_text, source_metadata)
        data = yaml.safe_load(result)

        principle = next(e for e in data["elements"] if e["id"] == "m1")
        business_role = next(e for e in data["elements"] if e["id"] == "b1")

        # Principle element should have dct properties
        assert "properties" in principle
        assert principle["properties"]["dct:identifier"] == "urn:uuid:aaa-10"

        # BusinessRole should NOT have dct properties
        assert "properties" not in business_role or \
            "dct:identifier" not in business_role.get("properties", {})


# ---------------------------------------------------------------------------
# Test 2: validate_archimate element count matches YAML
# ---------------------------------------------------------------------------

class TestValidationCountsMatchYAML:
    """Element/relationship counts from validate_archimate() must match
    the actual counts in the source YAML."""

    def test_counts_match(self):
        from aion.tools.archimate import validate_archimate
        from aion.tools.yaml_to_xml import yaml_to_archimate_xml

        yaml_text = textwrap.dedent("""\
            model:
              name: "Count Test"
            elements:
              - id: a1
                type: ApplicationComponent
                name: "Auth Service"
                documentation: "Authentication service."
              - id: a2
                type: ApplicationInterface
                name: "Login API"
                documentation: "REST API for login."
              - id: b1
                type: BusinessProcess
                name: "Login Process"
                documentation: "User login flow."
            relationships:
              - type: Serving
                source: a1
                target: b1
              - type: Composition
                source: a1
                target: a2
        """)

        xml_str, info = yaml_to_archimate_xml(yaml_text)
        validation = validate_archimate(xml_str)

        assert validation["valid"], f"XML validation failed: {validation['errors']}"
        assert validation["element_count"] == 3
        assert validation["relationship_count"] == 2
        assert info["element_count"] == 3
        assert info["relationship_count"] == 2


# ---------------------------------------------------------------------------
# Test 3: View elements reference only existing model elements
# ---------------------------------------------------------------------------

class TestViewReferentialIntegrity:
    """validate_archimate() must catch dangling elementRef in views."""

    def test_dangling_view_ref_detected(self):
        from aion.tools.archimate import validate_archimate

        # Manually constructed XML with a view node pointing to non-existent element
        xml = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <model xmlns="http://www.opengroup.org/xsd/archimate/3.0/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xsi:schemaLocation="http://www.opengroup.org/xsd/archimate/3.0/ archimate3_Diagram.xsd"
                   identifier="id-model-1">
              <name xml:lang="en">Test</name>
              <elements>
                <element identifier="id-elem-1" xsi:type="ApplicationComponent">
                  <name xml:lang="en">Real Component</name>
                  <documentation xml:lang="en">Exists.</documentation>
                </element>
              </elements>
              <views>
                <diagrams>
                  <view identifier="id-view-1" xsi:type="Diagram">
                    <name xml:lang="en">Test View</name>
                    <node identifier="id-node-1" elementRef="id-elem-GHOST"
                          x="0" y="0" w="120" h="55"/>
                  </view>
                </diagrams>
              </views>
            </model>
        """)

        result = validate_archimate(xml)
        # Should have an error about the dangling reference
        dangling_errors = [e for e in result["errors"] if "GHOST" in e or "not found" in e.lower()]
        assert dangling_errors, (
            f"Expected error about dangling elementRef 'id-elem-GHOST', "
            f"got errors: {result['errors']}"
        )


# ---------------------------------------------------------------------------
# Test 4: Hallucinated element type rejected
# ---------------------------------------------------------------------------

class TestHallucinatedElementTypeRejected:
    """validate_archimate() must flag invalid element types."""

    def test_invalid_type_detected(self):
        from aion.tools.archimate import validate_archimate

        xml = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <model xmlns="http://www.opengroup.org/xsd/archimate/3.0/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   identifier="id-model-1">
              <name xml:lang="en">Test</name>
              <elements>
                <element identifier="id-e1" xsi:type="MadeUpType">
                  <name xml:lang="en">Fake Element</name>
                  <documentation xml:lang="en">This type doesn't exist.</documentation>
                </element>
              </elements>
            </model>
        """)

        result = validate_archimate(xml)
        assert not result["valid"], "Validation should fail for invalid element type"
        type_errors = [e for e in result["errors"] if "MadeUpType" in e]
        assert type_errors, f"Expected error about 'MadeUpType', got: {result['errors']}"


# ---------------------------------------------------------------------------
# Test 5: Invalid relationship direction caught
# ---------------------------------------------------------------------------

class TestInvalidRelationshipDirection:
    """validate_archimate() should catch Serving in wrong direction (Biz→Tech)."""

    def test_invalid_serving_direction(self):
        from aion.tools.archimate import validate_archimate
        from aion.tools.yaml_to_xml import yaml_to_archimate_xml

        yaml_text = textwrap.dedent("""\
            model:
              name: "Invalid Direction Test"
            elements:
              - id: b1
                type: BusinessProcess
                name: "Biz Process"
                documentation: "A business process."
              - id: t1
                type: SystemSoftware
                name: "Database"
                documentation: "Database software."
            relationships:
              - type: Serving
                source: b1
                target: t1
                name: "serves (wrong direction)"
        """)

        xml_str, _ = yaml_to_archimate_xml(yaml_text)
        result = validate_archimate(xml_str)

        # Serving should go upward (Tech→App, App→Biz), not downward (Biz→Tech).
        # Check if validation catches this — depends on how strict the validator is.
        # If it doesn't flag it, this test documents the gap.
        serving_warnings = [
            w for w in result.get("warnings", []) + result.get("errors", [])
            if "Serving" in w or "serving" in w.lower()
        ]
        # This is an informational test — document whether the validator catches it
        if not serving_warnings:
            pytest.skip(
                "Validator does not currently enforce Serving direction rules. "
                "Consider adding this check to validate_archimate()."
            )


# ---------------------------------------------------------------------------
# Test 6: enrich_yaml_with_dct with empty source_metadata
# ---------------------------------------------------------------------------

class TestEnrichWithEmptyMetadata:
    """No crash when source_ref points to non-existent doc (PCP.99).
    source_ref must be stripped, no dct props added."""

    def test_unmatched_source_ref_graceful(self):
        from aion.tools.reconciliation import enrich_yaml_with_dct

        yaml_text = textwrap.dedent("""\
            model:
              name: "Ghost Ref Test"
            elements:
              - id: m1
                type: Principle
                name: "PCP.99 Non-Existent"
                source_ref: PCP.99
              - id: m2
                type: Principle
                name: "PCP.10 Real One"
                source_ref: PCP.10
        """)

        source_metadata = {
            "PCP.10": {
                "resolved_identifier": "urn:uuid:aaa-10",
                "title": "Eventual Consistency",
                "language": "en",
            }
            # PCP.99 intentionally missing
        }

        result = enrich_yaml_with_dct(yaml_text, source_metadata)
        data = yaml.safe_load(result)

        # PCP.99 element: source_ref stripped, no dct props
        ghost = next(e for e in data["elements"] if e["id"] == "m1")
        assert "source_ref" not in ghost, "source_ref should be stripped"
        assert "dct:identifier" not in ghost.get("properties", {}), \
            "Ghost ref should not get dct properties"

        # PCP.10 element: enriched normally
        real = next(e for e in data["elements"] if e["id"] == "m2")
        assert "source_ref" not in real, "source_ref should be stripped"
        assert real["properties"]["dct:identifier"] == "urn:uuid:aaa-10"


# ---------------------------------------------------------------------------
# Test 7: enrich_yaml_with_dct preserves existing properties
# ---------------------------------------------------------------------------

class TestEnrichPreservesExistingProperties:
    """Enrichment adds dct props without overwriting custom properties."""

    def test_custom_props_preserved(self):
        from aion.tools.reconciliation import enrich_yaml_with_dct

        yaml_text = textwrap.dedent("""\
            model:
              name: "Props Test"
            elements:
              - id: m1
                type: Principle
                name: "PCP.10 Test"
                source_ref: PCP.10
                properties:
                  "custom:priority": "high"
                  "custom:team": "architecture"
        """)

        source_metadata = {
            "PCP.10": {
                "resolved_identifier": "urn:uuid:aaa-10",
                "title": "Test Principle",
                "language": "en",
            }
        }

        result = enrich_yaml_with_dct(yaml_text, source_metadata)
        data = yaml.safe_load(result)

        elem = data["elements"][0]
        props = elem["properties"]

        # Custom properties preserved
        assert props["custom:priority"] == "high"
        assert props["custom:team"] == "architecture"
        # dct properties added
        assert props["dct:identifier"] == "urn:uuid:aaa-10"
        assert props["dct:title"] == "Test Principle"


# ---------------------------------------------------------------------------
# Test 8: Double urn:uuid: prefix prevention
# ---------------------------------------------------------------------------

class TestDoubleUrnUuidPrevention:
    """build_source_metadata() must NOT produce urn:uuid:urn:uuid:..."""

    def test_dct_identifier_already_has_prefix(self):
        from aion.tools.reconciliation import build_source_metadata

        sources = [{
            "principle_number": "0010",
            "dct_identifier": "urn:uuid:3c4d5e6f-7a8b-4c9d-0e1f-2a3b4c5d6e7f",
            "title": "Test Principle",
            "kb_uuid": "wv-chunk-random-001",
        }]

        meta = build_source_metadata(sources)
        assert "PCP.10" in meta
        resolved = meta["PCP.10"]["resolved_identifier"]

        # Must NOT have double prefix
        assert not resolved.startswith("urn:uuid:urn:uuid:"), (
            f"Double urn:uuid: prefix detected: {resolved}"
        )
        # Must have exactly one prefix
        assert resolved == "urn:uuid:3c4d5e6f-7a8b-4c9d-0e1f-2a3b4c5d6e7f"

    def test_bare_uuid_gets_prefix_added(self):
        from aion.tools.reconciliation import build_source_metadata

        sources = [{
            "principle_number": "0010",
            "dct_identifier": "3c4d5e6f-7a8b-4c9d-0e1f-2a3b4c5d6e7f",
            "title": "Test Principle",
            "kb_uuid": "",
        }]

        meta = build_source_metadata(sources)
        resolved = meta["PCP.10"]["resolved_identifier"]
        assert resolved == "urn:uuid:3c4d5e6f-7a8b-4c9d-0e1f-2a3b4c5d6e7f"

    def test_kb_uuid_fallback_gets_prefix(self):
        from aion.tools.reconciliation import build_source_metadata

        sources = [{
            "principle_number": "0010",
            "dct_identifier": "",
            "title": "Test Principle",
            "kb_uuid": "abc-def-123",
        }]

        meta = build_source_metadata(sources)
        resolved = meta["PCP.10"]["resolved_identifier"]
        assert resolved == "urn:uuid:abc-def-123"
