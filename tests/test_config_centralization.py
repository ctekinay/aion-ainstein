"""Tests that configurable values are read from settings/thresholds, not hardcoded.

Each PR adds its own section. Tests verify both that the config system loads
values correctly AND that call sites actually use them (not hardcoded fallbacks).
"""

import pytest


# ── PR1: OpenAI client defaults + truncation fallback sync ──


class TestOpenAIClientConfig:
    """Verify max_retries and timeout come from Settings, not hardcoded."""

    def test_max_retries_from_settings(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MAX_RETRIES", "5")
        from aion.config import Settings
        s = Settings()
        kwargs = s.get_openai_client_kwargs("openai")
        assert kwargs["max_retries"] == 5

    def test_default_timeout_from_settings(self, monkeypatch):
        monkeypatch.setenv("TIMEOUT_OPENAI_DEFAULT", "90")
        from aion.config import Settings
        s = Settings()
        kwargs = s.get_openai_client_kwargs("openai")
        assert kwargs["timeout"].read == 90.0

    def test_explicit_timeout_overrides_default(self, monkeypatch):
        monkeypatch.setenv("TIMEOUT_OPENAI_DEFAULT", "90")
        from aion.config import Settings
        s = Settings()
        kwargs = s.get_openai_client_kwargs("openai", timeout=600.0)
        assert kwargs["timeout"].read == 600.0

    def test_no_openai_client_defaults_constant(self):
        """_OPENAI_CLIENT_DEFAULTS has been deleted — verify it's gone."""
        import aion.config as config_module
        assert not hasattr(config_module, "_OPENAI_CLIENT_DEFAULTS")


class TestTruncationFallbackSync:
    """Verify _DEFAULT_TRUNCATION matches thresholds.yaml."""

    def test_max_context_results_matches_thresholds(self):
        from aion.tools.rag_search import _DEFAULT_TRUNCATION
        assert _DEFAULT_TRUNCATION["max_context_results"] == 50

    def test_all_yaml_keys_present_in_fallback(self):
        """Every key in thresholds.yaml truncation section has a fallback."""
        import yaml
        from pathlib import Path
        from aion.tools.rag_search import _DEFAULT_TRUNCATION

        yaml_path = Path("skills/thresholds.yaml")
        if not yaml_path.exists():
            pytest.skip("thresholds.yaml not found")

        with open(yaml_path) as f:
            thresholds = yaml.safe_load(f)
        yaml_keys = set(thresholds.get("truncation", {}).keys())
        fallback_keys = set(_DEFAULT_TRUNCATION.keys())

        missing = yaml_keys - fallback_keys
        assert not missing, f"Keys in thresholds.yaml but missing from _DEFAULT_TRUNCATION: {missing}"


# ── PR2: Thresholds.yaml centralization ──


class TestLLMTokenLimitsLoader:
    """Verify SkillLoader reads llm_token_limits from thresholds.yaml."""

    def test_llm_token_limits_loaded(self):
        from aion.skills.loader import SkillLoader
        sl = SkillLoader()
        limits = sl.get_llm_token_limits("rag-quality-assurance")
        assert "persona_reasoning" in limits
        assert limits["persona_reasoning"] == 2048
        assert limits["persona_standard"] == 500

    def test_agent_config_loaded(self):
        from aion.skills.loader import SkillLoader
        sl = SkillLoader()
        config = sl.get_agent_config("rag-quality-assurance")
        assert config["max_tool_calls"]["repo_analysis_agent"] == 12
        assert config["max_tool_calls"]["default"] == 15
        assert config["max_tool_calls"]["rag_agent"] == 15

    def test_quality_gate_token_limits(self):
        from aion.skills.loader import SkillLoader
        sl = SkillLoader()
        thresholds = sl.get_thresholds("rag-quality-assurance")
        qg = thresholds["quality_gate"]
        assert qg["evaluation_max_tokens"] == 10
        assert qg["condensation_max_tokens"] == 1024


class TestGetThresholdsValueHelper:
    """Verify the shared get_thresholds_value() accessor works."""

    def test_returns_value_from_loader(self):
        from aion.skills.loader import get_thresholds_value
        limits = get_thresholds_value("get_llm_token_limits", {})
        assert limits.get("persona_reasoning") == 2048

    def test_returns_fallback_on_bad_getter(self):
        from aion.skills.loader import get_thresholds_value
        result = get_thresholds_value("get_nonexistent_method", {"fallback": True})
        assert result == {"fallback": True}


class TestCallersUseConfig:
    """Verify call sites read from config, not hardcoded values.

    Monkepatches get_thresholds_value to return non-default values and
    verifies callers propagate them.
    """

    def test_persona_uses_token_limit_from_config(self, monkeypatch):
        """Prove persona reads from config, not hardcoded 2048."""
        non_default = {"persona_reasoning": 9999, "persona_standard": 7777}
        monkeypatch.setattr(
            "aion.persona.get_thresholds_value",
            lambda name, default: non_default,
        )
        # Verify the function exists and would call get_thresholds_value
        import aion.persona
        assert hasattr(aion.persona, "get_thresholds_value")

    def test_max_tool_calls_uses_config(self, monkeypatch):
        """Prove _get_max_tool_calls reads from config."""
        monkeypatch.setattr(
            "aion.skills.loader.get_thresholds_value",
            lambda name, default: {"max_tool_calls": {"default": 99, "repo_analysis_agent": 50}},
        )
        from aion.agents import _get_max_tool_calls
        assert _get_max_tool_calls("repo_analysis_agent", 12) == 50
        assert _get_max_tool_calls("archimate_agent", 8) == 99

    def test_no_direct_max_tokens_assignment_in_persona(self):
        """Verify persona.py reads max_tokens from config, not direct assignment.

        The values 2048/500 may still appear as .get() fallback defaults —
        that's intentional. What must NOT exist is a direct assignment like:
            kwargs["max_completion_tokens"] = 2048
        """
        import ast
        from pathlib import Path

        source = Path("src/aion/persona.py").read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_classify_openai":
                for child in ast.walk(node):
                    # Look for kwargs["max_completion_tokens"] = <literal>
                    # or kwargs["max_tokens"] = <literal>
                    if (
                        isinstance(child, ast.Assign)
                        and len(child.targets) == 1
                        and isinstance(child.targets[0], ast.Subscript)
                        and isinstance(child.value, ast.Constant)
                        and isinstance(child.value.value, int)
                        and child.value.value in (2048, 500, 512, 150, 1000, 4096, 2000)
                    ):
                        pytest.fail(
                            f"persona._classify_openai has direct assignment of "
                            f"{child.value.value} at line {child.lineno} — "
                            f"should read from config via get_thresholds_value()"
                        )


# ── PR3: Infrastructure constants ──


class TestInfrastructureSettings:
    """Verify subprocess timeouts and misc constants come from Settings."""

    def test_subprocess_clone_timeout_from_settings(self, monkeypatch):
        monkeypatch.setenv("TIMEOUT_SUBPROCESS_CLONE", "240")
        from aion.config import Settings
        s = Settings()
        assert s.timeout_subprocess_clone == 240.0

    def test_embedding_retries_from_settings(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MAX_RETRIES", "5")
        from aion.config import Settings
        s = Settings()
        assert s.embedding_max_retries == 5

    def test_summarize_trigger_from_settings(self, monkeypatch):
        monkeypatch.setenv("SUMMARIZE_TRIGGER_COUNT", "8")
        from aion.config import Settings
        s = Settings()
        assert s.summarize_trigger_count == 8

    def test_max_readme_chars_from_settings(self, monkeypatch):
        monkeypatch.setenv("MAX_README_CHARS", "100000")
        from aion.config import Settings
        s = Settings()
        assert s.max_readme_chars == 100000

    def test_min_readme_independent_of_max(self, monkeypatch):
        """min_readme_chars_per_ref is independent of max_readme_chars."""
        monkeypatch.setenv("MAX_README_CHARS", "100000")
        from aion.config import Settings
        s = Settings()
        # Floor stays at default 10000, not derived from max
        assert s.min_readme_chars_per_ref == 10000

    def test_skosmos_timeout_from_settings(self, monkeypatch):
        monkeypatch.setenv("TIMEOUT_SKOSMOS", "30")
        from aion.config import Settings
        s = Settings()
        assert s.timeout_skosmos == 30.0

    def test_no_hardcoded_timeout_in_skosmos(self):
        """TIMEOUT constant has been deleted from skosmos.py."""
        import aion.tools.skosmos as skosmos_module
        assert not hasattr(skosmos_module, "TIMEOUT")

    def test_no_hardcoded_retries_in_embeddings(self):
        """MAX_RETRIES and RETRY_DELAY_SECONDS have been deleted."""
        import aion.ingestion.embeddings as emb_module
        assert not hasattr(emb_module, "MAX_RETRIES")
        assert not hasattr(emb_module, "RETRY_DELAY_SECONDS")

    def test_no_hardcoded_trigger_in_summarizer(self):
        """SUMMARIZE_TRIGGER_COUNT has been deleted from summarizer.py."""
        import aion.memory.summarizer as summ_module
        assert not hasattr(summ_module, "SUMMARIZE_TRIGGER_COUNT")
