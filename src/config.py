"""Configuration management for the AION-AINSTEIN RAG system."""

from pathlib import Path
from typing import Optional

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

    # OpenAI Configuration
    openai_api_key: Optional[str] = Field(default=None)
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    openai_chat_model: str = Field(default="gpt-4o-mini")

    # Data Paths
    data_path: Path = Field(default=Path("./data"))
    rdf_path: Path = Field(default=Path("./data/esa-skosmos"))
    markdown_path: Path = Field(default=Path("./data/esa-main-artifacts/doc"))
    policy_path: Path = Field(default=Path("./data/do-artifacts/policy_docs"))
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
