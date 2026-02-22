"""Configuration management for the AION-AINSTEIN RAG system."""

from pathlib import Path
from typing import Literal, Optional

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
    openai_base_url: Optional[str] = Field(default=None)
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    openai_chat_model: str = Field(default="gpt-5.2")

    # Per-component LLM overrides (None = use global llm_provider / model).
    # Allows Persona and Tree to use different providers, e.g. Persona on
    # GitHub Models (fast, 8K limit OK) and Tree on Ollama (local, no limit).
    persona_provider: Optional[Literal["openai", "ollama"]] = Field(default=None)
    persona_model: Optional[str] = Field(default=None)
    tree_provider: Optional[Literal["openai", "ollama"]] = Field(default=None)
    tree_model: Optional[str] = Field(default=None)

    # Separate Weaviate vectorizer key. Weaviate's text2vec-openai module
    # needs a real OpenAI API key — not a GitHub PAT or Azure token.
    # If None, falls back to openai_api_key.
    weaviate_openai_api_key: Optional[str] = Field(default=None)

    def get_openai_client_kwargs(self) -> dict:
        """Build kwargs for OpenAI() client — supports custom base_url for GitHub Models."""
        kwargs = {"api_key": self.openai_api_key}
        if self.openai_base_url:
            kwargs["base_url"] = self.openai_base_url
        return kwargs

    # --- Per-component resolved settings ---
    # These resolve per-component overrides to global defaults when not set.

    @property
    def effective_persona_provider(self) -> str:
        return self.persona_provider or self.llm_provider

    @property
    def effective_persona_model(self) -> str:
        if self.persona_model:
            return self.persona_model
        if self.effective_persona_provider == "ollama":
            return self.ollama_model
        return self.openai_chat_model

    @property
    def effective_tree_provider(self) -> str:
        return self.tree_provider or self.llm_provider

    @property
    def effective_tree_model(self) -> str:
        if self.tree_model:
            return self.tree_model
        if self.effective_tree_provider == "ollama":
            return self.ollama_model
        return self.openai_chat_model

    @property
    def effective_weaviate_openai_api_key(self) -> Optional[str]:
        return self.weaviate_openai_api_key or self.openai_api_key

    # --- Global convenience properties ---

    @property
    def chat_model(self) -> str:
        """Get the current chat model based on global provider."""
        if self.llm_provider == "ollama":
            return self.ollama_model
        return self.openai_chat_model

    @property
    def embedding_model(self) -> str:
        """Get the current embedding model based on global provider."""
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
