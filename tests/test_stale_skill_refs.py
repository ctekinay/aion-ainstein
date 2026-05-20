"""Tests for the stale-skill-ref startup validator (ISS-003a defense-in-depth).

The validator scans ``src/aion/`` for kebab-case quoted-literals that
resemble skill names but aren't in the loaded set — catching the ISS-002
class of bug at startup rather than at user-query time.
"""
from __future__ import annotations

import logging

import pytest

from aion.diagnostics.stale_skill_refs import (
    _EXCLUSIONS,
    warn_on_stale_skill_refs,
)


# ---------------------------------------------------------------------------
# Positive control — the validator actually fires on stale literals
# ---------------------------------------------------------------------------

class TestPositiveControl:
    """Without this, the assert-absence tests below are vacuous: a permanently
    silent validator would pass everything else too.
    """

    def test_stale_literal_is_surfaced(self, tmp_path, caplog):
        """A kebab-case literal starting with a gating prefix, not in the
        loaded set and not in exclusions, MUST be reported.
        """
        (tmp_path / "fake_gate.py").write_text(
            'if skill_entry.name == "archimate-ghost-skill":\n    pass\n',
            encoding="utf-8",
        )
        caplog.set_level(logging.WARNING, logger="aion.diagnostics.stale_skill_refs")
        findings = warn_on_stale_skill_refs(
            loaded_skill_names={"archimate-oxc-generator"},
            src_root=tmp_path,
        )
        assert "archimate-ghost-skill" in findings
        # And the WARNING log record has the documented shape.
        msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("archimate-ghost-skill" in m and "stale-skill-ref" in m for m in msgs), msgs


# ---------------------------------------------------------------------------
# Negative-side controls — every reason for filtering is paired with a hit
# ---------------------------------------------------------------------------

class TestFilters:
    """Each filter test pairs the assert-absence with a positive control in
    the same fixture: if the validator stops firing entirely, the absence
    tests would silently pass — so every fixture also includes a literal
    that MUST be reported.
    """

    def test_literal_matching_loaded_skill_is_filtered(self, tmp_path):
        (tmp_path / "fake.py").write_text(
            'real = "archimate-oxc-generator"\n'  # in loaded set — must be ignored
            'stale = "archimate-ghost-skill"\n',   # control — must fire
            encoding="utf-8",
        )
        findings = warn_on_stale_skill_refs(
            loaded_skill_names={"archimate-oxc-generator"},
            src_root=tmp_path,
        )
        assert "archimate-oxc-generator" not in findings
        assert "archimate-ghost-skill" in findings  # positive control

    def test_literal_in_exclusion_set_is_filtered(self, tmp_path):
        """All entries in ``_EXCLUSIONS`` must produce no warning."""
        lines = [f'x = "{name}"' for name in sorted(_EXCLUSIONS)]
        lines.append('stale = "archimate-ghost-skill"')  # positive control
        (tmp_path / "fake.py").write_text("\n".join(lines), encoding="utf-8")
        findings = warn_on_stale_skill_refs(
            loaded_skill_names=set(),  # nothing loaded — only exclusions protect
            src_root=tmp_path,
        )
        for excl in _EXCLUSIONS:
            assert excl not in findings, f"exclusion {excl!r} unexpectedly surfaced"
        assert "archimate-ghost-skill" in findings  # positive control

    def test_non_gating_prefix_is_filtered(self, tmp_path):
        """Names not starting with a gating prefix must be ignored, even if
        they otherwise match the kebab-case shape.
        """
        (tmp_path / "fake.py").write_text(
            'a = "frontend-component"\n'   # not a gating prefix
            'b = "user-session-id"\n'      # not a gating prefix
            'c = "rag-provider"\n'         # rag- is deliberately not gated
            'd = "persona-model"\n'        # persona- is deliberately not gated
            'stale = "archimate-ghost-skill"\n',  # positive control
            encoding="utf-8",
        )
        findings = warn_on_stale_skill_refs(loaded_skill_names=set(), src_root=tmp_path)
        for noise in ("frontend-component", "user-session-id", "rag-provider", "persona-model"):
            assert noise not in findings
        assert "archimate-ghost-skill" in findings  # positive control


# ---------------------------------------------------------------------------
# Resilience — the validator must never raise, never block startup
# ---------------------------------------------------------------------------

class TestResilience:
    def test_missing_root_is_noop(self, tmp_path):
        """Pointing at a non-existent directory returns empty findings,
        never raises.
        """
        findings = warn_on_stale_skill_refs(
            loaded_skill_names=set(),
            src_root=tmp_path / "does-not-exist",
        )
        assert findings == {}

    def test_unreadable_file_is_skipped(self, tmp_path):
        """A file the scanner can't decode (binary) must not raise — only
        the candidate from the readable sibling file is returned.
        """
        # Real binary content with no UTF-8 sequence: forces UnicodeDecodeError
        (tmp_path / "binary.py").write_bytes(b"\xff\xfe\x00\x01some-bytes")
        (tmp_path / "readable.py").write_text(
            'gate = "archimate-ghost-skill"\n', encoding="utf-8",
        )
        findings = warn_on_stale_skill_refs(
            loaded_skill_names=set(),
            src_root=tmp_path,
        )
        assert "archimate-ghost-skill" in findings

    def test_returns_dict_for_test_assertions(self, tmp_path):
        """The function returns the findings dict (not None) so test
        harnesses can assert on it. Documents the contract.
        """
        result = warn_on_stale_skill_refs(loaded_skill_names=set(), src_root=tmp_path)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Clean-tree contract — running the real validator against the real
# loaded-skill set must produce zero warnings on the post-0a/0c tree.
# This is the contract that says "the next push of 0d / future phases
# must not regress this without an audited exclusion-set update".
# ---------------------------------------------------------------------------

class TestCleanTreeIsZeroWarnings:
    @pytest.mark.parametrize("src_root", ["src/aion"])
    def test_no_warnings_against_real_loaded_set(self, src_root):
        """Reproduces what lifespan does at startup: scan the real
        ``src/aion/`` against the union of loaded skill names from every
        plugin's registry.
        """
        from pathlib import Path


        from aion.skills.registry import SkillRegistry

        repo = Path(__file__).resolve().parent.parent
        plugins_dir = repo / "plugins"
        loaded: set[str] = set()
        for plugin_dir in sorted(plugins_dir.iterdir()):
            registry_yaml = plugin_dir / ".ainstein-plugin" / "skills-registry.yaml"
            if not registry_yaml.exists():
                continue
            reg = SkillRegistry(
                skills_dir=plugin_dir / "skills",
                registry_path=registry_yaml,
            )
            reg.load_registry()
            loaded.update(e.name for e in reg.list_skills())
        assert loaded, "no skills loaded across plugins — fixture is broken"

        findings = warn_on_stale_skill_refs(
            loaded_skill_names=loaded,
            src_root=str(repo / src_root),
        )
        assert findings == {}, (
            f"validator surfaced stale-skill-ref candidates on a clean tree: "
            f"{findings} — either fix the literal at the cited file, or "
            f"audit it as a non-skill literal and add to _EXCLUSIONS with a "
            f"comment explaining what it actually is. Never add a real skill "
            f"name to the exclusion list."
        )
