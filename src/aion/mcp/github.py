"""GitHub MCP integration for AInstein.

Provides file retrieval and URL parsing for the inspect pipeline.
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


def parse_github_url(url: str) -> dict | None:
    """Parse a GitHub URL into owner, repo, path, ref.

    Handles:
    - github.com/owner/repo/blob/ref/path/to/file
    - raw.githubusercontent.com/owner/repo/ref/path/to/file

    Returns:
        Dict with owner, repo, path, ref. None if not a file URL.
    """
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)", url
    )
    if m:
        return {
            "owner": m.group(1),
            "repo": m.group(2),
            "ref": m.group(3),
            "path": m.group(4),
        }

    m = re.match(
        r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)",
        url,
    )
    if m:
        return {
            "owner": m.group(1),
            "repo": m.group(2),
            "ref": m.group(3),
            "path": m.group(4),
        }

    return None
