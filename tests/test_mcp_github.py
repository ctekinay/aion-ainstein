"""Tests for MCP GitHub integration: URL parsing and registry."""

import os

import pytest

from src.aion.mcp.github import parse_github_url
from src.aion.mcp.registry import get_server, load_registry, _servers


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

class TestParseGithubUrl:

    def test_blob_url(self):
        url = "https://github.com/Alliander/esa-ainstein-artifacts/blob/main/tests/model.xml"
        result = parse_github_url(url)
        assert result == {
            "type": "file",
            "owner": "Alliander",
            "repo": "esa-ainstein-artifacts",
            "ref": "main",
            "path": "tests/model.xml",
        }

    def test_blob_url_with_branch(self):
        url = "https://github.com/Alliander/repo/blob/ainstein-skills-framework-v2/path/to/file.xml"
        result = parse_github_url(url)
        assert result["type"] == "file"
        assert result["ref"] == "ainstein-skills-framework-v2"
        assert result["path"] == "path/to/file.xml"

    def test_raw_url(self):
        url = "https://raw.githubusercontent.com/Alliander/repo/main/file.xml"
        result = parse_github_url(url)
        assert result == {
            "type": "file",
            "owner": "Alliander",
            "repo": "repo",
            "ref": "main",
            "path": "file.xml",
        }

    def test_non_github_url(self):
        assert parse_github_url("https://example.com/file.xml") is None

    def test_repo_root_url(self):
        result = parse_github_url("https://github.com/Alliander/repo")
        assert result == {
            "type": "repo",
            "owner": "Alliander",
            "repo": "repo",
            "ref": "main",
        }

    def test_repo_root_url_trailing_slash(self):
        result = parse_github_url("https://github.com/Alliander/repo/")
        assert result is not None
        assert result["type"] == "repo"
        assert result["owner"] == "Alliander"
        assert result["repo"] == "repo"

    def test_repo_tree_url(self):
        result = parse_github_url("https://github.com/Alliander/repo/tree/develop")
        assert result == {
            "type": "repo",
            "owner": "Alliander",
            "repo": "repo",
            "ref": "develop",
        }

    def test_repo_tree_url_default_ref(self):
        """Repo root without /tree/ defaults to main."""
        result = parse_github_url("https://github.com/OpenSTEF/openstef")
        assert result["type"] == "repo"
        assert result["ref"] == "main"

    def test_file_url_never_matches_repo(self):
        """File URLs with /blob/ always return type 'file', never 'repo'."""
        url = "https://github.com/Alliander/repo/blob/main/model.archimate.xml"
        result = parse_github_url(url)
        assert result["type"] == "file"
        assert result["path"] == "model.archimate.xml"

    def test_org_url(self):
        result = parse_github_url("https://github.com/OpenSTEF")
        assert result == {"type": "org", "owner": "OpenSTEF"}

    def test_org_url_trailing_slash(self):
        result = parse_github_url("https://github.com/OpenSTEF/")
        assert result == {"type": "org", "owner": "OpenSTEF"}

    def test_org_url_not_confused_with_repo(self):
        """Single-segment URL is org, two-segment URL is repo."""
        org = parse_github_url("https://github.com/OpenSTEF")
        repo = parse_github_url("https://github.com/OpenSTEF/openstef")
        assert org["type"] == "org"
        assert repo["type"] == "repo"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:

    def setup_method(self):
        _servers.clear()

    def test_load_registry(self):
        servers = load_registry()
        assert "github" in servers
        assert servers["github"].url == "https://api.githubcopilot.com/mcp/"

    def test_get_server(self):
        server = get_server("github")
        assert server.read_only is True
        assert server.auth_type == "bearer"
        assert server.auth_env_var == "GITHUB_TOKEN"

    def test_missing_server(self):
        load_registry()
        with pytest.raises(KeyError):
            get_server("nonexistent")

    def test_auth_headers_with_token(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        server = get_server("github")
        headers = server.auth_headers
        assert headers["Authorization"] == "Bearer ghp_test123"
        assert headers.get("X-MCP-Readonly") == "true"

    def test_auth_headers_without_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        server = get_server("github")
        assert "Authorization" not in server.auth_headers


# ---------------------------------------------------------------------------
# Integration (requires PAT)
# ---------------------------------------------------------------------------

class TestGetFileContents:

    @pytest.mark.skipif(
        not os.environ.get("GITHUB_TOKEN"),
        reason="No GITHUB_TOKEN set",
    )
    @pytest.mark.asyncio
    async def test_fetch_file(self):
        from src.aion.mcp.github import get_file_contents

        content = await get_file_contents(
            owner="modelcontextprotocol",
            repo="python-sdk",
            path="README.md",
            ref="main",
        )
        assert len(content) > 100
        assert "MCP" in content


class TestGetRepoReadme:

    @pytest.mark.skipif(
        not os.environ.get("GITHUB_TOKEN"),
        reason="No GITHUB_TOKEN set",
    )
    @pytest.mark.asyncio
    async def test_fetch_readme(self):
        from src.aion.mcp.github import get_repo_readme

        content = await get_repo_readme(
            owner="modelcontextprotocol",
            repo="python-sdk",
            ref="main",
        )
        assert len(content) > 100
        assert "MCP" in content


class TestListDirectory:

    @pytest.mark.skipif(
        not os.environ.get("GITHUB_TOKEN"),
        reason="No GITHUB_TOKEN set",
    )
    @pytest.mark.asyncio
    async def test_list_root(self):
        from src.aion.mcp.github import list_directory

        result = await list_directory(
            owner="modelcontextprotocol",
            repo="python-sdk",
            path="",
            ref="main",
        )
        assert len(result) > 0


class TestGetRepoMetadata:

    @pytest.mark.skipif(
        not os.environ.get("GITHUB_TOKEN"),
        reason="No GITHUB_TOKEN set",
    )
    @pytest.mark.asyncio
    async def test_get_metadata(self):
        from src.aion.mcp.github import get_repo_metadata

        result = await get_repo_metadata(
            owner="modelcontextprotocol",
            repo="python-sdk",
        )
        assert len(result) > 0


class TestGetOrgOverview:

    @pytest.mark.skipif(
        not os.environ.get("GITHUB_TOKEN"),
        reason="No GITHUB_TOKEN set",
    )
    @pytest.mark.asyncio
    async def test_get_org(self):
        from src.aion.mcp.github import get_org_overview

        result = await get_org_overview("OpenSTEF")
        assert "OpenSTEF" in result
        assert "REPOSITORIES" in result
