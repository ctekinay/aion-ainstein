# Security — Known Dependency Vulnerabilities

This document tracks known vulnerabilities in transitive dependencies,
their risk assessment, and resolution status.

---

## Open

### CVE-2025-69872 — diskcache <= 5.6.3 (unsafe pickle deserialization)

| Field | Value |
|-------|-------|
| **Package** | `diskcache==5.6.3` |
| **GHSA** | GHSA-w8v5-vhqr-4h9v |
| **CVSS** | NVD v3.1: 9.8 CRITICAL / GitHub v4.0: 5.2 MODERATE |
| **Status** | No upstream fix available |

**Dependency chain:**
`esa-ainstein-artifacts` → `elysia-ai` → `dspy-ai` → `dspy` → `diskcache==5.6.3`

**What it is:**
DiskCache uses Python's `pickle` for serialization. An attacker with write
access to the cache directory can inject a malicious pickle payload that
executes arbitrary code when the application reads from the cache.

**Why the NVD score is misleading:**
The NVD v3.1 score of 9.8 uses `AV:N` (network attack vector). This is
incorrect — exploitation requires **local filesystem write access** to the
cache directory (`~/.dspy_cache/`). GitHub's v4.0 score of 5.2 MODERATE
(`AV:L`) is more accurate.

**Why it cannot be fixed:**
- 5.6.3 is the latest release on PyPI (August 2023)
- The maintainer has not responded to [issue #357](https://github.com/grantjenks/python-diskcache/issues/357)
- `diskcache2` (a community fork) contains the same pickle code — it only adds type hints
- No patched version exists to bump to

**Why it cannot be removed:**
DSPy hard-imports `diskcache` at module level (`from diskcache import FanoutCache`
in `dspy/clients/cache.py`). Removing the package causes `import dspy` to fail
with `ModuleNotFoundError`, which cascades through Elysia and prevents the
application from starting.

**Why the risk is low in our deployment:**
- Attack requires local filesystem write access to `~/.dspy_cache/`
- Default directory permissions are `0700` (owner-only access)
- No user input reaches the cache file path or directory
- Only the application process accesses the cache directory

**Upstream tracking:**
DSPy has an open effort to make `diskcache` optional
([PR #9376](https://github.com/stanfordnlp/dspy/issues/8717)).
When merged and released, updating `dspy-ai` will remove the transitive
dependency entirely.

---

## Resolved

### authlib — alg:none signature bypass
- **Resolved:** Bumped 1.6.6 → 1.6.9 in `uv.lock`

### pip — path traversal (CVE in pip < 26.0)
- **Resolved:** Bumped 25.3 → 26.0.1 in `uv.lock`

### python-multipart — GHSA-cfh3-3jmp-rvhc
- **Resolved:** Override in `pyproject.toml` (`[tool.uv]` override-dependencies `python-multipart>=0.0.20`)
- `elysia-ai==0.2.8` pins `python-multipart==0.0.18` exactly; override is required
