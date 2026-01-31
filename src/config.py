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
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    openai_chat_model: str = Field(default="gpt-4o-mini")

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
