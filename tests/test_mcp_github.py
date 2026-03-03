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
            "owner": "Alliander",
            "repo": "esa-ainstein-artifacts",
            "ref": "main",
            "path": "tests/model.xml",
        }

    def test_blob_url_with_branch(self):
        url = "https://github.com/Alliander/repo/blob/ainstein-skills-framework-v2/path/to/file.xml"
        result = parse_github_url(url)
        assert result["ref"] == "ainstein-skills-framework-v2"
        assert result["path"] == "path/to/file.xml"

    def test_raw_url(self):
        url = "https://raw.githubusercontent.com/Alliander/repo/main/file.xml"
        result = parse_github_url(url)
        assert result == {
            "owner": "Alliander",
            "repo": "repo",
            "ref": "main",
            "path": "file.xml",
        }

    def test_non_github_url(self):
        assert parse_github_url("https://example.com/file.xml") is None

    def test_repo_url_without_file(self):
        assert parse_github_url("https://github.com/Alliander/repo") is None

    def test_github_url_no_blob(self):
        """Tree URLs (without /blob/) are not file URLs."""
        assert parse_github_url("https://github.com/Alliander/repo/tree/main") is None


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
