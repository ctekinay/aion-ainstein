"""Phase 1 — additive manifest contract (role, manifest_version,
requires_host_api) + host-side capability registry (Amendment A3).

Strictly additive / backward-compatible: a manifest with NONE of the new
fields must load with safe defaults; `requires_host_api` is parsed but
NOT enforced at load in Phase 1 (enforcement deferred so adding the field
can never break loading). Unknown `role` is rejected EARLY so a typo
cannot silently change host policy later.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aion.skills.plugin import (
    DEFAULT_MANIFEST_VERSION,
    DEFAULT_PLUGIN_ROLE,
    HOST_CAPABILITIES,
    PluginManifestError,
    host_supports,
    load_plugin_manifest,
)

# Re-baseline (Phase-5 supersession): ainstein-core was deleted; the
# bundled plugin that exercises the Phase-1 manifest contract is now
# ainstein-kernel (role: kernel).
AINSTEIN_KERNEL_ROOT = Path(__file__).parent.parent / "plugins" / "ainstein-kernel"


def _write(root: Path, payload: dict) -> Path:
    d = root / ".ainstein-plugin"
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")
    return root


class TestBackwardCompatibleDefaults:
    def test_legacy_manifest_loads_with_safe_defaults(self, tmp_path):
        """A manifest with NONE of the Phase-1 fields still loads."""
        p = load_plugin_manifest(_write(tmp_path, {
            "name": "legacy", "runtime": "ainstein",
        }))
        assert p.role == DEFAULT_PLUGIN_ROLE == "domain"
        assert p.manifest_version == DEFAULT_MANIFEST_VERSION == "1.0"
        assert p.requires_host_api == {}

    def test_explicit_fields_parsed(self, tmp_path):
        p = load_plugin_manifest(_write(tmp_path, {
            "name": "k", "runtime": "ainstein",
            "role": "kernel", "manifest_version": "2.1",
            "requires_host_api": {"artifact_materialization": ">=1"},
        }))
        assert p.role == "kernel"
        assert p.manifest_version == "2.1"
        assert p.requires_host_api == {"artifact_materialization": ">=1"}


class TestRoleValidation:
    def test_unknown_role_rejected_early(self, tmp_path):
        with pytest.raises(PluginManifestError, match="role"):
            load_plugin_manifest(_write(tmp_path, {
                "name": "x", "runtime": "ainstein", "role": "kernelish",
            }))

    def test_both_valid_roles_accepted(self, tmp_path):
        for r in ("kernel", "domain"):
            p = load_plugin_manifest(_write(tmp_path / r, {
                "name": r, "runtime": "ainstein", "role": r,
            }))
            assert p.role == r


class TestRequiresHostApiParsedNotEnforced:
    def test_non_dict_requires_host_api_rejected(self, tmp_path):
        with pytest.raises(PluginManifestError, match="requires_host_api"):
            load_plugin_manifest(_write(tmp_path, {
                "name": "x", "runtime": "ainstein",
                "requires_host_api": ["not", "a", "dict"],
            }))

    def test_unsatisfiable_requirement_still_loads_phase1(self, tmp_path):
        """Phase 1 parses but does NOT enforce: a plugin requiring a host
        capability the host does not provide must STILL load (enforcement
        is a later phase). This is the positive control proving
        non-enforcement, not just absence of a check.
        """
        p = load_plugin_manifest(_write(tmp_path, {
            "name": "needy", "runtime": "ainstein",
            "requires_host_api": {"does_not_exist_yet": ">=99"},
        }))
        assert p.requires_host_api == {"does_not_exist_yet": ">=99"}
        # And the host genuinely does NOT provide it (control):
        assert host_supports("does_not_exist_yet", 99) is False


class TestHostSideCapabilityRegistry:
    def test_artifact_materialization_registered_in_phase3(self):
        """Cross-phase re-baseline (intended, not a silent break): Phase 1
        asserted HOST_CAPABILITIES == {} 'until artifact_materialization
        arrives in Phase 3'. Phase 3 registered it host-side at major 1,
        so this assertion is deliberately updated with that rationale —
        the invariant evolved as the plan predicted, it was not broken.
        """
        assert HOST_CAPABILITIES.get("artifact_materialization") == 1, (
            "Phase 3 registers artifact_materialization@1 host-side (A3 "
            "two-sided versioning); host_supports() must now report it"
        )
        assert host_supports("artifact_materialization", 1) is True
        assert host_supports("artifact_materialization", 2) is False

    def test_host_supports_logic(self, monkeypatch):
        assert host_supports("anything", 1) is False  # unregistered capability
        # Inject a provided capability and exercise the >= comparison.
        monkeypatch.setitem(HOST_CAPABILITIES, "artifact_materialization", 1)
        assert host_supports("artifact_materialization", 1) is True
        assert host_supports("artifact_materialization", 2) is False  # major gate
        assert host_supports("other", 1) is False


class TestBundledManifestDeclaresFields:
    def test_kernel_manifest_has_phase1_fields(self):
        p = load_plugin_manifest(AINSTEIN_KERNEL_ROOT)
        assert p.name == "ainstein-kernel"
        # Post Phase-4 split: the kernel declares role=kernel explicitly.
        assert p.role == "kernel"
        assert p.manifest_version == "1.0"
        assert p.requires_host_api == {}
