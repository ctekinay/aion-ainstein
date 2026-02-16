"""Configuration management for the AION-AINSTEIN RAG system."""

import copy
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Literal, Optional, TYPE_CHECKING

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Weaviate Configuration
    weaviate_url: str = Field(default="http://localhost:8080")
    weaviate_grpc_url: str = Field(default="localhost:50051")
    weaviate_is_local: bool = Field(default=True)
    wcd_url: Optional[str] = Field(default=None)
    wcd_api_key: Optional[str] = Field(default=None)

    # LLM Provider Configuration
    llm_provider: Literal["openai", "ollama"] = Field(default="ollama")

    # Ollama Configuration (default provider)
    ollama_url: str = Field(default="http://localhost:11434")
    # URL for Weaviate (Docker) to reach Ollama on host machine
    ollama_docker_url: str = Field(default="http://host.docker.internal:11434")
    ollama_model: str = Field(default="gpt-oss:20b")# Alternative: qwen3:14b, alibayram/smollm3:latest (lighter)
    ollama_embedding_model: str = Field(default="nomic-embed-text-v2-moe")

    # OpenAI Configuration (fallback/alternative)
    openai_api_key: Optional[str] = Field(default=None)
    openai_embedding_model: str = Field(default="text-embedding-3-large")
    openai_chat_model: str = Field(default="gpt-5.2")

    @property
    def chat_model(self) -> str:
        """Get the current chat model based on provider."""
        if self.llm_provider == "ollama":
            return self.ollama_model
        return self.openai_chat_model

    @property
    def embedding_model(self) -> str:
        """Get the current embedding model based on provider."""
        if self.llm_provider == "ollama":
            return self.ollama_embedding_model
        return self.openai_embedding_model

    # Data Paths
    data_path: Path = Field(default=Path("./data"))
    rdf_path: Path = Field(default=Path("./data/esa-skosmos"))
    markdown_path: Path = Field(default=Path("./data/esa-main-artifacts/doc"))
    policy_path: Path = Field(default=Path("./data/do-artifacts/policy_docs"))
    general_policy_path: Path = Field(default=Path("./data/general-artifacts/policies"))
    principles_path: Path = Field(default=Path("./data/do-artifacts/principles"))

    # Logging
    log_level: str = Field(default="INFO")

    # Hybrid Search Alpha Configuration
    # Alpha controls balance between keyword (BM25) and vector search
    # 0.0 = 100% keyword, 1.0 = 100% vector, 0.5 = balanced
    alpha_default: float = Field(default=0.5, description="Default alpha for general queries")
    alpha_vocabulary: float = Field(default=0.6, description="Alpha for vocabulary/concept queries (favor semantic)")
    alpha_exact_match: float = Field(default=0.3, description="Alpha for exact term matching (favor keyword)")
    alpha_semantic: float = Field(default=0.7, description="Alpha for semantic/conceptual queries (favor vector)")

    # Elysia Concurrency Configuration
    # Controls thread pool usage for blocking Elysia Tree calls
    max_concurrent_elysia_calls: int = Field(
        default=4,
        description="Maximum concurrent Elysia Tree calls (prevents thread explosion under load)"
    )
    elysia_query_timeout_seconds: float = Field(
        default=120.0,
        description="Timeout for Elysia Tree queries in seconds"
    )

    # ==========================================================================
    # Fallback Filter Guardrails
    # ==========================================================================
    # When doc_type metadata is missing, the system can fall back to in-memory
    # filtering. These guardrails prevent runaway scans and provide observability.

    enable_inmemory_filter_fallback: bool = Field(
        default=True,
        description=(
            "Enable in-memory fallback filtering when doc_type is missing. "
            "Set to False in production once migration is complete."
        )
    )
    max_fallback_scan_docs: int = Field(
        default=2000,
        description=(
            "Maximum documents to scan in fallback mode. "
            "If collection exceeds this, return controlled error instead of scanning."
        )
    )
    environment: Literal["local", "dev", "staging", "prod"] = Field(
        default="local",
        description="Deployment environment for conditional behavior"
    )

    # AInstein Identity Configuration
    ainstein_disclosure_level: int = Field(
        default=0,
        description=(
            "Controls detail in meta responses and identity filtering. "
            "0=functional (default), 1=power-user (RAG details), "
            "2=debug (full internals: Elysia, Weaviate, DSPy)"
        )
    )

    # ==========================================================================
    # SKOSMOS Terminology Verification Configuration
    # ==========================================================================
    # Local-first approach: vocabulary is loaded from TTL files at startup.
    # API is optional, only called when local lookup misses.
    # ABSTAIN applies only when term cannot be verified (local miss + API miss/fail).

    skosmos_mode: Literal["local", "api", "hybrid"] = Field(
        default="hybrid",
        description=(
            "SKOSMOS verification mode: "
            "'local' = only use local TTL files, "
            "'api' = only use SKOSMOS API, "
            "'hybrid' = local-first with API fallback (recommended)"
        )
    )
    skosmos_data_path: Path = Field(
        default=Path("./data/esa-skosmos"),
        description="Path to directory containing SKOSMOS TTL vocabulary files"
    )
    skosmos_api_url: Optional[str] = Field(
        default=None,
        description="Optional SKOSMOS API URL for hybrid/api mode (e.g., https://skosmos.example.com/rest/v1)"
    )
    skosmos_api_timeout_seconds: float = Field(
        default=5.0,
        description="Timeout for SKOSMOS API calls in seconds"
    )
    skosmos_cache_ttl_seconds: int = Field(
        default=3600,
        description="TTL for SKOSMOS API response cache in seconds (1 hour default)"
    )
    skosmos_lazy_load: bool = Field(
        default=False,
        description="If True, load vocabularies lazily on first lookup. If False, load at startup."
    )

    # ==========================================================================
    # Taxonomy & Portability Configuration
    # ==========================================================================

    mode: Literal["esa_strict", "portable"] = Field(
        default="esa_strict",
        description=(
            "Operating mode: 'esa_strict' fails fast on unknown doc_types at "
            "ingestion. 'portable' ingests unknowns as 'unknown', excludes from "
            "default retrieval."
        )
    )

    # Collection name overrides (env vars take priority over YAML)
    collection_vocabulary: Optional[str] = Field(
        default=None,
        description="Override vocabulary collection name (env: COLLECTION_VOCABULARY)"
    )
    collection_adr: Optional[str] = Field(
        default=None,
        description="Override ADR collection name (env: COLLECTION_ADR)"
    )
    collection_principle: Optional[str] = Field(
        default=None,
        description="Override principle collection name (env: COLLECTION_PRINCIPLE)"
    )
    collection_policy: Optional[str] = Field(
        default=None,
        description="Override policy collection name (env: COLLECTION_POLICY)"
    )

    # Config file paths
    taxonomy_config_path: Path = Field(
        default=Path("config/taxonomy.default.yaml"),
        description="Path to platform-default taxonomy config"
    )
    taxonomy_override_path: Path = Field(
        default=Path("data/esa-main-artifacts/config/taxonomy.yaml"),
        description="Path to ESA-specific taxonomy override"
    )
    corpus_expectations_path: Path = Field(
        default=Path("config/corpus_expectations.yaml"),
        description="Path to corpus-specific verification expectations"
    )
    routing_policy_path: Path = Field(
        default=Path("config/routing_policy.yaml"),
        description="Path to routing policy config"
    )

    # ==========================================================================
    # Routing Policy Feature Flags
    # ==========================================================================
    # Environment variable overrides for routing_policy.yaml flags.
    # Env vars take precedence over YAML values.

    ainstein_intent_router: Optional[bool] = Field(
        default=None,
        description="Override intent_router_enabled (env: AINSTEIN_INTENT_ROUTER)"
    )
    ainstein_intent_router_mode: Optional[str] = Field(
        default=None,
        description="Override intent_router_mode: heuristic|llm (env: AINSTEIN_INTENT_ROUTER_MODE)"
    )
    ainstein_followup_binding: Optional[bool] = Field(
        default=None,
        description="Override followup_binding_enabled (env: AINSTEIN_FOLLOWUP_BINDING)"
    )
    ainstein_abstain_gate: Optional[bool] = Field(
        default=None,
        description="Override abstain_gate_enabled (env: AINSTEIN_ABSTAIN_GATE)"
    )
    ainstein_tree_enabled: Optional[bool] = Field(
        default=None,
        description="Override tree_enabled (env: AINSTEIN_TREE_ENABLED)"
    )
    ainstein_debug_headers: Optional[bool] = Field(
        default=None,
        description="Override debug_headers_enabled (env: AINSTEIN_DEBUG_HEADERS)"
    )
    ainstein_embed_mode: Optional[str] = Field(
        default=None,
        description="Embed mode: chunked|full|both (env: AINSTEIN_EMBED_MODE)"
    )

    @property
    def project_root(self) -> Path:
        """Get the project root directory."""
        return Path(__file__).parent.parent

    def resolve_path(self, path: Path) -> Path:
        """Resolve a path relative to the project root."""
        if path.is_absolute():
            return path
        return self.project_root / path

    def get_taxonomy_config(self) -> Dict[str, Any]:
        """Load taxonomy config with two-layer merge + caching.

        Precedence: env vars > ESA override YAML > platform default YAML > hardcoded defaults.
        """
        return _load_taxonomy_config(
            str(self.resolve_path(self.taxonomy_config_path)),
            str(self.resolve_path(self.taxonomy_override_path)),
        )

    def get_collection_names(self) -> Dict[str, str]:
        """Get collection names with full precedence chain.

        Precedence: env vars > ESA override YAML > platform default YAML > hardcoded defaults.
        """
        hardcoded = {
            "vocabulary": "Vocabulary",
            "adr": "ArchitecturalDecision",
            "principle": "Principle",
            "policy": "PolicyDocument",
        }

        # Layer 1: YAML config (platform default + ESA override already merged)
        taxonomy = self.get_taxonomy_config()
        yaml_collections = taxonomy.get("collections", {})
        result = {**hardcoded, **yaml_collections}

        # Layer 2: env var overrides
        env_overrides = {
            "vocabulary": self.collection_vocabulary,
            "adr": self.collection_adr,
            "principle": self.collection_principle,
            "policy": self.collection_policy,
        }
        for key, value in env_overrides.items():
            if value is not None:
                result[key] = value

        return result

    def get_corpus_expectations(self) -> Dict[str, Any]:
        """Load corpus expectations config with caching."""
        return _load_corpus_expectations(
            str(self.resolve_path(self.corpus_expectations_path))
        )

    def get_routing_policy(self) -> Dict[str, Any]:
        """Load routing policy with env var overrides.

        Precedence: env vars (AINSTEIN_*) > routing_policy.yaml > hardcoded defaults.
        """
        policy = _load_routing_policy(
            str(self.resolve_path(self.routing_policy_path))
        )

        # Apply env var overrides
        overrides = {
            "intent_router_enabled": self.ainstein_intent_router,
            "intent_router_mode": self.ainstein_intent_router_mode,
            "followup_binding_enabled": self.ainstein_followup_binding,
            "abstain_gate_enabled": self.ainstein_abstain_gate,
            "tree_enabled": self.ainstein_tree_enabled,
            "debug_headers_enabled": self.ainstein_debug_headers,
        }
        for key, value in overrides.items():
            if value is not None:
                policy[key] = value

        return policy


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge override into base (non-destructive). Override wins for scalars/lists."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


@lru_cache(maxsize=1)
def _load_taxonomy_config(default_path: str, override_path: str) -> Dict[str, Any]:
    """Load and merge taxonomy YAML files. Cached after first call."""
    config: Dict[str, Any] = {}
    sources: Dict[str, str] = {}

    # Layer 1: platform defaults
    default_file = Path(default_path)
    if default_file.exists():
        with open(default_file) as f:
            loaded = yaml.safe_load(f) or {}
        config = loaded
        sources["platform_default"] = str(default_file)
        logger.debug("Loaded platform default taxonomy from %s", default_file)
    else:
        logger.debug("No platform default taxonomy at %s, using hardcoded defaults", default_file)

    # Layer 2: ESA override (deep-merged on top)
    override_file = Path(override_path)
    if override_file.exists():
        with open(override_file) as f:
            override = yaml.safe_load(f) or {}
        config = _deep_merge(config, override)
        sources["esa_override"] = str(override_file)
        logger.debug("Merged ESA override taxonomy from %s", override_file)

    # DEBUG: full provenance map
    logger.debug("Taxonomy config sources: %s", sources)
    logger.debug("Taxonomy config keys: %s", list(config.keys()))

    # INFO: one-line summary
    mode = config.get("mode", "esa_strict")
    embed_profile = config.get("embedding", {}).get("profile", "local")
    collections = config.get("collections", {})
    collection_summary = ", ".join(f"{k}={v}" for k, v in collections.items())
    logger.info(
        "Taxonomy config loaded: mode=%s, embedding=%s, collections=[%s]",
        mode, embed_profile, collection_summary,
    )

    return config


@lru_cache(maxsize=1)
def _load_corpus_expectations(path: str) -> Dict[str, Any]:
    """Load corpus expectations YAML. Cached after first call."""
    expectations_file = Path(path)
    if expectations_file.exists():
        with open(expectations_file) as f:
            loaded = yaml.safe_load(f) or {}
        logger.debug("Loaded corpus expectations from %s", expectations_file)
        return loaded
    logger.debug("No corpus expectations at %s, returning empty", expectations_file)
    return {}


@lru_cache(maxsize=1)
def _load_routing_policy(path: str) -> Dict[str, Any]:
    """Load routing policy YAML. Cached after first call."""
    # Hardcoded defaults (used if YAML missing)
    defaults: Dict[str, Any] = {
        "intent_router_enabled": False,
        "intent_router_mode": "heuristic",
        "followup_binding_enabled": True,
        "abstain_gate_enabled": True,
        "max_tree_seconds": 120,
        "tree_enabled": True,
        "intent_confidence_threshold": 0.55,
        "debug_headers_enabled": False,
    }
    policy_file = Path(path)
    if policy_file.exists():
        with open(policy_file) as f:
            loaded = yaml.safe_load(f) or {}
        logger.debug("Loaded routing policy from %s", policy_file)
        defaults.update(loaded)
    else:
        logger.debug("No routing policy at %s, using defaults", policy_file)
    return defaults


def invalidate_config_caches() -> None:
    """Clear cached config. Useful for testing or config reload."""
    _load_taxonomy_config.cache_clear()
    _load_corpus_expectations.cache_clear()
    _load_routing_policy.cache_clear()


def save_routing_policy(policy: Dict[str, Any]) -> None:
    """Write routing policy to YAML and invalidate the cache.

    Only writes recognised keys so callers cannot inject arbitrary YAML.
    """
    _KNOWN_KEYS = {
        "intent_router_enabled", "intent_router_mode",
        "followup_binding_enabled",
        "abstain_gate_enabled",
        "max_tree_seconds", "tree_enabled", "intent_confidence_threshold",
        "debug_headers_enabled",
    }
    filtered = {k: v for k, v in policy.items() if k in _KNOWN_KEYS}
    policy_path = Path(settings.resolve_path(settings.routing_policy_path))
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    with open(policy_path, "w") as f:
        yaml.dump(filtered, f, default_flow_style=False, sort_keys=False)
    logger.info("Routing policy saved to %s", policy_path)
    invalidate_config_caches()


# Global settings instance
settings = Settings()
