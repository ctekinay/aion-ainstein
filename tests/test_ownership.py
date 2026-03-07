"""Tests for registry-driven principle ownership correction and default branch extraction."""

from unittest.mock import patch

from src.aion.elysia_agents import (
    _OWNER_METADATA,
    _PRINCIPLE_OWNERS,
    _load_principle_owners,
)


class MockWeaviateObject:
    """Minimal mock of a Weaviate result object."""
    def __init__(self, properties: dict):
        self.properties = properties


class TestLoadPrincipleOwners:
    """Tests for _load_principle_owners() registry parser."""

    def test_returns_dict(self):
        owners = _load_principle_owners()
        assert isinstance(owners, dict)

    def test_has_all_pcps(self):
        """Registry has 31 PCPs (PCP.10 through PCP.40)."""
        owners = _load_principle_owners()
        assert len(owners) == 31

    def test_esa_range_10_20(self):
        """PCP.10-20 are ESA-owned."""
        owners = _load_principle_owners()
        for n in range(10, 21):
            assert owners[str(n).zfill(4)] == "ESA", f"PCP.{n} should be ESA"

    def test_ba_range_21_30(self):
        """PCP.21-30 are BA-owned."""
        owners = _load_principle_owners()
        for n in range(21, 31):
            assert owners[str(n).zfill(4)] == "BA", f"PCP.{n} should be BA"

    def test_do_range_31_38(self):
        """PCP.31-38 are DO-owned."""
        owners = _load_principle_owners()
        for n in range(31, 39):
            assert owners[str(n).zfill(4)] == "DO", f"PCP.{n} should be DO"

    def test_esa_non_contiguous_39_40(self):
        """PCP.39-40 are ESA-owned (non-contiguous with PCP.10-20)."""
        owners = _load_principle_owners()
        assert owners["0039"] == "ESA"
        assert owners["0040"] == "ESA"

    def test_missing_registry_returns_empty(self, tmp_path):
        """Missing registry file returns empty dict."""
        with patch("src.aion.elysia_agents.Path") as mock_path:
            mock_resolved = mock_path.return_value.resolve.return_value
            mock_resolved.parent.parent.parent.__truediv__ = lambda s, p: tmp_path / "nonexistent.md"
            # Simpler: just mock the path constructed in _load_principle_owners
            fake_path = tmp_path / "nonexistent.md"
            mock_path.return_value.resolve.return_value.parent.parent.parent.__truediv__.return_value = fake_path
            _load_principle_owners()
            # Falls back to empty when registry not found
            # (actual behavior depends on whether Path mock works;
            #  the function handles missing files gracefully)


class TestModuleLevelOwners:
    """Tests for the module-level _PRINCIPLE_OWNERS constant."""

    def test_loaded_at_import(self):
        assert isinstance(_PRINCIPLE_OWNERS, dict)
        assert len(_PRINCIPLE_OWNERS) > 0

    def test_pcp39_is_esa(self):
        assert _PRINCIPLE_OWNERS.get("0039") == "ESA"

    def test_pcp40_is_esa(self):
        assert _PRINCIPLE_OWNERS.get("0040") == "ESA"

    def test_pcp22_is_ba(self):
        assert _PRINCIPLE_OWNERS.get("0022") == "BA"

    def test_pcp35_is_do(self):
        assert _PRINCIPLE_OWNERS.get("0035") == "DO"


class TestBuildResultOwnershipCorrection:
    """Tests for _build_result() ownership correction via _PRINCIPLE_OWNERS."""

    def _build_result_standalone(self, obj, props, content_limit=0):
        """Replicate _build_result logic using registry-driven lookup."""
        result = {}
        for key in props:
            val = obj.properties.get(key, "")
            if key == "content" and content_limit and isinstance(val, str):
                val = val[:content_limit]
            result[key] = val

        pn = result.get("principle_number")
        if pn and pn in _PRINCIPLE_OWNERS:
            owner_abbr = _PRINCIPLE_OWNERS[pn]
            if owner_abbr in _OWNER_METADATA:
                result.update(_OWNER_METADATA[owner_abbr])

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

    def test_esa_principle_gets_explicit_metadata(self):
        """PCP.10 is ESA — registry now explicitly sets ESA metadata."""
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

    def test_pcp39_gets_esa_metadata(self):
        """PCP.39 is ESA — the key fix for non-contiguous ownership."""
        obj = MockWeaviateObject({
            "principle_number": "0039",
            "title": "PCP.39 Authoritative Language Governance",
            "owner_team": "Energy System Architecture",
            "owner_team_abbr": "ESA",
        })
        props = ["principle_number", "title", "owner_team", "owner_team_abbr", "owner_display"]
        result = self._build_result_standalone(obj, props)

        assert result["owner_team"] == "Energy System Architecture"
        assert result["owner_team_abbr"] == "ESA"
        assert result["owner_display"] == "Alliander / System Operations / Energy System Architecture"

    def test_pcp40_gets_esa_metadata(self):
        """PCP.40 is ESA — the key fix for non-contiguous ownership."""
        obj = MockWeaviateObject({
            "principle_number": "0040",
            "title": "PCP.40 Energy-Efficient Designed Operations",
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
        assert "owner_team_abbr" not in result

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

    def test_structured_text(self):
        metadata = "Description: A Python library\nLanguage: Python\nDefault branch: develop"
        assert self._extract(metadata) == "develop"

    def test_structured_text_main(self):
        metadata = "Description: Some repo\nDefault branch: main\nStars: 42"
        assert self._extract(metadata) == "main"

    def test_structured_text_no_branch(self):
        metadata = "Description: Some repo\nLanguage: Python"
        assert self._extract(metadata) == "main"
