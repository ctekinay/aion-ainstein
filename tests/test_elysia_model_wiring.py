"""Tests for Elysia model configuration wiring.

Verifies that AInstein's --model / --provider settings are correctly
propagated to Elysia's config singleton so the Tree uses the intended
model, not the hardcoded smart_setup() defaults.

Note: elysia.config is mocked in conftest.py (avoids spacy dependency).
These tests verify configure() is called with the correct arguments.
"""

import sys
import pytest
from unittest.mock import MagicMock, call


@pytest.fixture(autouse=True)
def _reset_elysia_wiring():
    """Reset the module-level config state and mock call history."""
    import src.elysia_agents as ea
    ea._elysia_configured = False
    ea._elysia_config_signature = None

    elysia_config = sys.modules.get("elysia.config")
    if elysia_config and hasattr(elysia_config, "settings"):
        elysia_config.settings.configure.reset_mock()
    yield
    ea._elysia_configured = False
    ea._elysia_config_signature = None


class TestConfigureElysiaFromSettings:
    """Verify configure_elysia_from_settings() calls elysia.config.configure() correctly."""

    def test_openai_model_calls_configure_with_replace(self):
        """--provider openai --model gpt-5-mini → configure(replace=True, ...)."""
        from src.config import settings as ainstein_settings
        from src.elysia_agents import configure_elysia_from_settings

        orig_provider = ainstein_settings.llm_provider
        orig_model = ainstein_settings.openai_chat_model
        try:
            ainstein_settings.llm_provider = "openai"
            ainstein_settings.openai_chat_model = "gpt-5-mini"

            configure_elysia_from_settings()

            elysia_config = sys.modules["elysia.config"]
            elysia_config.settings.configure.assert_called_once_with(
                replace=True,
                base_model="gpt-5-mini",
                base_provider="openai",
                complex_model="gpt-5-mini",
                complex_provider="openai",
            )
        finally:
            ainstein_settings.llm_provider = orig_provider
            ainstein_settings.openai_chat_model = orig_model

    def test_ollama_model_calls_configure_with_api_base(self):
        """--provider ollama --model qwen3:14b → configure(..., model_api_base=...)."""
        from src.config import settings as ainstein_settings
        from src.elysia_agents import configure_elysia_from_settings

        orig_provider = ainstein_settings.llm_provider
        orig_model = ainstein_settings.ollama_model
        try:
            ainstein_settings.llm_provider = "ollama"
            ainstein_settings.ollama_model = "qwen3:14b"

            configure_elysia_from_settings()

            elysia_config = sys.modules["elysia.config"]
            elysia_config.settings.configure.assert_called_once_with(
                replace=True,
                base_model="qwen3:14b",
                base_provider="ollama",
                complex_model="qwen3:14b",
                complex_provider="ollama",
                model_api_base=ainstein_settings.ollama_url,
            )
        finally:
            ainstein_settings.llm_provider = orig_provider
            ainstein_settings.ollama_model = orig_model

    def test_openai_gpt52_not_hardcoded_default(self):
        """--model gpt-5.2 must pass 'gpt-5.2' to configure, not 'gpt-4.1-mini'."""
        from src.config import settings as ainstein_settings
        from src.elysia_agents import configure_elysia_from_settings

        orig_provider = ainstein_settings.llm_provider
        orig_model = ainstein_settings.openai_chat_model
        try:
            ainstein_settings.llm_provider = "openai"
            ainstein_settings.openai_chat_model = "gpt-5.2"

            configure_elysia_from_settings()

            elysia_config = sys.modules["elysia.config"]
            args = elysia_config.settings.configure.call_args
            assert args.kwargs["base_model"] == "gpt-5.2"
            assert args.kwargs["base_model"] != "gpt-4.1-mini"
        finally:
            ainstein_settings.llm_provider = orig_provider
            ainstein_settings.openai_chat_model = orig_model

    def test_ollama_gpt_oss_wired(self):
        """--provider ollama --model gpt-oss:20b → correct configure() call."""
        from src.config import settings as ainstein_settings
        from src.elysia_agents import configure_elysia_from_settings

        orig_provider = ainstein_settings.llm_provider
        orig_model = ainstein_settings.ollama_model
        try:
            ainstein_settings.llm_provider = "ollama"
            ainstein_settings.ollama_model = "gpt-oss:20b"

            configure_elysia_from_settings()

            elysia_config = sys.modules["elysia.config"]
            args = elysia_config.settings.configure.call_args
            assert args.kwargs["base_model"] == "gpt-oss:20b"
            assert args.kwargs["complex_model"] == "gpt-oss:20b"
            assert args.kwargs["base_provider"] == "ollama"
        finally:
            ainstein_settings.llm_provider = orig_provider
            ainstein_settings.ollama_model = orig_model


class TestIdempotencyAndSignature:
    """Verify idempotency guard rejects mismatched reconfiguration."""

    def test_same_config_twice_is_noop(self):
        """Calling with the same settings twice only configures once."""
        from src.config import settings as ainstein_settings
        from src.elysia_agents import configure_elysia_from_settings

        orig_provider = ainstein_settings.llm_provider
        orig_model = ainstein_settings.openai_chat_model
        try:
            ainstein_settings.llm_provider = "openai"
            ainstein_settings.openai_chat_model = "gpt-5-mini"

            configure_elysia_from_settings()
            configure_elysia_from_settings()  # same settings — no-op

            elysia_config = sys.modules["elysia.config"]
            assert elysia_config.settings.configure.call_count == 1
        finally:
            ainstein_settings.llm_provider = orig_provider
            ainstein_settings.openai_chat_model = orig_model

    def test_different_config_raises(self):
        """Calling with different settings after first configure raises RuntimeError."""
        import src.elysia_agents as ea
        from src.config import settings as ainstein_settings
        from src.elysia_agents import configure_elysia_from_settings

        orig_provider = ainstein_settings.llm_provider
        orig_model = ainstein_settings.openai_chat_model
        try:
            # First configure: openai / gpt-5-mini
            ainstein_settings.llm_provider = "openai"
            ainstein_settings.openai_chat_model = "gpt-5-mini"
            configure_elysia_from_settings()

            # Change settings and try again
            ainstein_settings.openai_chat_model = "gpt-5.2"
            with pytest.raises(RuntimeError, match="refusing to reconfigure"):
                configure_elysia_from_settings()
        finally:
            ainstein_settings.llm_provider = orig_provider
            ainstein_settings.openai_chat_model = orig_model

    def test_signature_stored_after_configure(self):
        """After configure, _elysia_config_signature matches settings."""
        import src.elysia_agents as ea
        from src.config import settings as ainstein_settings
        from src.elysia_agents import configure_elysia_from_settings

        orig_provider = ainstein_settings.llm_provider
        orig_model = ainstein_settings.openai_chat_model
        try:
            ainstein_settings.llm_provider = "openai"
            ainstein_settings.openai_chat_model = "gpt-5-mini"

            configure_elysia_from_settings()

            assert ea._elysia_config_signature == ("openai", "gpt-5-mini", None)
        finally:
            ainstein_settings.llm_provider = orig_provider
            ainstein_settings.openai_chat_model = orig_model

    def test_ollama_signature_includes_api_base(self):
        """Ollama signature includes the api_base URL."""
        import src.elysia_agents as ea
        from src.config import settings as ainstein_settings
        from src.elysia_agents import configure_elysia_from_settings

        orig_provider = ainstein_settings.llm_provider
        orig_model = ainstein_settings.ollama_model
        try:
            ainstein_settings.llm_provider = "ollama"
            ainstein_settings.ollama_model = "gpt-oss:20b"

            configure_elysia_from_settings()

            assert ea._elysia_config_signature == (
                "ollama", "gpt-oss:20b", ainstein_settings.ollama_url
            )
        finally:
            ainstein_settings.llm_provider = orig_provider
            ainstein_settings.ollama_model = orig_model


class TestSafetyNet:
    """Verify __init__ safety net behavior by environment."""

    def test_safety_net_in_dev_auto_configures(self):
        """In local/dev, __init__ warns and auto-configures."""
        import src.elysia_agents as ea
        import inspect

        source = inspect.getsource(ea.ElysiaRAGSystem.__init__)
        assert "configure_elysia_from_settings" in source
        assert "_elysia_configured" in source

    def test_safety_net_fails_fast_in_prod(self):
        """In prod/staging, __init__ raises RuntimeError if not configured."""
        import inspect
        from src.elysia_agents import ElysiaRAGSystem

        source = inspect.getsource(ElysiaRAGSystem.__init__)
        assert 'environment in ("prod", "staging")' in source
        assert "RuntimeError" in source

    def test_configure_called_at_all_entrypoints(self):
        """All composition roots call configure_elysia_from_settings."""
        import inspect

        from src.evaluation import test_runner
        source = inspect.getsource(test_runner.init_rag_system)
        assert "configure_elysia_from_settings" in source

    def test_safety_net_before_tool_registry(self):
        """Safety net runs before _build_tool_registry() in __init__."""
        import inspect
        from src.elysia_agents import ElysiaRAGSystem

        source = inspect.getsource(ElysiaRAGSystem.__init__)
        safety_pos = source.find("configure_elysia_from_settings")
        registry_pos = source.find("_build_tool_registry")

        assert safety_pos > 0
        assert registry_pos > 0
        assert safety_pos < registry_pos
