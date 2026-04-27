"""MCP server registry.

Loads server configurations from config.yaml and provides
access to connection parameters by server name.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class MCPServerConfig:
    name: str
    url: str
    transport: str          # "http" or "stdio"
    auth_type: str          # "bearer" or "none"
    auth_env_var: str       # env var name for the token
    headers: dict = field(default_factory=dict)
    read_only: bool = False

    @property
    def token(self) -> str | None:
        if self.auth_env_var:
            return os.environ.get(self.auth_env_var)
        return None

    @property
    def auth_headers(self) -> dict:
        h = dict(self.headers)
        if self.auth_type == "bearer" and self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h


_CONFIG_PATH = Path(__file__).parent / "config.yaml"
_servers: dict[str, MCPServerConfig] = {}


def load_registry() -> dict[str, MCPServerConfig]:
    """Load MCP server configs from config.yaml."""
    global _servers
    with open(_CONFIG_PATH) as f:
        raw = yaml.safe_load(f)

    for name, cfg in raw.get("servers", {}).items():
        auth = cfg.get("auth", {})
        _servers[name] = MCPServerConfig(
            name=name,
            url=cfg["url"],
            transport=cfg.get("transport", "http"),
            auth_type=auth.get("type", "none"),
            auth_env_var=auth.get("env_var", ""),
            headers=cfg.get("headers", {}),
            read_only=cfg.get("read_only", False),
        )
    return _servers


def get_server(name: str) -> MCPServerConfig:
    """Get a server config by name. Raises KeyError if not found."""
    if not _servers:
        load_registry()
    return _servers[name]
