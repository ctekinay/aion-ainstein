"""ISS-002 regression: YAML→XML pipeline is gated on the declarative
``yaml_pipeline`` capability, not a hardcoded skill name.

Previously the gate at ``generation.py:~350`` (and the registry-context
injection at ``:~190``) read::

    if skill_entry.name == "archimate-generator":

The live skill is ``archimate-oxc-generator`` (in the enterpower plugin),
so the gate was permanently False. Raw YAML flowed into validation,
``_extract_xml`` found nothing, and users got the saved artifact as
unusable YAML. Existing generation tests mocked above the gate and did
not catch it — these tests deliberately don't.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aion.generation import GenerationPipeline
from aion.skills.registry import SkillRegistry, SkillRegistryEntry


# Borrowed from tests/test_yaml_to_xml.py — a known-good ArchiMate YAML.
VALID_YAML = """\
model:
  name: "Gate Regression Fixture"
  documentation: "Tiny model used to prove the YAML→XML gate fires."

elements:
  - id: b1
    type: BusinessProcess
    name: "Order Processing"

relationships: []
"""


_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENTERPOWER_PLUGIN_DIR = _REPO_ROOT / "plugins" / "enterpower-architecture"
_ENTERPOWER_REGISTRY = _ENTERPOWER_PLUGIN_DIR / ".ainstein-plugin" / "skills-registry.yaml"
_ENTERPOWER_SKILLS_DIR = _ENTERPOWER_PLUGIN_DIR / "skills"


# ---------------------------------------------------------------------------
# Test A — real-registry parser: the yaml_pipeline opt-in lands on the entry
# ---------------------------------------------------------------------------

class TestEnterpowerRegistryParsesYamlPipeline:
    """No mocks at the registry level. Loads the real enterpower registry
    from disk and asserts the parsed ``yaml_pipeline`` value on the entry.
    """

    @pytest.fixture
    def registry(self) -> SkillRegistry:
        reg = SkillRegistry(
            skills_dir=_ENTERPOWER_SKILLS_DIR,
            registry_path=_ENTERPOWER_REGISTRY,
        )
        reg.load_registry()
        return reg

    def test_archimate_oxc_generator_opts_in(self, registry: SkillRegistry):
        entry = registry.get_skill_entry("archimate-oxc-generator")
        assert entry is not None, "archimate-oxc-generator not in registry"
        assert entry.yaml_pipeline is True, (
            "archimate-oxc-generator must declare yaml_pipeline: true — "
            "this is the ISS-002 regression guard"
        )

    @pytest.mark.parametrize(
        "name",
        [
            # Generates VIEWS data, not OXC model XML.
            "archimate-visual-composer",
            # Generates an HTML explorer.
            "repo-architecture-explorer",
        ],
    )
    def test_other_generation_skills_stay_opted_out(
        self, registry: SkillRegistry, name: str,
    ):
        entry = registry.get_skill_entry(name)
        assert entry is not None, f"{name} not in registry"
        assert entry.yaml_pipeline is False, (
            f"{name} declares execution: generation but must NOT opt into "
            "the YAML→XML pipeline — its output is not OXC ArchiMate XML"
        )


# ---------------------------------------------------------------------------
# Test B — the actual gate at generation.py:~350 fires on yaml_pipeline=True
# and does NOT fire on yaml_pipeline=False
# ---------------------------------------------------------------------------

class _StubRegistry:
    """Minimal stand-in for the multi-plugin registry. The ``SkillRegistryEntry``
    is real — only the lookup is stubbed — so the gate evaluates a real
    dataclass instance with the chosen ``yaml_pipeline`` value.
    """

    def __init__(self, entry: SkillRegistryEntry):
        self._entry = entry

    def get_generation_skill(self, skill_tags: Any) -> SkillRegistryEntry:
        return self._entry

    def get_loader_for_skill(self, name: str) -> None:
        return None  # → system_prompt = "" (skipping skill content load)


async def _stub_call_llm(self, system_prompt, user_prompt, max_tokens_override=None):
    """Returns the VALID_YAML fixture wrapped in markdown fences.
    Matches the real ``_call_llm`` shape: ``(text, stats)``.
    """
    return (
        f"```yaml\n{VALID_YAML}```",
        {"prompt_tokens": 0, "completion_tokens": 0},
    )


@pytest.fixture
def conversion_spy(monkeypatch):
    """Replace ``aion.generation.yaml_to_archimate_xml`` with a spy that records
    whether the YAML→XML branch was entered. Returns the spy.

    The spy delegates to a deterministic stub instead of the real converter
    so the test is independent of converter behavior (which has its own
    coverage in ``test_yaml_to_xml.py``).
    """
    calls: list[str] = []

    def _spy(yaml_text: str) -> tuple[str, dict]:
        calls.append(yaml_text)
        return ("<model>stub-xml</model>", {})

    monkeypatch.setattr("aion.generation.yaml_to_archimate_xml", _spy)
    return calls


@pytest.fixture
def patched_pipeline(monkeypatch):
    """A ``GenerationPipeline`` whose LLM and SQLite-backed prompt-registry are
    stubbed *below* the gate at ``:~350``. The gate itself is the real code
    path under test.
    """
    monkeypatch.setattr(GenerationPipeline, "_call_llm", _stub_call_llm, raising=True)
    # Registry-context injection (also gated on yaml_pipeline) hits SQLite;
    # stub to [] so the test does not depend on the on-disk registry DB.
    monkeypatch.setattr(
        "aion.generation.query_registry_for_prompt",
        lambda **kwargs: [],
    )
    return GenerationPipeline(client=None)  # client unused — source_text passed


def _entry(name: str, yaml_pipeline: bool) -> SkillRegistryEntry:
    return SkillRegistryEntry(
        name=name,
        path=f"{name}/SKILL.md",
        description="(regression-test entry)",
        execution="generation",
        validation_tool="",  # skip post-generation validation
        yaml_pipeline=yaml_pipeline,
    )


@pytest.mark.asyncio
async def test_gate_fires_when_yaml_pipeline_true(
    patched_pipeline, conversion_spy, monkeypatch,
):
    """yaml_pipeline=True → the YAML→XML converter is invoked at ``:~350``."""
    monkeypatch.setattr(
        "aion.generation.get_skill_registry",
        lambda: _StubRegistry(_entry("archimate-oxc-generator", yaml_pipeline=True)),
    )

    response, _sources = await patched_pipeline.generate(
        query="generate a small archimate model",
        skill_tags=["archimate"],
        source_text="(source content stub — bypasses Weaviate fetch)",
        conversation_id=None,
    )

    assert len(conversion_spy) == 1, (
        "yaml_to_archimate_xml was not called — the gate at generation.py:~350 "
        "did NOT fire on yaml_pipeline=True (ISS-002 regression)"
    )
    # And the user-facing response goes down the artifact path — _build_response
    # recognises ``<model`` as artifact content and does not inline it.
    assert "saved as an artifact" in response


@pytest.mark.asyncio
async def test_gate_skipped_when_yaml_pipeline_false(
    patched_pipeline, conversion_spy, monkeypatch,
):
    """Negative control: yaml_pipeline=False → the converter is NOT invoked.

    Without this assertion the positive test above is vacuous: a permanently-
    True gate would also pass. This proves the gate is actually gating.
    """
    monkeypatch.setattr(
        "aion.generation.get_skill_registry",
        lambda: _StubRegistry(_entry("some-other-generation-skill", yaml_pipeline=False)),
    )

    response, _sources = await patched_pipeline.generate(
        query="generate something else",
        skill_tags=["other"],
        source_text="(source content stub)",
        conversation_id=None,
    )

    assert conversion_spy == [], (
        "yaml_to_archimate_xml was unexpectedly called for yaml_pipeline=False "
        "— the gate at generation.py:~350 is not actually gating"
    )
    # And the raw LLM YAML keys leak inline through _build_response, since
    # the content does not match the artifact-detection heuristic.
    assert "elements:" in response
