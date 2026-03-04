"""GitHub MCP integration for AInstein.

Provides file retrieval, URL parsing, and repo browsing for the inspect pipeline.
Uses the remote GitHub MCP server at api.githubcopilot.com.
"""

import logging
import re

from .client import call_tool
from .registry import get_server

logger = logging.getLogger(__name__)


async def get_file_contents(
    owner: str,
    repo: str,
    path: str,
    ref: str = "main",
) -> str:
    """Fetch a file from a GitHub repository via MCP.

    Args:
        owner: GitHub org or user (e.g., "Alliander").
        repo: Repository name.
        path: File path within the repo.
        ref: Branch or tag (default: "main").

    Returns:
        File content as a string.

    Raises:
        ValueError: If fetch fails or no content returned.
    """
    server = get_server("github")

    result = await call_tool(
        server,
        "get_file_contents",
        {
            "owner": owner,
            "repo": repo,
            "path": path,
            "ref": ref,
        },
    )

    logger.info(f"Fetched {owner}/{repo}/{path}@{ref} ({len(result)} chars)")
    return result


async def list_directory(
    owner: str,
    repo: str,
    path: str = "",
    ref: str = "main",
) -> str:
    """List contents of a directory in a GitHub repository via MCP.

    Returns the MCP response (typically a listing of files and directories).
    """
    server = get_server("github")

    result = await call_tool(
        server,
        "list_directory",
        {
            "owner": owner,
            "repo": repo,
            "path": path,
            "ref": ref,
        },
    )

    logger.info(f"Listed {owner}/{repo}/{path or '/'}@{ref}")
    return result


async def get_repo_metadata(owner: str, repo: str) -> str:
    """Fetch repository metadata (description, language, etc.) via MCP."""
    server = get_server("github")

    result = await call_tool(
        server,
        "get_repo",
        {"owner": owner, "repo": repo},
    )

    logger.info(f"Got metadata for {owner}/{repo}")
    return result


async def get_repo_readme(
    owner: str,
    repo: str,
    ref: str = "main",
) -> str:
    """Fetch README from a GitHub repository via MCP.

    Tries README.md first, then readme.md.

    Raises:
        ValueError: If no README found.
    """
    for path in ("README.md", "readme.md"):
        try:
            return await get_file_contents(owner, repo, path, ref)
        except ValueError:
            continue
    raise ValueError(f"No README found in {owner}/{repo}@{ref}")


def parse_github_url(url: str) -> dict | None:
    """Parse a GitHub URL into components with a type discriminator.

    Handles:
    - github.com/owner/repo/blob/ref/path  → type: "file"
    - raw.githubusercontent.com/owner/repo/ref/path  → type: "file"
    - github.com/owner/repo  → type: "repo"
    - github.com/owner/repo/tree/ref  → type: "repo"

    Returns:
        Dict with type + owner/repo/ref (and path for files). None if not GitHub.
    """
    # File URL: github.com/owner/repo/blob/ref/path
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)", url
    )
    if m:
        return {
            "type": "file",
            "owner": m.group(1),
            "repo": m.group(2),
            "ref": m.group(3),
            "path": m.group(4),
        }

    # Raw file URL: raw.githubusercontent.com/owner/repo/ref/path
    m = re.match(
        r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)",
        url,
    )
    if m:
        return {
            "type": "file",
            "owner": m.group(1),
            "repo": m.group(2),
            "ref": m.group(3),
            "path": m.group(4),
        }

    # Repo root or tree URL: github.com/owner/repo[/tree/ref]
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+?)(?:/tree/([^/]+))?/?$", url
    )
    if m:
        return {
            "type": "repo",
            "owner": m.group(1),
            "repo": m.group(2),
            "ref": m.group(3) or "main",
        }

    return None
