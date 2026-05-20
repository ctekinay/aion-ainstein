"""Artifact-materialization host capability (Phase 3, hard part C).

AInstein stores artifacts as SQLite blobs, not on-disk files; PostToolUse
hooks therefore receive only a *filename*, not a real path. File-oriented
plugin tooling (e.g. enterpower's ``archimate-view-post-write.sh``, which
rsyncs a written file into a Vite work dir) cannot function with a bare
filename. This module is the first-class host capability that projects a
SQLite-stored artifact onto a real filesystem path for the duration of a
hook invocation.

**Authority model — `artifact_materialization@1` (locked Phase-3 decision):**
SQLite remains authoritative. Materialized files are **ephemeral hook
inputs**: written before the hook runs, removed immediately after. There
is **no automatic sync-back** — mutations a hook makes to the materialized
file are NOT written back to SQLite. If write-back is ever required it
will be a *separate* versioned capability (``artifact_sync_back@1``), not
a widening of this one.

**Opt-in (A5):** only plugins that declare
``requires_host_api: {"artifact_materialization": ...}`` AND that the host
supports receive a real path. Every other plugin keeps the unchanged
filename-only payload — existing hook-payload tests are protected by
construction.

Capability identity: name ``artifact_materialization``, major version 1
(registered host-side in ``aion.skills.plugin.HOST_CAPABILITIES``).
"""

from __future__ import annotations

import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

CAPABILITY_NAME = "artifact_materialization"
CAPABILITY_MAJOR = 1


@contextmanager
def materialized_artifact(filename: str, content: str):
    """Yield a real on-disk path to ``content`` under ``filename``.

    Ephemeral: a fresh temp directory is created, ``content`` is written
    to ``<tmp>/<safe-filename>``, the real path is yielded, and the entire
    directory is removed on exit (success or error) — SQLite stays
    authoritative, no sync-back. ``filename`` is treated as a leaf name
    only (any path components are stripped) so a crafted artifact name
    cannot escape the temp dir.
    """
    leaf = Path(filename).name or "artifact"
    tmpdir = Path(tempfile.mkdtemp(prefix="ainstein-artifact-"))
    target = tmpdir / leaf
    try:
        target.write_text(content, encoding="utf-8")
        logger.debug(
            "Materialized artifact %r at %s (%d chars; ephemeral)",
            leaf, target, len(content),
        )
        yield target
    finally:
        try:
            for child in tmpdir.iterdir():
                child.unlink(missing_ok=True)
            tmpdir.rmdir()
            logger.debug("Cleaned up materialized artifact dir %s", tmpdir)
        except Exception:
            logger.warning(
                "Failed to clean up materialized artifact dir %s "
                "(ephemeral; safe to ignore)", tmpdir, exc_info=True,
            )


def plugin_requires_materialization(plugin) -> bool:
    """True iff ``plugin`` declares it requires the artifact-materialization
    host capability AND the host actually provides a compatible major.

    Gated by ``host_supports`` (Phase-1 two-sided versioning, A3): a plugin
    asking for a capability the host does not provide does NOT get a real
    path — it falls back to filename-only, never an error.
    """
    from aion.skills.plugin import host_supports

    req = getattr(plugin, "requires_host_api", {}) or {}
    if CAPABILITY_NAME not in req:
        return False
    return host_supports(CAPABILITY_NAME, CAPABILITY_MAJOR)
