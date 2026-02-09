"""Configuration management for the AION-AINSTEIN RAG system."""

from pathlib import Path
from typing import Literal, Optional, TYPE_CHECKING

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    ollama_model: str = Field(default="alibayram/smollm3:latest")
    ollama_embedding_model: str = Field(default="nomic-embed-text-v2-moe")

    # OpenAI Configuration (fallback/alternative)
    openai_api_key: Optional[str] = Field(default=None)
    openai_embedding_model: str = Field(default="text-embedding-3-small")
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

    @property
    def project_root(self) -> Path:
        """Get the project root directory."""
        return Path(__file__).parent.parent

    def resolve_path(self, path: Path) -> Path:
        """Resolve a path relative to the project root."""
        if path.is_absolute():
            return path
        return self.project_root / path


# Global settings instance
settings = Settings()
