"""Tests for principle ownership correction and default branch extraction."""

import pytest

from src.aion.elysia_agents import _get_principle_owner_group, _PRINCIPLE_OWNER_MAP


class MockWeaviateObject:
    """Minimal mock of a Weaviate result object."""
    def __init__(self, properties: dict):
        self.properties = properties


class TestGetPrincipleOwnerGroup:
    """Tests for _get_principle_owner_group() number → group mapping."""

    def test_esa_range_returns_none(self):
        """PCP.10-20 are ESA (default), function returns None."""
        assert _get_principle_owner_group("0010") is None
        assert _get_principle_owner_group("0015") is None
        assert _get_principle_owner_group("0020") is None

    def test_ba_range(self):
        """PCP.21-30 are Business Architecture."""
        assert _get_principle_owner_group("0021") == "BA"
        assert _get_principle_owner_group("0025") == "BA"
        assert _get_principle_owner_group("0030") == "BA"

    def test_do_range(self):
        """PCP.31-38 are Data Office."""
        assert _get_principle_owner_group("0031") == "DO"
        assert _get_principle_owner_group("0035") == "DO"
        assert _get_principle_owner_group("0038") == "DO"

    def test_boundary_ba_do(self):
        """PCP.30 is BA, PCP.31 is DO."""
        assert _get_principle_owner_group("0030") == "BA"
        assert _get_principle_owner_group("0031") == "DO"

    def test_above_do_range(self):
        """PCP.39+ are ESA (outside override ranges)."""
        assert _get_principle_owner_group("0039") is None
        assert _get_principle_owner_group("0040") is None

    def test_invalid_value(self):
        assert _get_principle_owner_group("invalid") is None
        assert _get_principle_owner_group("") is None
        assert _get_principle_owner_group(None) is None


class TestBuildResultOwnershipCorrection:
    """Tests for _build_result() ownership correction via _PRINCIPLE_OWNER_MAP."""

    def _build_result_standalone(self, obj, props, content_limit=0):
        """Replicate _build_result logic without needing a full ElysiaRAGSystem."""
        result = {}
        for key in props:
            val = obj.properties.get(key, "")
            if key == "content" and content_limit and isinstance(val, str):
                val = val[:content_limit]
            result[key] = val

        pn = result.get("principle_number")
        if pn:
            group = _get_principle_owner_group(pn)
            if group and group in _PRINCIPLE_OWNER_MAP:
                result.update(_PRINCIPLE_OWNER_MAP[group])

        return result

    def test_ba_principle_gets_corrected(self):
        """PCP.22 should have Business Architecture ownership."""
        obj = MockWeaviateObject({
            "principle_number": "0022",
            "title": "PCP.22 Omnichannel",
            "owner_team": "Energy System Architecture",
            "owner_team_abbr": "ESA",
            "owner_display": "Alliander / System Operations / Energy System Architecture",
        })
        props = ["principle_number", "title", "owner_team", "owner_team_abbr", "owner_display"]
        result = self._build_result_standalone(obj, props)

        assert result["owner_team"] == "Business Architecture"
        assert result["owner_team_abbr"] == "BA"
        assert result["owner_display"] == "Alliander / Business Architecture Group"

    def test_do_principle_gets_corrected(self):
        """PCP.35 should have Data Office ownership."""
        obj = MockWeaviateObject({
            "principle_number": "0035",
            "title": "PCP.35 Data is begrijpelijk",
            "owner_team": "Energy System Architecture",
            "owner_team_abbr": "ESA",
        })
        props = ["principle_number", "title", "owner_team", "owner_team_abbr"]
        result = self._build_result_standalone(obj, props)

        assert result["owner_team"] == "Data Office"
        assert result["owner_team_abbr"] == "DO"

    def test_esa_principle_unchanged(self):
        """PCP.10 is correctly ESA — no correction applied."""
        obj = MockWeaviateObject({
            "principle_number": "0010",
            "title": "PCP.10 Eventual Consistency",
            "owner_team": "Energy System Architecture",
            "owner_team_abbr": "ESA",
        })
        props = ["principle_number", "title", "owner_team", "owner_team_abbr"]
        result = self._build_result_standalone(obj, props)

        assert result["owner_team"] == "Energy System Architecture"
        assert result["owner_team_abbr"] == "ESA"

    def test_non_principle_object_unchanged(self):
        """ADR results (no principle_number) should not be affected."""
        obj = MockWeaviateObject({
            "adr_number": "0029",
            "title": "ADR.29 OAuth 2.0",
            "owner_team": "Energy System Architecture",
        })
        props = ["adr_number", "title", "owner_team"]
        result = self._build_result_standalone(obj, props)

        assert result["owner_team"] == "Energy System Architecture"
        assert "owner_team_abbr" not in result  # no correction applied

    def test_content_truncation_still_works(self):
        """Content truncation should work alongside ownership correction."""
        obj = MockWeaviateObject({
            "principle_number": "0025",
            "content": "x" * 1000,
        })
        props = ["principle_number", "content"]
        result = self._build_result_standalone(obj, props, content_limit=100)

        assert len(result["content"]) == 100
        assert result["owner_team"] == "Business Architecture"


class TestExtractDefaultBranch:
    """Tests for GenerationPipeline._extract_default_branch()."""

    def _extract(self, metadata: str) -> str:
        from src.aion.generation import GenerationPipeline
        return GenerationPipeline._extract_default_branch(metadata)

    def test_json_field(self):
        metadata = '{"name": "repo", "default_branch": "develop", "stars": 42}'
        assert self._extract(metadata) == "develop"

    def test_main_branch(self):
        metadata = '{"default_branch": "main"}'
        assert self._extract(metadata) == "main"

    def test_master_branch(self):
        metadata = '{"default_branch": "master"}'
        assert self._extract(metadata) == "master"

    def test_no_field_falls_back_to_main(self):
        metadata = '{"name": "repo", "description": "some repo"}'
        assert self._extract(metadata) == "main"

    def test_empty_string_falls_back_to_main(self):
        assert self._extract("") == "main"

    def test_plain_text_falls_back_to_main(self):
        assert self._extract("desc") == "main"

    def test_multiline_json(self):
        metadata = '{\n  "name": "repo",\n  "default_branch": "trunk"\n}'
        assert self._extract(metadata) == "trunk"
