"""Configuration management for the AInstein RAG system."""

import json
import logging
import os
from pathlib import Path
from typing import Literal

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Supported LLM providers — three distinct services.
PROVIDER_TYPE = Literal["ollama", "github_models", "openai"]

# User settings persistence — survives server restarts.
# Only LLM provider/model preferences are stored here.
# API keys should NEVER be persisted in this file — use .env for secrets.
_USER_SETTINGS_FILE = Path.home() / ".ainstein" / "settings.json"

# Fields that are safe to persist (no secrets, no paths, no API keys).
_PERSISTABLE_FIELDS = (
    "llm_provider", "ollama_model", "openai_chat_model",
    "github_models_model", "persona_provider", "persona_model",
    "rag_provider", "rag_model", "embedding_provider",
)


def _load_user_settings() -> dict:
    """Load persisted user settings from ~/.ainstein/settings.json."""
    # Clean up stale .tmp files from crashed saves
    if _USER_SETTINGS_FILE.parent.is_dir():
        for stale in _USER_SETTINGS_FILE.parent.glob("settings.*.tmp"):
            try:
                stale.unlink()
            except OSError:
                pass
    if _USER_SETTINGS_FILE.exists():
        try:
            return json.loads(_USER_SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load user settings: %s", e)
    return {}


def _save_user_settings(data: dict) -> None:
    """Persist user settings to ~/.ainstein/settings.json.

    Uses atomic write (temp file + rename) so concurrent saves cannot
    produce a half-written file that corrupts the next load.
    """
    try:
        _USER_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _USER_SETTINGS_FILE.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(_USER_SETTINGS_FILE)
    except OSError as e:
        logger.warning("Could not save user settings: %s", e)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Weaviate Configuration
    weaviate_url: str = Field(default="http://localhost:8090")
    weaviate_grpc_url: str = Field(default="localhost:50061")
    weaviate_is_local: bool = Field(default=True)
    wcd_url: str | None = Field(default=None)
    wcd_api_key: str | None = Field(default=None)

    # SKOSMOS Configuration
    skosmos_url: str = Field(default="http://localhost:8080")

    # Pixel Agents (VSCode extension visualization)
    pixel_agents_dir: str | None = Field(default=None)

    # LLM Provider Configuration
    llm_provider: PROVIDER_TYPE = Field(default="openai")

    # --- Ollama (Local) ---
    ollama_url: str = Field(default="http://localhost:11434")
    # URL for Weaviate (Docker) to reach Ollama on host machine
    ollama_docker_url: str = Field(default="http://host.docker.internal:11434")
    ollama_model: str = Field(default="qwen3.5:35b-a3b")
    ollama_embedding_model: str = Field(default="nomic-embed-text-v2-moe")

    # --- GitHub Models (Free, 8K token limit) ---
    github_models_api_key: str | None = Field(default=None)
    github_models_model: str = Field(default="openai/gpt-4.1")

    # --- OpenAI (Pay-per-token) ---
    openai_api_key: str | None = Field(default=None)
    openai_chat_model: str = Field(default="gpt-5.2")
    openai_embedding_model: str = Field(default="text-embedding-3-large")

    # Per-component LLM overrides (None = use global llm_provider / model).
    persona_provider: PROVIDER_TYPE | None = Field(default=None)
    persona_model: str | None = Field(default=None)
    rag_provider: PROVIDER_TYPE | None = Field(default=None)
    rag_model: str | None = Field(default=None)
    embedding_provider: PROVIDER_TYPE | None = Field(default=None)

    def apply_user_overrides(self) -> None:
        """Apply persisted user settings (from ~/.ainstein/settings.json) over env defaults.

        Called once at startup in the lifespan function. Only updates
        fields listed in _PERSISTABLE_FIELDS — never touches API keys or paths.
        Values are validated against field types before applying; invalid
        values are skipped with a warning.
        """
        saved = _load_user_settings()
        if not saved or not isinstance(saved, dict):
            return
        # Provider fields accept these values (or None for optional fields).
        _valid_providers = {"ollama", "github_models", "openai"}
        _provider_fields = {
            "llm_provider", "persona_provider", "rag_provider", "embedding_provider",
        }
        applied = []
        for field_name in _PERSISTABLE_FIELDS:
            if field_name not in saved:
                continue
            value = saved[field_name]
            # Validate provider fields against the allowed literal values.
            if field_name in _provider_fields:
                if value is not None and value not in _valid_providers:
                    logger.warning(
                        "Ignoring invalid persisted value for %s: %r", field_name, value,
                    )
                    continue
            # Model name fields must be strings (or None for optional).
            elif not isinstance(value, (str, type(None))):
                logger.warning(
                    "Ignoring invalid persisted value for %s: %r", field_name, value,
                )
                continue
            setattr(self, field_name, value)
            applied.append(field_name)
        if applied:
            logger.info("Applied persisted user settings: %s", ", ".join(applied))

    def get_openai_client_kwargs(self, provider: str = None, *, timeout: float | None = None) -> dict:
        """Build kwargs for OpenAI() client based on provider.

        Each provider has its own API key and base URL. No cross-fallback
        between keys — a missing key is a validation error, not a silent
        fallback to the wrong service.

        Args:
            timeout: Read timeout in seconds. Each caller should pass
                     the appropriate settings.timeout_* value for its
                     use case. Falls back to settings.timeout_openai_default.
        """
        provider = provider or self.llm_provider
        effective_timeout = timeout if timeout is not None else self.timeout_openai_default
        base = {
            "max_retries": self.openai_max_retries,
            "timeout": httpx.Timeout(effective_timeout, connect=10.0),
        }
        if provider == "github_models":
            return {
                **base,
                "api_key": self.github_models_api_key,
                "base_url": "https://models.github.ai/inference",
            }
        if provider == "openai":
            return {**base, "api_key": self.openai_api_key}
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
    def effective_rag_provider(self) -> str:
        return self.rag_provider or self.llm_provider

    @property
    def effective_rag_model(self) -> str:
        if self.rag_model:
            return self.rag_model
        return self._default_model_for(self.effective_rag_provider)

    @property
    def effective_embedding_provider(self) -> str:
        return self.embedding_provider or self.llm_provider

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
        """Get the current embedding model based on embedding provider.

        Note: if effective_embedding_provider is 'github_models', this returns
        openai_embedding_model. The factory in embeddings.py raises before
        that value is ever used (GitHub Models has no embedding endpoint).
        """
        if self.effective_embedding_provider == "ollama":
            return self.ollama_embedding_model
        return self.openai_embedding_model

    # --- Pydantic AI model builder ---

    def build_pydantic_ai_model(
        self,
        component: str = "rag",
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ):
        """Build a Pydantic AI model for the given component.

        Args:
            component: "rag" (default) or "persona"
            timeout: Override HTTP read timeout (seconds). Defaults to
                timeout_agent_multi_tool.
            max_retries: Override HTTP client retry count. Defaults to
                openai_max_retries.

        Returns:
            OpenAIChatModel configured for the component's provider.
        """
        from openai import AsyncOpenAI
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        if component == "persona":
            provider = self.effective_persona_provider
            model_name = self.effective_persona_model
        else:
            provider = self.effective_rag_provider
            model_name = self.effective_rag_model

        _timeout = timeout if timeout is not None else self.timeout_agent_multi_tool
        _retries = max_retries if max_retries is not None else self.openai_max_retries

        if provider == "ollama":
            client = AsyncOpenAI(
                base_url=f"{self.ollama_url}/v1",
                api_key="ollama",
                max_retries=_retries,
                timeout=httpx.Timeout(_timeout, connect=10.0),
            )
            return OpenAIChatModel(
                model_name,
                provider=OpenAIProvider(openai_client=client),
            )
        elif provider == "github_models":
            kwargs = self.get_openai_client_kwargs("github_models", timeout=_timeout)
            bare_model = model_name.split("/", 1)[-1] if "/" in model_name else model_name
            client = AsyncOpenAI(
                base_url=kwargs["base_url"],
                api_key=kwargs["api_key"],
                max_retries=_retries,
                timeout=kwargs["timeout"],
            )
            return OpenAIChatModel(
                bare_model,
                provider=OpenAIProvider(openai_client=client),
            )
        else:  # openai
            kwargs = self.get_openai_client_kwargs("openai", timeout=_timeout)
            client = AsyncOpenAI(
                api_key=kwargs["api_key"],
                max_retries=_retries,
                timeout=kwargs["timeout"],
            )
            return OpenAIChatModel(
                model_name,
                provider=OpenAIProvider(openai_client=client),
            )

    # Project root — resolved from config.py's location (src/aion/config.py)
    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent.parent

    @property
    def db_path(self) -> Path:
        """Path to the shared SQLite database (chat history, sessions, registry)."""
        return self.project_root / "chat_history.db"

    # Data Paths
    data_path: Path = Field(default=Path("./data"))
    markdown_path: Path = Field(default=Path("./data/esa-main-artifacts/doc"))
    policy_path: Path = Field(default=Path("./data/do-artifacts/policy_docs"))
    corporate_policy_path: Path = Field(default=Path("./data/general-artifacts/policies"))
    principles_path: Path = Field(default=Path("./data/esa-main-artifacts/doc/principles"))

    # Server
    server_port: int = Field(default=8081)

    # Timeouts (seconds) — configurable via env vars (e.g. TIMEOUT_HEALTH_CHECK=10)
    timeout_health_check: float = Field(default=5.0)
    timeout_llm_call: float = Field(default=30.0)
    timeout_llm_inspect: float = Field(default=120.0)
    timeout_agent_multi_tool: float = Field(default=180.0)
    timeout_long_running: float = Field(default=300.0)
    timeout_generation: float = Field(default=600.0)
    timeout_github_api: float = Field(default=15.0)
    timeout_agent_default: float = Field(default=60.0)
    timeout_openai_default: float = Field(default=60.0)

    # OpenAI client retries — without a cap, the httpx client retries
    # indefinitely (observed: 23 min hang). 2 retries = 3 total attempts.
    openai_max_retries: int = Field(default=2)

    # Subprocess timeouts
    timeout_subprocess_quick: float = Field(default=5.0)
    timeout_subprocess_diff: float = Field(default=30.0)
    timeout_subprocess_clone: float = Field(default=120.0)
    timeout_skosmos: float = Field(default=10.0)

    # Content limits
    max_clone_size_mb: int = Field(default=1024)
    max_readme_chars: int = Field(default=50000)
    min_readme_chars_per_ref: int = Field(default=10000)

    # Embedding retries (application-level, not HTTP-level)
    embedding_max_retries: int = Field(default=3)
    embedding_retry_delay: float = Field(default=5.0)

    # Memory summarizer
    summarize_trigger_count: int = Field(default=4)

    # Logging
    log_level: str = Field(default="INFO")

    # Hybrid Search Alpha Configuration
    # Alpha controls balance between keyword (BM25) and vector search
    # 0.0 = 100% keyword, 1.0 = 100% vector, 0.5 = balanced
    alpha_default: float = Field(default=0.5, description="Default alpha for general queries")
    alpha_vocabulary: float = Field(default=0.6, description="Alpha for vocabulary/concept queries (favor semantic)")
    alpha_exact_match: float = Field(default=0.3, description="Alpha for exact term matching (favor keyword)")
    alpha_semantic: float = Field(default=0.7, description="Alpha for semantic/conceptual queries (favor vector)")

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
            self.effective_rag_provider,
            self.effective_embedding_provider,
        }

        if "github_models" in providers_in_use and not self.github_models_api_key:
            errors.append(
                "GITHUB_MODELS_API_KEY required when persona, rag, or "
                "embedding provider is 'github_models'"
            )

        if "openai" in providers_in_use and not self.openai_api_key:
            errors.append(
                "OPENAI_API_KEY required when persona, rag, or "
                "embedding provider is 'openai'"
            )

        if self.persona_model and not self.persona_provider:
            errors.append("PERSONA_MODEL set without PERSONA_PROVIDER")
        if self.rag_model and not self.rag_provider:
            errors.append("RAG_MODEL set without RAG_PROVIDER")

        return errors


# Global settings instance
settings = Settings()


def is_reasoning_model(model: str) -> bool:
    """Check if a model uses max_completion_tokens instead of max_tokens.

    Reasoning models (e.g. gpt-5.x) consume reasoning tokens within
    max_completion_tokens, so callers need higher limits to leave room
    for both reasoning and visible output.

    Handles publisher-prefixed names like "openai/gpt-5.2".
    """
    base = model.rsplit("/", 1)[-1] if "/" in model else model
    return base.startswith("gpt-5")
