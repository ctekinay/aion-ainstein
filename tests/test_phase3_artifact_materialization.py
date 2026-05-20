"""Phase 3 — artifact-materialization host capability (hard part C).

Authority model under test: `artifact_materialization@1` — SQLite
authoritative, materialized files ephemeral hook inputs, no sync-back.

Positive controls (engagement discipline — assert the mechanism CAN
fire, never just assert-absence):
  * a REQUIRING plugin's hook receives a real, existing, readable path
    whose bytes are the artifact content (mechanism fires);
  * paired in the same scenario, a NON-REQUIRING plugin's hook receives
    the bare filename only (A5 opt-in protects existing semantics — the
    intersection of requiring×non-requiring asserted together so the
    silent "both behave the same" failure can't pass);
  * the materialized path does NOT exist after the call (ephemeral
    lifecycle / no sync-back).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from aion.skills.artifact_materialization import (
    materialized_artifact,
    plugin_requires_materialization,
)
from aion.skills.hooks import fire_post_tool_use
from aion.skills.multi_registry import (
    MultiPluginRegistry,
    _reset_multi_registry_for_tests,
)
from aion.skills.plugin import load_plugin_manifest

# Hook script: reads the stdin payload, writes "<file_path>|<EXISTS|MISSING>|
# <content-or-empty>" to $RESULT_LOG. Lets the test assert exactly what the
# hook saw — a real readable path + content, or just a filename string.
_HOOK_PY = '''import json, os, sys
d = json.load(sys.stdin)
fp = d["tool_input"]["file_path"]
log = os.environ["RESULT_LOG"]
exists = os.path.isfile(fp)
body = ""
if exists:
    with open(fp, encoding="utf-8") as fh:
        body = fh.read()
with open(log, "a", encoding="utf-8") as out:
    out.write(f"{fp}|{'EXISTS' if exists else 'MISSING'}|{body}\\n")
'''


def _plugin(root: Path, name: str, *, requires: bool) -> Path:
    d = root / ".ainstein-plugin"
    d.mkdir(parents=True, exist_ok=True)
    script = root / "hook.py"
    script.write_text(_HOOK_PY, encoding="utf-8")
    manifest = {
        "name": name, "runtime": "ainstein",
        "hooks": {
            "PostToolUse": [{
                "matcher": "Write",
                "hooks": [{"command": f"{sys.executable} {script}"}],
            }]
        },
    }
    if requires:
        manifest["requires_host_api"] = {"artifact_materialization": ">=1"}
    (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (d / "skills-registry.yaml").write_text(
        yaml.safe_dump({"skills": []}, sort_keys=False), encoding="utf-8"
    )
    (root / "skills").mkdir(exist_ok=True)
    return root


def _install(*roots: Path) -> MultiPluginRegistry:
    _reset_multi_registry_for_tests()
    import aion.skills.multi_registry as mr
    m = MultiPluginRegistry()
    for r in roots:
        m.add_plugin_from_object(load_plugin_manifest(r))
    m.load()
    mr._global_multi = m
    return m


class TestMaterializedArtifactContextManager:
    def test_yields_real_path_with_content_then_cleans_up(self):
        captured = {}
        with materialized_artifact("model.xml", "<archimate>hi</archimate>") as p:
            captured["path"] = p
            assert p.is_file(), "must yield a real existing file"
            assert p.read_text() == "<archimate>hi</archimate>"
            assert p.name == "model.xml"
        # Ephemeral: gone after the context (no sync-back, SQLite authoritative).
        assert not captured["path"].exists()
        assert not captured["path"].parent.exists()

    def test_filename_is_leaf_only_no_path_traversal(self):
        with materialized_artifact("../../etc/evil.txt", "x") as p:
            assert p.name == "evil.txt"
            assert ".." not in str(p)
            assert p.is_file()


class TestPluginRequiresMaterialization:
    def test_declared_and_host_supports_is_true(self, tmp_path):
        r = _plugin(tmp_path / "r", "r", requires=True)
        plug = load_plugin_manifest(r)
        assert plugin_requires_materialization(plug) is True

    def test_not_declared_is_false(self, tmp_path):
        n = _plugin(tmp_path / "n", "n", requires=False)
        plug = load_plugin_manifest(n)
        assert plugin_requires_materialization(plug) is False


class TestHookFilePathSemantics:
    def test_requiring_gets_real_path_nonrequiring_gets_filename(
        self, tmp_path, monkeypatch
    ):
        """The untested intersection asserted in ONE scenario: with a
        requiring AND a non-requiring plugin both loaded, the requiring
        hook must see a real readable file with the content, and the
        non-requiring hook must see the bare filename — proving (a) the
        mechanism fires and (b) A5 opt-in protects the old semantics.
        Testing them separately could let 'both behave identically' pass
        silently.
        """
        log = tmp_path / "result.log"
        monkeypatch.setenv("RESULT_LOG", str(log))
        req = _plugin(tmp_path / "req", "req-plug", requires=True)
        non = _plugin(tmp_path / "non", "non-plug", requires=False)
        _install(req, non)

        content = "<archimate>PHASE3-CONTENT</archimate>"
        fire_post_tool_use(
            "diagram.archimate", tool_name="Write",
            content=content, content_type="application/xml",
        )

        lines = [l for l in log.read_text().splitlines() if l.strip()]
        assert len(lines) == 2, f"expected 2 hook records, got {lines}"
        rows = [tuple(l.split("|", 2)) for l in lines]

        # Requiring plugin: real existing path + exact content (mechanism fired).
        req_rows = [r for r in rows if r[1] == "EXISTS"]
        assert len(req_rows) == 1, f"requiring hook saw no real file: {rows}"
        fp, _, body = req_rows[0]
        assert fp != "diagram.archimate", "requiring plugin still got filename-only"
        assert Path(fp).name == "diagram.archimate"
        assert body == content, "materialized file content mismatch"

        # Non-requiring plugin: bare filename, no real file (A5 unchanged).
        non_rows = [r for r in rows if r[1] == "MISSING"]
        assert len(non_rows) == 1, f"non-requiring hook unexpectedly saw a file: {rows}"
        assert non_rows[0][0] == "diagram.archimate", (
            "A5 regression: non-requiring plugin's file_path is not the bare filename"
        )

        # Ephemeral lifecycle: the materialized path is gone post-call.
        assert not Path(req_rows[0][0]).exists(), (
            "materialized artifact not cleaned up (must be ephemeral, no sync-back)"
        )

        _reset_multi_registry_for_tests()

    def test_no_content_means_filename_only_even_if_required(
        self, tmp_path, monkeypatch
    ):
        """Defensive: a requiring plugin still gets filename-only when no
        content is supplied (can't materialize nothing) — never an error."""
        log = tmp_path / "r.log"
        monkeypatch.setenv("RESULT_LOG", str(log))
        req = _plugin(tmp_path / "req", "req-plug", requires=True)
        _install(req)
        fire_post_tool_use("x.xml", tool_name="Write")  # no content kwarg
        line = log.read_text().strip()
        assert line.endswith("|MISSING|")
        assert line.split("|")[0] == "x.xml"
        _reset_multi_registry_for_tests()
