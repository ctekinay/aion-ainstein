"""Tests for registry-driven principle ownership correction and default branch extraction."""

from unittest.mock import MagicMock

from aion.ingestion.ingestion import (
    _OWNER_METADATA,
    DataIngestionPipeline,
    _load_principle_owner_map,
)


class TestLoadPrincipleOwnerMap:
    """Tests for _load_principle_owner_map() registry parser."""

    def test_returns_dict(self):
        owners = _load_principle_owner_map()
        assert isinstance(owners, dict)

    def test_has_all_pcps(self):
        """Registry has 41 PCPs (PCP.10 through PCP.50)."""
        owners = _load_principle_owner_map()
        assert len(owners) == 41

    def test_esa_range_10_20(self):
        """PCP.10-20 are ESA-owned."""
        owners = _load_principle_owner_map()
        for n in range(10, 21):
            assert owners[str(n).zfill(4)] == "ESA", f"PCP.{n} should be ESA"

    def test_ba_range_21_30(self):
        """PCP.21-30 are BA-owned."""
        owners = _load_principle_owner_map()
        for n in range(21, 31):
            assert owners[str(n).zfill(4)] == "BA", f"PCP.{n} should be BA"

    def test_do_range_31_38(self):
        """PCP.31-38 are DO-owned."""
        owners = _load_principle_owner_map()
        for n in range(31, 39):
            assert owners[str(n).zfill(4)] == "DO", f"PCP.{n} should be DO"

    def test_esa_non_contiguous_39_40(self):
        """PCP.39-40 are ESA-owned (non-contiguous with PCP.10-20)."""
        owners = _load_principle_owner_map()
        assert owners["0039"] == "ESA"
        assert owners["0040"] == "ESA"

    def test_nb_ea_range_41_48(self):
        """PCP.41-48 are NB-EA-owned."""
        owners = _load_principle_owner_map()
        for n in range(41, 49):
            assert owners[str(n).zfill(4)] == "NB-EA", f"PCP.{n} should be NB-EA"

    def test_ea_range_49_50(self):
        """PCP.49-50 are EA-owned."""
        owners = _load_principle_owner_map()
        assert owners["0049"] == "EA"
        assert owners["0050"] == "EA"

    def test_pcp39_is_esa(self):
        assert _load_principle_owner_map().get("0039") == "ESA"

    def test_pcp22_is_ba(self):
        assert _load_principle_owner_map().get("0022") == "BA"

    def test_pcp35_is_do(self):
        assert _load_principle_owner_map().get("0035") == "DO"

    def test_pcp41_is_nb_ea(self):
        assert _load_principle_owner_map().get("0041") == "NB-EA"


def _make_pipeline_with_owners():
    """Return a DataIngestionPipeline instance with _principle_owners loaded (no Weaviate)."""
    pipeline = object.__new__(DataIngestionPipeline)
    pipeline._principle_owners = _load_principle_owner_map()
    return pipeline


def _override(target, principle_number: str) -> None:
    """Convenience wrapper — calls _override_principle_ownership on a pipeline instance."""
    pipeline = _make_pipeline_with_owners()
    pipeline._override_principle_ownership(target, principle_number)


class TestOverridePrincipleOwnershipDict:
    """Tests for _override_principle_ownership() with dict targets (legacy path)."""

    def test_ba_principle_overrides_esa_default(self):
        """PCP.22 (BA) overwrites the ESA default from index.md."""
        doc = {
            "principle_number": "0022",
            "owner_team": "Energy System Architecture",
            "owner_team_abbr": "ESA",
            "owner_display": "Alliander / System Operations / Energy System Architecture",
        }
        _override(doc, "0022")
        assert doc["owner_team"] == "Business Architecture"
        assert doc["owner_team_abbr"] == "BA"
        assert doc["owner_display"] == "Alliander / Business Architecture Group"

    def test_do_principle_overrides_esa_default(self):
        """PCP.35 (DO) overwrites the ESA default from index.md."""
        doc = {"owner_team": "Energy System Architecture", "owner_team_abbr": "ESA"}
        _override(doc, "0035")
        assert doc["owner_team"] == "Data Office"
        assert doc["owner_team_abbr"] == "DO"

    def test_nb_ea_principle_overrides_esa_default(self):
        """PCP.41 (NB-EA) overwrites the ESA default from index.md."""
        doc = {"owner_team": "Energy System Architecture", "owner_team_abbr": "ESA"}
        _override(doc, "0041")
        assert doc["owner_team"] == "Netbeheer Nederland Enterprise Architecture"
        assert doc["owner_team_abbr"] == "NB-EA"

    def test_ea_principle_overrides_esa_default(self):
        """PCP.49 (EA) overwrites the ESA default from index.md."""
        doc = {"owner_team": "Energy System Architecture", "owner_team_abbr": "ESA"}
        _override(doc, "0049")
        assert doc["owner_team"] == "Enterprise Architecture"
        assert doc["owner_team_abbr"] == "EA"

    def test_esa_principle_stays_esa(self):
        """PCP.10 is ESA — override keeps ESA values, replacing the empty index.md default."""
        doc = {"owner_team": "Energy System Architecture", "owner_team_abbr": "ESA"}
        _override(doc, "0010")
        assert doc["owner_team"] == "Energy System Architecture"
        assert doc["owner_team_abbr"] == "ESA"

    def test_pcp39_stays_esa(self):
        """PCP.39 is ESA (non-contiguous) — the key fix for the original bug."""
        doc = {"owner_team": "Energy System Architecture", "owner_team_abbr": "ESA"}
        _override(doc, "0039")
        assert doc["owner_team_abbr"] == "ESA"
        assert doc["owner_display"] == "Alliander / System Operations / Energy System Architecture"

    def test_empty_principle_number_no_op(self):
        """Empty principle_number should leave dict unchanged."""
        doc = {"owner_team": "Energy System Architecture"}
        _override(doc, "")
        assert doc["owner_team"] == "Energy System Architecture"

    def test_unknown_principle_number_no_op(self):
        """Unknown principle_number (not in registry) should leave dict unchanged."""
        doc = {"owner_team": "Energy System Architecture"}
        _override(doc, "9999")
        assert doc["owner_team"] == "Energy System Architecture"


class TestOverridePrincipleOwnershipChunk:
    """Tests for _override_principle_ownership() with Chunk targets (chunked path)."""

    def _make_chunk(self, owner_team="Energy System Architecture",
                    owner_team_abbr="ESA", owner_display=""):
        chunk = MagicMock()
        chunk.metadata.owner_team = owner_team
        chunk.metadata.owner_team_abbr = owner_team_abbr
        chunk.metadata.owner_display = owner_display
        return chunk

    def test_ba_chunk_overrides_esa_default(self):
        chunk = self._make_chunk()
        _override(chunk, "0025")
        assert chunk.metadata.owner_team == "Business Architecture"
        assert chunk.metadata.owner_team_abbr == "BA"

    def test_nb_ea_chunk_overrides_esa_default(self):
        chunk = self._make_chunk()
        _override(chunk, "0041")
        assert chunk.metadata.owner_team_abbr == "NB-EA"
        assert chunk.metadata.owner_display == "Netbeheer Nederland / Enterprise Architecture Group"

    def test_esa_chunk_stays_esa(self):
        chunk = self._make_chunk()
        _override(chunk, "0015")
        assert chunk.metadata.owner_team_abbr == "ESA"


class TestExtractDefaultBranch:
    """Tests for GenerationPipeline._extract_default_branch()."""

    def _extract(self, metadata: str) -> str:
        from aion.generation import GenerationPipeline
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
