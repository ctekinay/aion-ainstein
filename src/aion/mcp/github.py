"""GitHub MCP integration for AInstein.

Provides file retrieval, URL parsing, and repo browsing for the inspect pipeline.
Uses the remote GitHub MCP server at api.githubcopilot.com.
"""

import logging
import re

from aion.config import settings

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

    Uses get_file_contents which returns a directory listing when called
    on a directory path.
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

    logger.info(f"Listed {owner}/{repo}/{path or '/'}@{ref}")
    return result


async def get_repo_metadata(owner: str, repo: str) -> str:
    """Fetch repository metadata via GitHub REST API.

    Returns a formatted text summary with description, language, topics,
    stars, and default_branch. Used by the generation pipeline to provide
    repo context to the LLM.
    """
    import os

    import httpx

    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=settings.timeout_github_api) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}", headers=headers
        )
        resp.raise_for_status()
        data = resp.json()

    parts = []
    if data.get("description"):
        parts.append(f"Description: {data['description']}")
    if data.get("language"):
        parts.append(f"Language: {data['language']}")
    if data.get("topics"):
        parts.append(f"Topics: {', '.join(data['topics'])}")
    if data.get("stargazers_count"):
        parts.append(f"Stars: {data['stargazers_count']}")
    if data.get("default_branch"):
        parts.append(f"Default branch: {data['default_branch']}")

    logger.info(f"Got metadata for {owner}/{repo}")
    return "\n".join(parts)


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


async def get_org_overview(owner: str) -> str:
    """Fetch organization/user overview via GitHub REST API.

    MCP repos toolset has no org-level tools, so we hit the API directly.
    Tries /orgs/{owner} first, falls back to /users/{owner}.
    Returns a text summary of profile + top repositories.
    """
    import os

    import httpx

    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=settings.timeout_github_api) as client:
        # Try org first, fall back to user
        org_resp = await client.get(
            f"https://api.github.com/orgs/{owner}", headers=headers
        )
        if org_resp.status_code == 200:
            profile = org_resp.json()
            entity_type = "organization"
            repos_url = f"https://api.github.com/orgs/{owner}/repos"
        else:
            user_resp = await client.get(
                f"https://api.github.com/users/{owner}", headers=headers
            )
            user_resp.raise_for_status()
            profile = user_resp.json()
            entity_type = "user"
            repos_url = f"https://api.github.com/users/{owner}/repos"

        # Fetch top repos by stars
        repos_resp = await client.get(
            repos_url,
            headers=headers,
            params={"sort": "stars", "per_page": 15, "direction": "desc"},
        )
        repos = repos_resp.json() if repos_resp.status_code == 200 else []

    # Assemble text summary
    parts = [f"GITHUB {entity_type.upper()}: {profile.get('login', owner)}"]
    if profile.get("name"):
        parts.append(f"Name: {profile['name']}")
    if profile.get("description") or profile.get("bio"):
        parts.append(f"Description: {profile.get('description') or profile.get('bio')}")
    if profile.get("blog"):
        parts.append(f"Website: {profile['blog']}")
    if profile.get("public_repos"):
        parts.append(f"Public repositories: {profile['public_repos']}")

    if repos:
        parts.append("\nTOP REPOSITORIES:")
        for r in repos:
            stars = r.get("stargazers_count", 0)
            desc = r.get("description", "") or ""
            lang = r.get("language", "") or ""
            line = f"- {r['name']}"
            if lang:
                line += f" [{lang}]"
            if stars:
                line += f" ({stars} stars)"
            if desc:
                line += f" — {desc}"
            parts.append(line)

    logger.info(f"Got {entity_type} overview for {owner} ({len(repos)} repos)")
    return "\n".join(parts)


def parse_github_url(url: str) -> dict | None:
    """Parse a GitHub URL into components with a type discriminator.

    Handles:
    - github.com/owner/repo/blob/ref/path  → type: "file"
    - raw.githubusercontent.com/owner/repo/ref/path  → type: "file"
    - github.com/owner/repo  → type: "repo"
    - github.com/owner/repo/tree/ref  → type: "repo"
    - github.com/name  → type: "org" (org or user profile)

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

    # Org/user URL: github.com/name (single path segment)
    m = re.match(r"https?://github\.com/([^/]+)/?$", url)
    if m:
        return {
            "type": "org",
            "owner": m.group(1),
        }

    return None
