"""Configuration management for the AInstein RAG system."""

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Supported LLM providers — three distinct services.
PROVIDER_TYPE = Literal["ollama", "github_models", "openai"]


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

    # SKOSMOS Configuration
    skosmos_url: str = Field(default="http://localhost:8080")

    # LLM Provider Configuration
    llm_provider: PROVIDER_TYPE = Field(default="openai")

    # --- Ollama (Local) ---
    ollama_url: str = Field(default="http://localhost:11434")
    # URL for Weaviate (Docker) to reach Ollama on host machine
    ollama_docker_url: str = Field(default="http://host.docker.internal:11434")
    ollama_model: str = Field(default="gpt-oss:20b")
    ollama_embedding_model: str = Field(default="nomic-embed-text-v2-moe")

    # --- GitHub Models (Free, 8K token limit) ---
    github_models_api_key: Optional[str] = Field(default=None)
    github_models_model: str = Field(default="openai/gpt-4.1")

    # --- OpenAI (Pay-per-token) ---
    openai_api_key: Optional[str] = Field(default=None)
    openai_chat_model: str = Field(default="gpt-5.2")
    openai_embedding_model: str = Field(default="text-embedding-3-large")

    # Per-component LLM overrides (None = use global llm_provider / model).
    persona_provider: Optional[PROVIDER_TYPE] = Field(default=None)
    persona_model: Optional[str] = Field(default=None)
    tree_provider: Optional[PROVIDER_TYPE] = Field(default=None)
    tree_model: Optional[str] = Field(default=None)

    def get_openai_client_kwargs(self, provider: str = None) -> dict:
        """Build kwargs for OpenAI() client based on provider.

        Each provider has its own API key and base URL. No cross-fallback
        between keys — a missing key is a validation error, not a silent
        fallback to the wrong service.
        """
        provider = provider or self.llm_provider
        if provider == "github_models":
            return {
                "api_key": self.github_models_api_key,
                "base_url": "https://models.github.ai/inference",
            }
        if provider == "openai":
            return {"api_key": self.openai_api_key}
        raise ValueError(f"Not an OpenAI-compatible provider: {provider}")

    # --- Per-component resolved settings ---

    @property
    def effective_persona_provider(self) -> str:
        return self.persona_provider or self.llm_provider

    @property
    def effective_persona_model(self) -> str:
        if self.persona_model:
            return self.persona_model
        return self._default_model_for(self.effective_persona_provider)

    @property
    def effective_tree_provider(self) -> str:
        return self.tree_provider or self.llm_provider

    @property
    def effective_tree_model(self) -> str:
        if self.tree_model:
            return self.tree_model
        return self._default_model_for(self.effective_tree_provider)

    def _default_model_for(self, provider: str) -> str:
        """Return the default model for a given provider."""
        if provider == "ollama":
            return self.ollama_model
        if provider == "github_models":
            return self.github_models_model
        return self.openai_chat_model

    # --- Global convenience properties ---

    @property
    def chat_model(self) -> str:
        """Get the current chat model based on global provider."""
        return self._default_model_for(self.llm_provider)

    @property
    def embedding_model(self) -> str:
        """Get the current embedding model based on global provider."""
        if self.llm_provider == "ollama":
            return self.ollama_embedding_model
        return self.openai_embedding_model

    # Data Paths
    data_path: Path = Field(default=Path("./data"))
    markdown_path: Path = Field(default=Path("./data/esa-main-artifacts/doc"))
    policy_path: Path = Field(default=Path("./data/do-artifacts/policy_docs"))
    corporate_policy_path: Path = Field(default=Path("./data/general-artifacts/policies"))
    principles_path: Path = Field(default=Path("./data/esa-main-artifacts/doc/principles"))

    # Logging
    log_level: str = Field(default="INFO")

    # Hybrid Search Alpha Configuration
    # Alpha controls balance between keyword (BM25) and vector search
    # 0.0 = 100% keyword, 1.0 = 100% vector, 0.5 = balanced
    alpha_default: float = Field(default=0.5, description="Default alpha for general queries")
    alpha_vocabulary: float = Field(default=0.6, description="Alpha for vocabulary/concept queries (favor semantic)")
    alpha_exact_match: float = Field(default=0.3, description="Alpha for exact term matching (favor keyword)")
    alpha_semantic: float = Field(default=0.7, description="Alpha for semantic/conceptual queries (favor vector)")

    @property
    def project_root(self) -> Path:
        """Get the project root directory."""
        return Path(__file__).parent.parent.parent

    def resolve_path(self, path: Path) -> Path:
        """Resolve a path relative to the project root."""
        if path.is_absolute():
            return path
        return self.project_root / path

    def validate_startup(self) -> list[str]:
        """Validate configuration at startup. Returns list of error messages."""
        errors = []

        # Check API keys per provider — no cross-fallback
        providers_in_use = {
            self.effective_persona_provider,
            self.effective_tree_provider,
        }

        if "github_models" in providers_in_use and not self.github_models_api_key:
            errors.append(
                "GITHUB_MODELS_API_KEY required when persona or tree "
                "provider is 'github_models'"
            )

        if "openai" in providers_in_use and not self.openai_api_key:
            errors.append(
                "OPENAI_API_KEY required when persona or tree "
                "provider is 'openai'"
            )

        if self.persona_model and not self.persona_provider:
            errors.append("PERSONA_MODEL set without PERSONA_PROVIDER")
        if self.tree_model and not self.tree_provider:
            errors.append("TREE_MODEL set without TREE_PROVIDER")

        return errors


# Global settings instance
settings = Settings()
